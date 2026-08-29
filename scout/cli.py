"""Scout CLI: Universal Music Discovery & Archiving Command Line Interface."""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from rich.table import Table

from scout.core.config import Config, load_config
from scout.core.dedupe import HistoryStore
from scout.core.downloader import AudioDownloader
from scout.core.models import Playlist, Track
from scout.dna.engine import PlaylistDNAEngine
from scout.integrations.mpris import get_current_playing_track
from scout.integrations.navidrome import NavidromeScanner
from scout.integrations.notifier import notify
from scout.integrations.subsonic import SubsonicClient
from scout.providers.lastfm import LastFMProvider
from scout.providers.spotify import SpotifyProvider
from scout.providers.ytmusic import YTMusicProvider

console = Console()


def render_banner():
    banner_text = (
        "[bold cyan]🎯 SCOUT[/bold cyan] [dim]v1.0.0[/dim]\n"
        "[dim]Universal Music Discovery & Archiving Engine[/dim]"
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))


def resolve_track_from_input(
    query_or_url: str,
    spotify: SpotifyProvider,
    ytm: YTMusicProvider,
    interactive: bool = True,
) -> Optional[Track]:
    # 1. Check if Spotify URL
    if SpotifyProvider.is_spotify_url(query_or_url):
        entity_type, _ = SpotifyProvider.parse_url_type(query_or_url)
        if entity_type == "track":
            with console.status("[bold green]Parsing Spotify track metadata...[/bold green]"):
                sp_track = spotify.get_track(query_or_url)
            if sp_track:
                with console.status(f"[bold cyan]Matching studio audio for {sp_track.display_name}...[/bold cyan]"):
                    yt_track = ytm.search_track(sp_track.artist, sp_track.title, album=sp_track.album)
                if yt_track:
                    # Inherit Spotify high-res metadata if better
                    if sp_track.cover_url:
                        yt_track.cover_url = sp_track.cover_url
                    if sp_track.album and sp_track.album != "Single":
                        yt_track.album = sp_track.album
                    if sp_track.year:
                        yt_track.year = sp_track.year
                    return yt_track
                return sp_track
        elif entity_type == "album":
            console.print("[yellow]Provided URL is a Spotify album. Use 'scout album <URL>' to download complete albums.[/yellow]")
            return None
        elif entity_type == "playlist":
            console.print("[yellow]Provided URL is a Spotify playlist. Use 'scout playlist <URL>' to download complete playlists.[/yellow]")
            return None

    # 2. Check if YouTube URL
    if "youtube.com" in query_or_url or "youtu.be" in query_or_url:
        import re
        v_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", query_or_url)
        if v_match:
            v_id = v_match.group(1)
            return Track(
                title=f"YouTube Track ({v_id})",
                artist="Unknown Artist",
                video_id=v_id,
                source_url=f"https://www.youtube.com/watch?v={v_id}",
            )

    # 3. Plain search query
    query = query_or_url.strip()
    # If "Artist - Title" format
    if " - " in query:
        parts = query.split(" - ", 1)
        artist_hint, title_hint = parts[0].strip(), parts[1].strip()
    else:
        artist_hint, title_hint = "", query

    with console.status(f"[bold green]Searching YouTube Music for '{query}'...[/bold green]"):
        results = ytm.search_tracks(query, limit=5)

    if not results:
        return None

    if len(results) == 1 or not interactive or not sys.stdin.isatty():
        return results[0]

    # Interactive choice table
    table = Table(title="Select Studio Track", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Artist", style="bold")
    table.add_column("Title", style="green")
    table.add_column("Album", style="dim")
    table.add_column("Duration", style="yellow")
    table.add_column("Studio", style="magenta")

    for idx, r in enumerate(results, 1):
        mins, secs = divmod(r.duration_seconds, 60)
        dur_str = f"{mins}:{secs:02d}" if r.duration_seconds else "--:--"
        studio_str = "✨ Official" if r.is_studio else "Video"
        table.add_row(str(idx), r.artist, r.title, r.album, dur_str, studio_str)

    console.print(table)
    choice = Prompt.ask("Choose track number", choices=[str(i) for i in range(1, len(results) + 1)], default="1")
    return results[int(choice) - 1]


def cmd_add(args, config: Config):
    render_banner()
    downloader = AudioDownloader(config=config)
    spotify = SpotifyProvider()
    ytm = YTMusicProvider()
    scanner = NavidromeScanner(config=config.navidrome)

    target_dir = Path(args.dir) if args.dir else config.general.music_dir

    track = resolve_track_from_input(args.query, spotify, ytm, interactive=not args.yes)
    if not track:
        console.print("[red]❌ Could not find or resolve track matching query.[/red]")
        sys.exit(1)
    force = getattr(args, "force", False)
    if not force:
        existing = downloader.is_track_already_present(track, target_dir)
        if existing:
            console.print(f"[yellow]✔ Track already exists in library:[/yellow] {existing} [dim](use --force to re-download)[/dim]")
            if config.navidrome.scan_on_download:
                scanner.trigger_scan()
            return

    console.print(f"[bold green]⬇ Downloading:[/bold green] [bold cyan]{track.display_name}[/bold cyan] [dim]({track.album})[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading studio audio & tagging ID3...", total=None)
        res = downloader.download_track(track, target_dir=target_dir, overwrite=force)
        progress.update(task, completed=100, total=100)

    if res.success:
        if res.already_exists:
            console.print(f"[bold yellow]✔ Already present at:[/bold yellow] {res.file_path}")
        else:
            console.print(f"[bold green]✔ Saved to:[/bold green] {res.file_path}")
        if config.navidrome.scan_on_download:
            scanner.trigger_scan()
        notify("🎯 Scout Download Complete", f"Added: {track.display_name}")
    else:
        console.print(f"[bold red]❌ Download failed:[/bold red] {res.error}")
        sys.exit(1)

def cmd_album(args, config: Config):
    render_banner()
    downloader = AudioDownloader(config=config)
    spotify = SpotifyProvider()
    ytm = YTMusicProvider()
    scanner = NavidromeScanner(config=config.navidrome)

    target_dir = Path(args.dir) if args.dir else config.general.music_dir

    album_obj: Optional[Album] = None

    if SpotifyProvider.is_spotify_url(args.query):
        with console.status("[bold green]Parsing Spotify album tracklist...[/bold green]"):
            album_obj = spotify.get_album(args.query)

    if not album_obj:
        with console.status(f"[bold green]Searching YouTube Music for album '{args.query}'...[/bold green]"):
            if " - " in args.query:
                parts = args.query.split(" - ", 1)
                album_obj = ytm.search_album(parts[0].strip(), parts[1].strip())
            else:
                album_obj = ytm.search_album("", args.query)

    if not album_obj or not album_obj.tracks:
        console.print("[red]❌ Could not find album or tracklist.[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[bold cyan]Album:[/bold cyan] {album_obj.title}\n"
        f"[bold cyan]Artist:[/bold cyan] {album_obj.artist}\n"
        f"[bold cyan]Tracks:[/bold cyan] {len(album_obj.tracks)} tracks\n"
        f"[bold cyan]Year:[/bold cyan] {album_obj.year or 'N/A'}",
        title="💿 Album Details",
        border_style="cyan"
    ))

    force = getattr(args, "force", False)
    success_count = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        main_task = progress.add_task(f"Downloading album ({len(album_obj.tracks)} tracks)", total=len(album_obj.tracks))

        for idx, t in enumerate(album_obj.tracks, 1):
            progress.update(main_task, description=f"[{idx}/{len(album_obj.tracks)}] {t.title}")

            if not force:
                existing = downloader.is_track_already_present(t, target_dir)
                if existing:
                    success_count += 1
                    progress.advance(main_task)
                    continue

            # Ensure video_id is resolved
            if not t.video_id:
                matched = ytm.search_track(t.artist, t.title, album=album_obj.title)
                if matched and matched.video_id:
                    t.video_id = matched.video_id
                    if not t.cover_url and matched.cover_url:
                        t.cover_url = matched.cover_url

            if album_obj.cover_url and not t.cover_url:
                t.cover_url = album_obj.cover_url
            t.album = album_obj.title
            t.album_artist = album_obj.artist
            t.year = album_obj.year

            res = downloader.download_track(t, target_dir=target_dir, overwrite=force)
            if res.success:
                success_count += 1
            progress.advance(main_task)

    console.print(f"[bold green]✔ Successfully processed {success_count}/{len(album_obj.tracks)} tracks![/bold green]")
    if config.navidrome.scan_on_download:
        scanner.trigger_scan()
    notify("💿 Album Download Complete", f"{album_obj.artist} - {album_obj.title} ({success_count} tracks)")


def cmd_playlist(args, config: Config):
    render_banner()
    downloader = AudioDownloader(config=config)
    spotify = SpotifyProvider()
    ytm = YTMusicProvider()
    scanner = NavidromeScanner(config=config.navidrome)
    playlist_obj: Optional[Playlist] = None

    if SpotifyProvider.is_spotify_url(args.query):
        with console.status("[bold green]Parsing Spotify playlist tracklist & metadata...[/bold green]"):
            playlist_obj = spotify.get_playlist(args.query)

    if not playlist_obj or not playlist_obj.tracks:
        console.print("[red]❌ Could not find or parse Spotify playlist.[/red]")
        sys.exit(1)

    from scout.core.downloader import sanitize_filename
    safe_name = sanitize_filename(playlist_obj.title) or "Spotify Playlist"

    # Default to dedicated playlist folder ~/Music/Playlists/<PlaylistName>/ to prevent music folder pollution
    if args.dir:
        target_dir = Path(args.dir)
    else:
        target_dir = config.general.music_dir / "Playlists" / safe_name

    target_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[bold cyan]Playlist:[/bold cyan] {playlist_obj.title}\n"
        f"[bold cyan]Description:[/bold cyan] {playlist_obj.description or 'N/A'}\n"
        f"[bold cyan]Tracks:[/bold cyan] {len(playlist_obj.tracks)} tracks\n"
        f"[bold cyan]Target Dir:[/bold cyan] {target_dir}",
        title="🎵 Spotify Playlist Details",
        border_style="cyan"
    ))
    force = getattr(args, "force", False)
    processed_count = 0
    downloaded_paths: list[tuple[Track, Path]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        main_task = progress.add_task(f"Processing playlist ({len(playlist_obj.tracks)} tracks)", total=len(playlist_obj.tracks))

        for idx, t in enumerate(playlist_obj.tracks, 1):
            progress.update(main_task, description=f"[{idx}/{len(playlist_obj.tracks)}] {t.display_name}")

            # Collision / Duplicate check: If track exists on disk/library and not forcing
            if not force:
                existing = downloader.is_track_already_present(t, target_dir)
                if existing:
                    processed_count += 1
                    downloaded_paths.append((t, existing))
                    progress.advance(main_task)
                    continue

            # Ensure video_id is resolved
            if not t.video_id:
                matched = ytm.search_track(t.artist, t.title)
                if matched and matched.video_id:
                    t.video_id = matched.video_id
                    if not t.cover_url and matched.cover_url:
                        t.cover_url = matched.cover_url
                    if matched.album and matched.album != "Single" and (not t.album or t.album == "Single"):
                        t.album = matched.album
                    if matched.year and not t.year:
                        t.year = matched.year

            res = downloader.download_track(t, target_dir=target_dir, overwrite=force)
            if res.success and res.file_path:
                processed_count += 1
                downloaded_paths.append((t, res.file_path))
            progress.advance(main_task)

    console.print(f"[bold green]✔ Successfully processed {processed_count}/{len(playlist_obj.tracks)} tracks![/bold green]")

    # Generate .m3u8 playlist file if requested
    no_m3u = getattr(args, "no_m3u", False)
    if not no_m3u and downloaded_paths:
        playlists_dir = config.general.music_dir / "Playlists"
        playlists_dir.mkdir(parents=True, exist_ok=True)
        m3u8_path = playlists_dir / f"{safe_name}.m3u8"

        with open(m3u8_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            f.write(f"#PLAYLIST:{playlist_obj.title}\n")
            for trk, pth in downloaded_paths:
                f.write(f"#EXTINF:{trk.duration_seconds},{trk.display_name}\n")
                f.write(f"{pth.resolve()}\n")

        console.print(f"[bold cyan]📄 Created Playlist File:[/bold cyan] {m3u8_path}")
    if config.navidrome.scan_on_download:
        scanner.trigger_scan()
    notify("🎵 Playlist Download Complete", f"{playlist_obj.title} ({processed_count} tracks)")

def cmd_artist(args, config: Config):
    render_banner()
    ytm = YTMusicProvider()
    with console.status(f"[bold green]Searching discography for '{args.artist}'...[/bold green]"):
        artist_obj = ytm.search_artist(args.artist)

    if not artist_obj:
        console.print(f"[red]❌ Artist '{args.artist}' not found.[/red]")
        sys.exit(1)

    table = Table(title=f"Discography: {artist_obj.name}")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Type", style="magenta")
    table.add_column("Title", style="bold green")
    table.add_column("Year", style="yellow")

    items = []
    for a in artist_obj.albums:
        items.append(("Album", a))
    for s in artist_obj.singles:
        items.append(("Single / EP", s))

    if not items:
        console.print("[yellow]No albums or singles found for this artist.[/yellow]")
        return

    for idx, (itype, album) in enumerate(items, 1):
        table.add_row(str(idx), itype, album.title, album.year or "--")

    console.print(table)
    choice = Prompt.ask("Choose album number to download (or 'all')", default="1")
    if choice.lower() == "all":
        for _, alb in items:
            cmd_album(argparse.Namespace(query=f"{artist_obj.name} - {alb.title}", dir=args.dir), config)
    else:
        idx = int(choice) - 1
        if 0 <= idx < len(items):
            selected = items[idx][1]
            cmd_album(argparse.Namespace(query=f"{artist_obj.name} - {selected.title}", dir=args.dir), config)


def cmd_radio(args, config: Config):
    render_banner()
    downloader = AudioDownloader(config=config)
    spotify = SpotifyProvider()
    ytm = YTMusicProvider()
    lastfm = LastFMProvider(config=config)
    scanner = NavidromeScanner(config=config.navidrome)

    seed_track = resolve_track_from_input(args.query, spotify, ytm, interactive=False)
    if not seed_track:
        console.print("[red]❌ Seed track not found.[/red]")
        sys.exit(1)

    console.print(f"[bold cyan]🎯 Seed Track:[/bold cyan] {seed_track.display_name}")

    with console.status(f"[bold green]Fetching recommendations for {seed_track.display_name}...[/bold green]"):
        similar = lastfm.get_similar_tracks(seed_track.artist, seed_track.title, limit=args.count)
        if not similar and seed_track.video_id:
            radio_tracks = ytm.get_radio_tracks(seed_track.video_id, limit=args.count)
            for r in radio_tracks:
                from scout.core.models import DiscoveryCandidate
                similar.append(DiscoveryCandidate(track=r, similarity_score=0.8, seed_track=seed_track.display_name))

    if not similar:
        console.print("[red]❌ No recommendations found.[/red]")
        sys.exit(1)

    table = Table(title=f"Discovery Radio ({len(similar)} Tracks)")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Artist", style="bold")
    table.add_column("Title", style="green")
    table.add_column("Match", style="yellow")

    for idx, c in enumerate(similar, 1):
        match_pct = f"{int(c.similarity_score * 100)}%" if c.similarity_score <= 1.0 else "Nexus"
        table.add_row(str(idx), c.track.artist, c.track.title, match_pct)

    console.print(table)

    target_dir = Path(args.dir) if args.dir else config.general.discovery_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        main_task = progress.add_task("Downloading discovery radio...", total=len(similar))
        force = getattr(args, "force", False)
        for idx, cand in enumerate(similar, 1):
            progress.update(main_task, description=f"[{idx}/{len(similar)}] {cand.track.display_name}")
            if not force:
                existing = downloader.is_track_already_present(cand.track, target_dir)
                if existing:
                    progress.advance(main_task)
                    continue
            matched = ytm.search_track(cand.track.artist, cand.track.title)
            if matched and matched.video_id:
                res = downloader.download_track(matched, target_dir=target_dir, overwrite=force)
                if res.success and not res.already_exists:
                    downloaded.append(matched)
            progress.advance(main_task)
    if downloaded:
        try:
            from scout.core.downloader import sanitize_filename
            new_pl_file = config.general.music_dir / "🆕 Scout Yeni Keşifler.m3u8"
            new_lines = ["#EXTM3U", "#PLAYLIST:🆕 Scout Yeni Keşifler", ""]
            for dt in downloaded:
                clean_art = sanitize_filename(dt.artist or "Unknown Artist")
                clean_tit = sanitize_filename(dt.title or "Unknown Title")
                f = config.general.discovery_dir / f"{clean_art} - {clean_tit}.mp3"
                if f.exists():
                    try:
                        rel_path = f.relative_to(config.general.music_dir)
                        new_lines.append(f"#EXTINF:{dt.duration_seconds},{dt.display_name}")
                        new_lines.append(str(rel_path))
                    except Exception:
                        pass
            with open(new_pl_file, "w", encoding="utf-8") as pf:
                pf.write("\n".join(new_lines))
        except Exception:
            pass

    try:
        mix_pl_file = config.general.music_dir / "✨ Scout Mix.m3u8"
        discovery_tracks = list(config.general.discovery_dir.glob("*.mp3")) + list(config.general.discovery_dir.glob("*.flac"))
        discovery_tracks.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        m3u_lines = ["#EXTM3U", "#PLAYLIST:✨ Scout Mix", ""]
        for f in discovery_tracks:
            try:
                rel_path = f.relative_to(config.general.music_dir)
                m3u_lines.append(f"#EXTINF:-1,{f.stem}")
                m3u_lines.append(str(rel_path))
            except Exception:
                pass
        with open(mix_pl_file, "w", encoding="utf-8") as pf:
            pf.write("\n".join(m3u_lines))
    except Exception:
        pass
    console.print(f"[bold green]✔ Added {len(downloaded)} new discovery tracks to {target_dir}![/bold green]")
    if config.navidrome.scan_on_download:
        scanner.trigger_scan()
    notify("✨ Discovery Radio Complete", f"Downloaded {len(downloaded)} tracks for {seed_track.display_name}")


def cmd_mix(args, config: Config):
    render_banner()
    history = HistoryStore()
    dna_engine = PlaylistDNAEngine(config=config, history_store=history)
    subsonic = SubsonicClient(config=config.subsonic)
    navidrome = NavidromeScanner(config=config.navidrome)
    downloader = AudioDownloader(config=config, history_store=history)

    seeds: list[Track] = []

    # 1. Custom seeds argument
    if args.seeds:
        for s in args.seeds.split(","):
            s = s.strip()
            if " - " in s:
                p = s.split(" - ", 1)
                seeds.append(Track(artist=p[0].strip(), title=p[1].strip()))
            elif s:
                seeds.append(Track(artist="Unknown", title=s))

    # 2. Subsonic seed playlist
    elif subsonic.is_enabled:
        playlist_name = args.playlist or config.subsonic.seed_playlist
        pl = subsonic.get_playlist_by_name(playlist_name)
        if pl:
            with console.status(f"[bold green]Fetching seeds from Subsonic playlist '{playlist_name}'...[/bold green]"):
                seeds = subsonic.get_playlist_tracks(pl["id"])

    # 3. Navidrome starred fallback
    if not seeds:
        with console.status("[bold green]Reading starred tracks from Navidrome...[/bold green]"):
            seeds = navidrome.get_starred_tracks()

    if not seeds:
        console.print("[red]❌ No seeds found! Provide --seeds 'Artist - Title,...' or star tracks in Navidrome/Subsonic.[/red]")
        sys.exit(1)
    console.print(f"[bold cyan]🧬 Loaded {len(seeds)} seed tracks from your favorites.[/bold cyan]")

    # Sync deleted files to negative blacklist
    active_keys = {s.clean_key for s in seeds}
    purged = history.sync_deleted_files_to_blacklist(active_seed_keys=active_keys)
    if purged:
        console.print(f"[dim]🗑️ Synced {len(purged)} deleted tracks to blacklist (Scout will never re-download them).[/dim]")
    def progress_cb(msg: str, current: int, total: int):
        console.print(f"[dim]• {msg}[/dim]")

    candidates = dna_engine.generate_mix(
        seeds=seeds,
        target_count=args.count,
        max_per_artist=args.max_per_artist,
        progress_callback=progress_cb,
    )

    if not candidates:
        console.print("[yellow]No candidates generated. Check network connection or seed validity.[/yellow]")
        return

    table = Table(title=f"✨ Generated Scout Mix ({len(candidates)} Tracks)")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Artist", style="bold")
    table.add_column("Title", style="green")
    table.add_column("Source / Reason", style="dim")

    for idx, c in enumerate(candidates, 1):
        table.add_row(str(idx), c.track.artist, c.track.title, c.reason)

    console.print(table)

    target_dir = Path(args.dir) if args.dir else config.general.discovery_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        main_task = progress.add_task("Archiving Scout Mix...", total=len(candidates))
        force = getattr(args, "force", False)
        for idx, cand in enumerate(candidates, 1):
            progress.update(main_task, description=f"[{idx}/{len(candidates)}] {cand.track.display_name}")
            res = downloader.download_track(cand.track, target_dir=target_dir, overwrite=force)
            if res.success and not res.already_exists:
                downloaded.append(cand.track)
            progress.advance(main_task)
    # 1. Generate / update '🆕 Scout Yeni Keşifler.m3u8' (SADECE bu oturumda yeni inen ve diskte var olan parçalar)
    if downloaded:
        try:
            from scout.core.downloader import sanitize_filename
            new_pl_file = config.general.music_dir / "🆕 Scout Yeni Keşifler.m3u8"
            new_lines = ["#EXTM3U", "#PLAYLIST:🆕 Scout Yeni Keşifler", ""]
            for dt in downloaded:
                clean_art = sanitize_filename(dt.artist or "Unknown Artist")
                clean_tit = sanitize_filename(dt.title or "Unknown Title")
                f = config.general.discovery_dir / f"{clean_art} - {clean_tit}.mp3"
                if not f.exists():
                    f = config.general.discovery_dir / f"{clean_art} - {clean_tit}.flac"
                if f.exists():
                    try:
                        rel_path = f.relative_to(config.general.music_dir)
                        new_lines.append(f"#EXTINF:{dt.duration_seconds},{dt.display_name}")
                        new_lines.append(str(rel_path))
                    except Exception:
                        pass
            with open(new_pl_file, "w", encoding="utf-8") as pf:
                pf.write("\n".join(new_lines))
            console.print(f"[bold cyan]🆕 Yeni Keşifler Çalma Listesi Güncellendi:[/bold cyan] [dim]{new_pl_file.name} ({len(downloaded)} yeni parça)[/dim]")
        except Exception:
            pass

    # 2. Prune and update '✨ Scout Mix.m3u8' (SADECE diskte fiziksel olarak VAR OLAN keşif parçaları)
    try:
        mix_pl_file = config.general.music_dir / "✨ Scout Mix.m3u8"
        # Scan only files that physically exist right now
        discovery_tracks = [
            f for f in (list(config.general.discovery_dir.glob("*.mp3")) + list(config.general.discovery_dir.glob("*.flac")))
            if f.is_file() and f.stat().st_size > 1000
        ]
        # Sort by modification time so newest discoveries are at the top
        discovery_tracks.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        m3u_lines = ["#EXTM3U", "#PLAYLIST:✨ Scout Mix", ""]
        for f in discovery_tracks:
            try:
                rel_path = f.relative_to(config.general.music_dir)
                m3u_lines.append(f"#EXTINF:-1,{f.stem}")
                m3u_lines.append(str(rel_path))
            except Exception:
                pass

        with open(mix_pl_file, "w", encoding="utf-8") as pf:
            pf.write("\n".join(m3u_lines))
        console.print(f"[dim]🎵 Genel Keşif Miksi Güncellendi: {mix_pl_file.name} (Diskteki {len(discovery_tracks)} canlı parça)[/dim]")
    except Exception:
        pass
    console.print(f"[bold green]✔ Added {len(downloaded)} tracks to Discovery library![/bold green]")
    if config.navidrome.scan_on_download:
        navidrome.trigger_scan()
    notify("✨ Scout Mix Generated", f"Successfully discovered and downloaded {len(downloaded)} tracks!")


def cmd_mpris(args, config: Config):
    render_banner()
    track = get_current_playing_track()
    if not track:
        console.print("[red]❌ No active media player found via MPRIS (Feishin, Spotify, etc.)[/red]")
        sys.exit(1)

    console.print(f"[bold green]🎵 Currently Playing:[/bold green] [bold cyan]{track.display_name}[/bold cyan] [dim]({track.album})[/dim]")
    cmd_radio(argparse.Namespace(query=f"{track.artist} - {track.title}", count=args.count, dir=args.dir, force=getattr(args, "force", False)), config)


def cmd_stats(args, config: Config):
    render_banner()
    history = HistoryStore()
    stats = history.get_stats()
    recent = history.get_recent_downloads(limit=10)

    console.print(Panel(
        f"[bold cyan]Total Downloaded Tracks:[/bold cyan] {stats['total_downloads']}\n"
        f"[bold cyan]Total Processed Seeds:[/bold cyan] {stats['total_seeds']}\n"
        f"[bold cyan]Blacklisted Items:[/bold cyan] {stats['total_blacklist']}\n"
        f"[bold cyan]Music Directory:[/bold cyan] {config.general.music_dir}\n"
        f"[bold cyan]Discovery Directory:[/bold cyan] {config.general.discovery_dir}\n"
        f"[bold cyan]Audio Format:[/bold cyan] {config.general.audio_format.upper()} ({config.general.bitrate})",
        title="📊 Scout Statistics & Library Health",
        border_style="cyan",
    ))

    if recent:
        table = Table(title="Recent 10 Downloads")
        table.add_column("#", style="cyan", width=4)
        table.add_column("Artist", style="bold")
        table.add_column("Title", style="green")
        table.add_column("Album", style="dim")
        table.add_column("Format", style="yellow")
        table.add_column("Date", style="dim")

        for idx, r in enumerate(recent, 1):
            table.add_row(str(idx), r["artist"], r["title"], r.get("album") or "Single", r.get("audio_format", "mp3"), str(r.get("date_added", ""))[:19])

def cmd_upgrade(args, config: Config):
    import concurrent.futures
    import threading
    import shutil
    from mutagen.mp3 import MP3

    render_banner()
    downloader = AudioDownloader(config=config)
    scanner = NavidromeScanner(config=config.navidrome)
    history = HistoryStore()

    target_dir = Path(args.dir) if args.dir else config.general.music_dir
    mp3_files = list(target_dir.rglob("*.mp3"))

    if not mp3_files:
        console.print("[yellow]Kütüphanede yükseltilecek MP3 dosyası bulunamadı.[/yellow]")
        return

    concurrency = getattr(args, "concurrency", 3) or 3
    concurrency = max(1, min(6, concurrency))

    console.print(f"[bold cyan]🔍 Kütüphanede {len(mp3_files)} MP3 bulundu. Soulseek Eşzamanlı ({concurrency} Kanal) FLAC Yükseltmesi Başlatılıyor...[/bold cyan]\n")

    upgraded_count = 0
    kept_count = 0
    lock = threading.Lock()

    track_items = []
    for mp3_path in mp3_files:
        artist, title, album = "", "", ""
        try:
            audio = MP3(mp3_path)
            if audio.tags:
                title = str(audio.tags.get("TIT2", ""))
                artist = str(audio.tags.get("TPE1", ""))
                album = str(audio.tags.get("TALB", ""))
        except Exception:
            pass

        if not artist or not title:
            stem = mp3_path.stem
            if " - " in stem:
                parts = stem.split(" - ", 1)
                artist, title = parts[0].strip(), parts[1].strip()
            else:
                artist = mp3_path.parent.name
                title = stem

        track = Track(artist=artist, title=title, album=album or "Single")
        track_items.append((mp3_path, track))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task(f"[bold green]Genel İlerleme (Toplam {len(track_items)} Parça)[/bold green]", total=len(track_items))

        def process_track(item):
            nonlocal upgraded_count, kept_count
            mp3_path, track = item
            display = f"{track.artist} - {track.title}"

            worker_task = progress.add_task(
                f"  [dim]•[/dim] [cyan]{display[:30]}[/cyan] [yellow]🔍 Aranıyor...[/yellow]",
                total=100,
                completed=10,
            )

            def on_progress(curr_bytes: int, _):
                curr_mb = curr_bytes / (1024 * 1024)
                pct = min(92, int(15 + (curr_mb / 32.0) * 75))
                progress.update(
                    worker_task,
                    completed=pct,
                    description=f"  [dim]•[/dim] [cyan]{display[:28]}[/cyan] [blue]⬇ FLAC İndiriliyor ({curr_mb:.1f} MB)[/blue]",
                )

            try:
                tmp_flac = downloader.soulseek.download_flac(track, progress_hook=on_progress)

                if tmp_flac and tmp_flac.exists() and tmp_flac.stat().st_size > 1024 * 1024:
                    size_mb = tmp_flac.stat().st_size / (1024 * 1024)
                    progress.update(
                        worker_task,
                        completed=96,
                        description=f"  [dim]•[/dim] [cyan]{display[:28]}[/cyan] [magenta]🏷️ Etiketleniyor ({size_mb:.1f} MB)...[/magenta]",
                    )
                    flac_dest = mp3_path.with_suffix(".flac")
                    downloader.tag_file(tmp_flac, track, None)
                    flac_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(tmp_flac), str(flac_dest))

                    if flac_dest.exists() and flac_dest.stat().st_size > 1024 * 1024:
                        mp3_path.unlink(missing_ok=True)
                        with lock:
                            history.record_download(
                                track=track,
                                file_path=flac_dest,
                                source_url="soulseek://p2p",
                                audio_format="flac",
                                bitrate="Lossless FLAC",
                            )
                            upgraded_count += 1
                        progress.update(
                            worker_task,
                            completed=100,
                            description=f"  [dim]•[/dim] [green]✔ Yükseltildi:[/green] [cyan]{display[:28]}[/cyan] [bold cyan]({size_mb:.1f} MB)[/bold cyan]",
                        )
                else:
                    with lock:
                        kept_count += 1
                    progress.update(
                        worker_task,
                        completed=100,
                        description=f"  [dim]•[/dim] [yellow]ℹ MP3 Korundu:[/yellow] [dim]{display[:28]}[/dim]",
                    )
            except Exception:
                with lock:
                    kept_count += 1
                progress.update(
                    worker_task,
                    completed=100,
                    description=f"  [dim]•[/dim] [yellow]ℹ MP3 Korundu:[/yellow] [dim]{display[:28]}[/dim]",
                )
            finally:
                with lock:
                    progress.advance(overall_task)
                time.sleep(1.0)
                progress.remove_task(worker_task)
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            list(executor.map(process_track, track_items))

    console.print(f"\n[bold green]✔ Kütüphane FLAC Yükseltmesi Tamamlandı![/bold green]")
    console.print(f"  • Orijinal FLAC'e Yükseltilen: [bold cyan]{upgraded_count}[/bold cyan]")
    console.print(f"  • Korunan MP3 (Ağda bulunmayan): [bold yellow]{kept_count}[/bold yellow]")

    if config.navidrome.scan_on_download:
        scanner.trigger_scan()
    notify("✨ Scout FLAC Upgrade Complete", f"Upgraded {upgraded_count} tracks to lossless FLAC!")


def cmd_watch(args, config: Config):
    render_banner()
    console.print("[bold green]👁️ Scout Watcher Started...[/bold green] [dim](Press Ctrl+C to stop)[/dim]")
    history = HistoryStore()
    navidrome = NavidromeScanner(config=config.navidrome)
    downloader = AudioDownloader(config=config)
    dna_engine = PlaylistDNAEngine(config=config, history_store=history)

    interval = getattr(args, "interval", 30)

    while True:
        try:
            starred = navidrome.get_starred_tracks()
            for s in starred:
                if not history.is_seed_processed(s.artist, s.title):
                    console.print(f"[bold cyan]🌟 New Starred Seed Detected:[/bold cyan] {s.display_name}")
                    history.record_seed(s.artist, s.title, reason="navidrome_starred_watch")
                    candidates = dna_engine.generate_mix([s], target_count=5)
                    for cand in candidates:
                        res = downloader.download_track(cand.track, target_dir=config.general.discovery_dir)
                        if res.success:
                            console.print(f"[green]  + Downloaded:[/green] {cand.track.display_name}")
                    if config.navidrome.scan_on_download:
                        navidrome.trigger_scan()
                    notify("✨ New Starred Discovery", f"Discovered tracks for {s.display_name}")

            time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]Watcher stopped.[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error in watcher loop:[/red] {e}")
            time.sleep(interval)


def cmd_tui(args, config: Config):
    from scout.tui.app import ScoutApp
    app = ScoutApp()
    app.run()


def main():
    parser = argparse.ArgumentParser(
        prog="scout",
        description="🎯 Scout: Universal Music Discovery & Archiving Engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # add
    p_add = subparsers.add_parser("add", help="Download single track from Spotify URL, YouTube URL, or query")
    p_add.add_argument("query", help="Track URL or 'Artist - Title'")
    p_add.add_argument("--dir", help="Custom target directory")
    p_add.add_argument("-y", "--yes", action="store_true", help="Auto-select top match without interactive prompt")
    p_add.add_argument("-f", "--force", action="store_true", help="Force overwrite even if track exists")

    # album
    p_album = subparsers.add_parser("album", help="Download complete album into {Artist}/{Album}/")
    p_album.add_argument("query", help="Album URL or 'Artist - Album'")
    p_album.add_argument("--dir", help="Custom target directory")
    p_album.add_argument("-f", "--force", action="store_true", help="Force re-download existing album tracks")


    # playlist
    p_playlist = subparsers.add_parser("playlist", help="Download complete playlist from Spotify URL and generate .m3u8")
    p_playlist.add_argument("query", help="Playlist URL or Spotify playlist link")
    p_playlist.add_argument("--dir", help="Custom target directory")
    p_playlist.add_argument("-f", "--force", action="store_true", help="Force re-download existing playlist tracks")
    p_playlist.add_argument("--no-m3u", action="store_true", help="Skip generating .m3u8 playlist file")
    # artist
    p_artist = subparsers.add_parser("artist", help="List and download artist discography albums")
    p_artist.add_argument("artist", help="Artist Name")
    p_artist.add_argument("--dir", help="Custom target directory")
    p_artist.add_argument("-f", "--force", action="store_true", help="Force re-download existing tracks")

    # radio
    p_radio = subparsers.add_parser("radio", help="Download track + 10 similar discovery tracks")
    p_radio.add_argument("query", help="Seed Track URL or 'Artist - Title'")
    p_radio.add_argument("--count", type=int, default=10, help="Number of similar tracks")
    p_radio.add_argument("--dir", help="Custom target directory")
    p_radio.add_argument("-f", "--force", action="store_true", help="Force re-download existing discovery tracks")

    # mix
    p_mix = subparsers.add_parser("mix", help="Run Playlist DNA Engine on seeds and generate discovery mix")
    p_mix.add_argument("--playlist", help="Subsonic seed playlist name")
    p_mix.add_argument("--seeds", help="Comma-separated seed tracks ('Artist - Title,Artist - Title')")
    p_mix.add_argument("--count", type=int, default=20, help="Number of discovery tracks")
    p_mix.add_argument("--max-per-artist", type=int, default=2, help="Max tracks per artist constraint")
    p_mix.add_argument("--dir", help="Custom target directory")
    p_mix.add_argument("-f", "--force", action="store_true", help="Force re-download existing discovery tracks")

    # mpris
    p_mpris = subparsers.add_parser("mpris", help="Instant discovery radio from currently playing song in MPRIS")
    p_mpris.add_argument("--count", type=int, default=10, help="Number of discovery tracks")
    p_mpris.add_argument("--dir", help="Custom target directory")
    p_mpris.add_argument("-f", "--force", action="store_true", help="Force re-download existing tracks")
    p_watch = subparsers.add_parser("watch", help="Background watcher daemon for starred songs & seed changes")
    p_watch.add_argument("--interval", type=int, default=30, help="Check interval in seconds")
    p_upgrade = subparsers.add_parser("upgrade", help="Batch upgrade existing MP3 tracks in library to Soulseek Lossless FLAC")
    p_upgrade.add_argument("--dir", help="Custom target directory to scan")
    p_upgrade.add_argument("-c", "--concurrency", type=int, default=3, help="Number of concurrent download channels (default: 3)")

    # stats
    subparsers.add_parser("stats", help="View archive statistics and recent downloads")

    # tui
    subparsers.add_parser("tui", help="Launch interactive full-screen Terminal User Interface (TUI)")

    args = parser.parse_args()
    config = load_config()

    if args.command is None:
        # Default behavior: run instant discovery mix based on active favorites!
        default_args = argparse.Namespace(
            playlist=None,
            seeds=None,
            count=10,
            max_per_artist=2,
            dir=None,
            force=False,
        )
        cmd_mix(default_args, config)
    elif args.command == "add":
        cmd_add(args, config)
    elif args.command == "album":
        cmd_album(args, config)
    elif args.command == "playlist":
        cmd_playlist(args, config)
    elif args.command == "artist":
        cmd_artist(args, config)
    elif args.command == "radio":
        cmd_radio(args, config)
    elif args.command == "mix":
        cmd_mix(args, config)
    elif args.command == "mpris":
        cmd_mpris(args, config)
    elif args.command == "watch":
        cmd_watch(args, config)
    elif args.command == "stats":
        cmd_stats(args, config)
    elif args.command == "tui":
        cmd_tui(args, config)
    elif args.command == "upgrade":
        cmd_upgrade(args, config)


if __name__ == "__main__":
    main()
