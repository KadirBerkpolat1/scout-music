"""Interactive full-screen Textual Terminal User Interface for Scout."""

import threading
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RadioSet,
    RadioButton,
    Static,
    TabbedContent,
    TabPane,
)

from scout.core.config import Config, load_config
from scout.core.dedupe import HistoryStore
from scout.core.downloader import AudioDownloader
from scout.core.models import DiscoveryCandidate, Track
from scout.dna.engine import PlaylistDNAEngine
from scout.integrations.navidrome import NavidromeScanner
from scout.integrations.notifier import notify
from scout.providers.spotify import SpotifyProvider
from scout.providers.ytmusic import YTMusicProvider


class ScoutApp(App):
    CSS = """
    Screen {
        background: #0f141c;
        color: #e6edf3;
    }

    Header {
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        padding: 1 2;
    }

    .section-title {
        font-size: 100%;
        text-style: bold;
        color: #58a6ff;
        margin-bottom: 1;
    }

    .input-bar {
        height: auto;
        margin-bottom: 1;
    }

    Input {
        border: tall #30363d;
        background: #161b22;
        color: #f0f6fc;
        margin-right: 1;
    }

    Input:focus {
        border: tall #58a6ff;
    }

    Button {
        background: #238636;
        color: #ffffff;
        border: none;
        text-style: bold;
    }

    Button:hover {
        background: #2ea043;
    }

    Button.-secondary {
        background: #30363d;
        color: #c9d1d9;
    }

    Button.-secondary:hover {
        background: #3c444d;
    }

    DataTable {
        height: 1fr;
        border: tall #30363d;
        background: #0d1117;
    }

    .stat-card {
        background: #161b22;
        border: tall #30363d;
        padding: 1;
        margin: 0 1 1 0;
        text-align: center;
    }

    .stat-number {
        text-style: bold;
        color: #58a6ff;
        font-size: 140%;
    }

    .stat-label {
        color: #8b949e;
    }

    .status-msg {
        color: #7ee787;
        margin-top: 1;
        text-style: italic;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f5", "refresh_data", "Refresh"),
    ]

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.history = HistoryStore()
        self.ytm = YTMusicProvider()
        self.spotify = SpotifyProvider()
        self.downloader = AudioDownloader(config=self.config, history_store=self.history)
        self.dna_engine = PlaylistDNAEngine(config=self.config, history_store=self.history)
        self.navidrome = NavidromeScanner(config=self.config.navidrome)

        self.search_results: list[Track] = []
        self.mix_candidates: list[DiscoveryCandidate] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab_search"):
            # Tab 1: Search & Download
            with TabPane("🔍 Search & Download", id="tab_search"):
                yield Label("Search Tracks or Paste Spotify URL", classes="section-title")
                with Horizontal(classes="input-bar"):
                    yield Input(placeholder="e.g. Daft Punk - Get Lucky or Spotify link...", id="inp_search")
                    yield Button("Search", id="btn_search")
                yield DataTable(id="dt_search")
                with Horizontal():
                    yield Button("Download Selected Track", id="btn_download_selected")
                    yield Label("", id="lbl_search_status", classes="status-msg")

            # Tab 2: Discovery Station (DNA Engine)
            with TabPane("🧬 Discovery Station (DNA)", id="tab_dna"):
                yield Label("Playlist DNA Discovery Generator", classes="section-title")
                with Horizontal(classes="input-bar"):
                    yield Input(placeholder="Seed tracks (e.g. Eve - Underdog, Ado - Show) or leave blank for Navidrome starred", id="inp_dna_seeds")
                    yield Button("Generate Mix", id="btn_generate_dna")
                with Horizontal(classes="input-bar"):
                    yield Input(value="20", placeholder="Count (e.g. 20)", id="inp_dna_count")
                    yield Input(value="2", placeholder="Max per artist (e.g. 2)", id="inp_dna_max_artist")
                yield DataTable(id="dt_dna")
                with Horizontal():
                    yield Button("Download All Mix Tracks", id="btn_download_mix")
                    yield Label("", id="lbl_dna_status", classes="status-msg")

            # Tab 3: History & Archive
            with TabPane("📊 History & Stats", id="tab_history"):
                yield Label("Library Archive & History", classes="section-title")
                with Horizontal():
                    with Container(classes="stat-card"):
                        yield Label("0", id="stat_downloads", classes="stat-number")
                        yield Label("Downloaded Tracks", classes="stat-label")
                    with Container(classes="stat-card"):
                        yield Label("0", id="stat_seeds", classes="stat-number")
                        yield Label("Processed Seeds", classes="stat-label")
                    with Container(classes="stat-card"):
                        yield Label("0", id="stat_blacklist", classes="stat-number")
                        yield Label("Blacklisted Items", classes="stat-label")
                yield DataTable(id="dt_history")

            # Tab 4: Settings
            with TabPane("⚙️ Settings", id="tab_settings"):
                yield Label("Scout Engine Configuration", classes="section-title")
                with VerticalScroll():
                    yield Label("Music Directory:")
                    yield Input(value=str(self.config.general.music_dir), id="inp_cfg_music_dir")
                    yield Label("Discovery Directory:")
                    yield Input(value=str(self.config.general.discovery_dir), id="inp_cfg_disc_dir")
                    yield Label("Audio Format (mp3, flac, opus):")
                    yield Input(value=str(self.config.general.audio_format), id="inp_cfg_format")
                    yield Label("Bitrate (e.g. 320k):")
                    yield Input(value=str(self.config.general.bitrate), id="inp_cfg_bitrate")
                    yield Label("Last.fm API Key:")
                    yield Input(value=str(self.config.lastfm.api_key), id="inp_cfg_lastfm")
                    yield Label("Subsonic URL:")
                    yield Input(value=str(self.config.subsonic.url), id="inp_cfg_sub_url")
                    yield Label("Subsonic Username:")
                    yield Input(value=str(self.config.subsonic.username), id="inp_cfg_sub_user")
                    with Horizontal():
                        yield Button("Save Configuration", id="btn_save_config")
                        yield Label("", id="lbl_settings_status", classes="status-msg")

        yield Footer()

    def on_mount(self) -> None:
        # Initialize DataTables
        dt_search = self.query_one("#dt_search", DataTable)
        dt_search.cursor_type = "row"
        dt_search.add_columns("#", "Artist", "Title", "Album", "Duration", "Studio")

        dt_dna = self.query_one("#dt_dna", DataTable)
        dt_dna.cursor_type = "row"
        dt_dna.add_columns("#", "Artist", "Title", "Match Score", "Reason / Nexus")

        dt_history = self.query_one("#dt_history", DataTable)
        dt_history.cursor_type = "row"
        dt_history.add_columns("#", "Artist", "Title", "Album", "Format", "Date Added")

        self.refresh_stats()

    def action_refresh_data(self) -> None:
        self.refresh_stats()

    def refresh_stats(self) -> None:
        stats = self.history.get_stats()
        self.query_one("#stat_downloads", Label).update(str(stats["total_downloads"]))
        self.query_one("#stat_seeds", Label).update(str(stats["total_seeds"]))
        self.query_one("#stat_blacklist", Label).update(str(stats["total_blacklist"]))

        recent = self.history.get_recent_downloads(limit=50)
        dt_history = self.query_one("#dt_history", DataTable)
        dt_history.clear()
        for idx, r in enumerate(recent, 1):
            dt_history.add_row(
                str(idx),
                r["artist"],
                r["title"],
                r.get("album") or "Single",
                r.get("audio_format", "mp3"),
                str(r.get("date_added", ""))[:19],
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn_search":
            self.perform_search()
        elif btn_id == "btn_download_selected":
            self.download_selected_search_track()
        elif btn_id == "btn_generate_dna":
            self.generate_dna_mix()
        elif btn_id == "btn_download_mix":
            self.download_all_mix_tracks()
        elif btn_id == "btn_save_config":
            self.save_settings()

    @work(exclusive=True, thread=True)
    def perform_search(self) -> None:
        query = self.query_one("#inp_search", Input).value.strip()
        if not query:
            return

        self.app.call_from_thread(self.query_one("#lbl_search_status", Label).update, "Searching...")

        results: list[Track] = []
        if SpotifyProvider.is_spotify_url(query):
            sp_track = self.spotify.get_track(query)
            if sp_track:
                yt_track = self.ytm.search_track(sp_track.artist, sp_track.title, album=sp_track.album)
                if yt_track:
                    if sp_track.cover_url:
                        yt_track.cover_url = sp_track.cover_url
                    results.append(yt_track)
                else:
                    results.append(sp_track)
        else:
            results = self.ytm.search_tracks(query, limit=15)

        self.search_results = results

        def update_ui():
            dt = self.query_one("#dt_search", DataTable)
            dt.clear()
            for idx, r in enumerate(results, 1):
                mins, secs = divmod(r.duration_seconds, 60)
                dur_str = f"{mins}:{secs:02d}" if r.duration_seconds else "--:--"
                studio_str = "✨ Official" if r.is_studio else "Video"
                dt.add_row(str(idx), r.artist, r.title, r.album, dur_str, studio_str)
            self.query_one("#lbl_search_status", Label).update(f"Found {len(results)} results")

        self.app.call_from_thread(update_ui)

    @work(exclusive=True, thread=True)
    def download_selected_search_track(self) -> None:
        dt = self.query_one("#dt_search", DataTable)
        if dt.cursor_row is None or not self.search_results:
            self.app.call_from_thread(self.query_one("#lbl_search_status", Label).update, "No track selected.")
            return

        row_idx = dt.cursor_row
        if 0 <= row_idx < len(self.search_results):
            track = self.search_results[row_idx]
            self.app.call_from_thread(
                self.query_one("#lbl_search_status", Label).update,
                f"Downloading {track.display_name}...",
            )
            res = self.downloader.download_track(track)
            if res.success:
                self.app.call_from_thread(
                    self.query_one("#lbl_search_status", Label).update,
                    f"✔ Saved: {track.display_name}",
                )
                self.app.call_from_thread(self.refresh_stats)
                if self.config.navidrome.scan_on_download:
                    self.navidrome.trigger_scan()
                notify("🎯 Scout Download", f"Saved: {track.display_name}")
            else:
                self.app.call_from_thread(
                    self.query_one("#lbl_search_status", Label).update,
                    f"❌ Failed: {res.error}",
                )

    @work(exclusive=True, thread=True)
    def generate_dna_mix(self) -> None:
        raw_seeds = self.query_one("#inp_dna_seeds", Input).value.strip()
        count_val = int(self.query_one("#inp_dna_count", Input).value.strip() or 20)
        max_artist_val = int(self.query_one("#inp_dna_max_artist", Input).value.strip() or 2)

        seeds: list[Track] = []
        if raw_seeds:
            for s in raw_seeds.split(","):
                s = s.strip()
                if " - " in s:
                    p = s.split(" - ", 1)
                    seeds.append(Track(artist=p[0].strip(), title=p[1].strip()))
                elif s:
                    seeds.append(Track(artist="Unknown", title=s))
        else:
            seeds = self.navidrome.get_starred_tracks()

        if not seeds:
            self.app.call_from_thread(
                self.query_one("#lbl_dna_status", Label).update,
                "❌ No seed tracks provided or found in Navidrome.",
            )
            return

        self.app.call_from_thread(
            self.query_one("#lbl_dna_status", Label).update,
            f"Analyzing {len(seeds)} seeds with DNA Engine...",
        )

        def progress_cb(msg: str, cur: int, tot: int):
            self.app.call_from_thread(self.query_one("#lbl_dna_status", Label).update, msg)

        candidates = self.dna_engine.generate_mix(
            seeds=seeds,
            target_count=count_val,
            max_per_artist=max_artist_val,
            progress_callback=progress_cb,
        )
        self.mix_candidates = candidates

        def update_dna_ui():
            dt = self.query_one("#dt_dna", DataTable)
            dt.clear()
            for idx, c in enumerate(candidates, 1):
                score_str = f"{int(c.similarity_score * 100)}%" if c.similarity_score <= 1.0 else f"{c.similarity_score:.1f}x"
                dt.add_row(str(idx), c.track.artist, c.track.title, score_str, c.reason)
            self.query_one("#lbl_dna_status", Label).update(f"Generated {len(candidates)} mix tracks!")

        self.app.call_from_thread(update_dna_ui)

    @work(exclusive=True, thread=True)
    def download_all_mix_tracks(self) -> None:
        if not self.mix_candidates:
            self.app.call_from_thread(self.query_one("#lbl_dna_status", Label).update, "No mix generated to download.")
            return

        total = len(self.mix_candidates)
        downloaded = 0
        for idx, c in enumerate(self.mix_candidates, 1):
            self.app.call_from_thread(
                self.query_one("#lbl_dna_status", Label).update,
                f"Downloading [{idx}/{total}] {c.track.display_name}...",
            )
            res = self.downloader.download_track(c.track, target_dir=self.config.general.discovery_dir)
            if res.success:
                downloaded += 1

        self.app.call_from_thread(
            self.query_one("#lbl_dna_status", Label).update,
            f"✔ Completed mix download: {downloaded}/{total} saved!",
        )
        self.app.call_from_thread(self.refresh_stats)
        if self.config.navidrome.scan_on_download:
            self.navidrome.trigger_scan()
        notify("✨ Scout Mix Downloaded", f"Added {downloaded} discovery tracks to library.")

    def save_settings(self) -> None:
        from pathlib import Path
        self.config.general.music_dir = Path(self.query_one("#inp_cfg_music_dir", Input).value.strip())
        self.config.general.discovery_dir = Path(self.query_one("#inp_cfg_disc_dir", Input).value.strip())
        self.config.general.audio_format = self.query_one("#inp_cfg_format", Input).value.strip()
        self.config.general.bitrate = self.query_one("#inp_cfg_bitrate", Input).value.strip()
        self.config.lastfm.api_key = self.query_one("#inp_cfg_lastfm", Input).value.strip()
        self.config.subsonic.url = self.query_one("#inp_cfg_sub_url", Input).value.strip()
        self.config.subsonic.username = self.query_one("#inp_cfg_sub_user", Input).value.strip()

        self.config.save()
        self.query_one("#lbl_settings_status", Label).update("✔ Configuration saved successfully!")
