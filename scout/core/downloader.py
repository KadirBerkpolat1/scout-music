"""Audio downloader and studio-grade metadata tagger using yt-dlp and Mutagen."""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Optional
import requests
import yt_dlp
from mutagen.id3 import (
    APIC,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TRCK,
    ID3NoHeaderError,
)
from mutagen.mp3 import MP3

from scout.core.config import Config, load_config
from scout.core.dedupe import HistoryStore
from scout.core.models import DownloadResult, Track
from scout.providers.qobuz import QobuzFlacProvider
from scout.providers.soulseek import SoulseekFlacProvider
def sanitize_filename(name: str) -> str:
    """Clean filename of illegal characters across Linux, macOS, and Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


class AudioDownloader:
    def __init__(
        self,
        config: Optional[Config] = None,
        history_store: Optional[HistoryStore] = None,
        qobuz_provider: Optional[QobuzFlacProvider] = None,
        soulseek_provider: Optional[SoulseekFlacProvider] = None,
    ):
        self.config = config or load_config()
        self.history = history_store or HistoryStore()
        self.qobuz = qobuz_provider or QobuzFlacProvider()
        self.soulseek = soulseek_provider or SoulseekFlacProvider(config=self.config.soulseek)
    def resolve_destination_path(self, track: Track, target_dir: Optional[Path] = None, flat: bool = False) -> Path:
        base_dir = target_dir or self.config.general.music_dir
        ext = self.config.general.audio_format.lower()

        clean_artist = sanitize_filename(track.artist or "Unknown Artist")
        clean_album = sanitize_filename(track.album or "Single")
        clean_title = sanitize_filename(track.title or "Unknown Title")
        track_num = track.track_num or 1

        if flat or (target_dir and target_dir == self.config.general.discovery_dir):
            full_path = base_dir / f"{clean_artist} - {clean_title}.{ext}"
        elif target_dir and target_dir != self.config.general.music_dir:
            # Inside a dedicated playlist directory, organize by artist: <PlaylistDir>/<Artist>/<track_num> - <title>.<ext>
            if track_num and track_num > 0:
                full_path = base_dir / clean_artist / f"{track_num:02d} - {clean_title}.{ext}"
            else:
                full_path = base_dir / clean_artist / f"{clean_title}.{ext}"
        else:
            template = self.config.general.folder_template
            relative_path_str = template.format(
                artist=clean_artist,
                album=clean_album,
                title=clean_title,
                track_num=track_num,
            )
            full_path = base_dir / f"{relative_path_str}.{ext}"

        full_path.parent.mkdir(parents=True, exist_ok=True)
        return full_path
    def is_track_already_present(self, track: Track, target_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Check if the track already exists physically on disk in target_dir, discovery_dir,
        or music_dir across supported audio formats, or in history database with an existing file.
        """
        from scout.core.dedupe import get_track_keys
        track_keys = track.clean_keys

        # 1. Check exact resolved destination path with all valid audio extensions
        dest_path = self.resolve_destination_path(track, target_dir)
        for ext in [".mp3", ".flac", ".opus", ".m4a", ".ogg", ".wav"]:
            candidate_path = dest_path.with_suffix(ext)
            if candidate_path.exists() and candidate_path.is_file() and candidate_path.stat().st_size > 1000:
                return candidate_path

        # 2. Check discovery_dir, target_dir, and music_dir root / subfolders
        search_dirs = []
        if target_dir and target_dir.exists():
            search_dirs.append(target_dir)
        if self.config.general.discovery_dir.exists() and self.config.general.discovery_dir not in search_dirs:
            search_dirs.append(self.config.general.discovery_dir)
        if self.config.general.music_dir.exists() and self.config.general.music_dir not in search_dirs:
            search_dirs.append(self.config.general.music_dir)

        for s_dir in search_dirs:
            for ext in ["*.mp3", "*.flac", "*.opus", "*.m4a", "*.ogg", "*.wav"]:
                for f in s_dir.glob(ext):
                    if not f.is_file() or f.stat().st_size < 1000:
                        continue
                    stem = f.stem
                    file_keys = set()
                    if " - " in stem:
                        parts = stem.split(" - ", 1)
                        file_keys = get_track_keys(parts[0].strip(), parts[1].strip())
                    else:
                        file_keys = get_track_keys("", stem)
                    if track_keys & file_keys:
                        return f

        # 3. Check history database recorded file_path
        if self.history.is_downloaded(track.artist, track.title):
            with self.history._get_connection() as conn:
                keys = list(track_keys)
                if keys:
                    placeholders = ",".join("?" * len(keys))
                    cursor = conn.execute(
                        f"SELECT file_path FROM downloaded_tracks WHERE clean_key IN ({placeholders}) AND file_path IS NOT NULL AND file_path != ''",
                        keys,
                    )
                    for row in cursor.fetchall():
                        hp = Path(row["file_path"])
                        if hp.exists() and hp.is_file() and hp.stat().st_size > 1000:
                            return hp

        return None

    def download_cover_bytes(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except Exception:
            pass
        return None

    def tag_mp3(self, file_path: Path, track: Track, cover_bytes: Optional[bytes] = None):
        try:
            try:
                audio = MP3(file_path, ID3=ID3)
            except ID3NoHeaderError:
                audio = MP3(file_path)
                audio.add_tags()

            if audio.tags is None:
                audio.add_tags()

            audio.tags.add(TIT2(encoding=3, text=track.title))
            audio.tags.add(TPE1(encoding=3, text=track.artist))
            audio.tags.add(TPE2(encoding=3, text=track.album_artist or track.artist))
            audio.tags.add(TALB(encoding=3, text=track.album))
            audio.tags.add(TRCK(encoding=3, text=f"{track.track_num}"))
            audio.tags.add(TPOS(encoding=3, text=f"{track.disc_num}"))

            if track.year:
                audio.tags.add(TDRC(encoding=3, text=str(track.year)))
            if track.genre:
                audio.tags.add(TCON(encoding=3, text=track.genre))

            if cover_bytes:
                audio.tags.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,  # 3 is for album front cover
                        desc="Cover",
                        data=cover_bytes,
                    )
                )

            audio.save(v2_version=3)
        except Exception as e:
            # Fallback gracefully if tagging fails
            pass

    def tag_flac(self, file_path: Path, track: Track, cover_bytes: Optional[bytes] = None):
        try:
            from mutagen.flac import FLAC, Picture

            audio = FLAC(file_path)
            audio["TITLE"] = track.title
            audio["ARTIST"] = track.artist
            audio["ALBUMARTIST"] = track.album_artist or track.artist
            audio["ALBUM"] = track.album
            audio["TRACKNUMBER"] = str(track.track_num)
            audio["DISCNUMBER"] = str(track.disc_num)
            if track.year:
                audio["DATE"] = str(track.year)
            if track.genre:
                audio["GENRE"] = track.genre

            if cover_bytes:
                pic = Picture()
                pic.data = cover_bytes
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.desc = "Front Cover"
                audio.clear_pictures()
                audio.add_picture(pic)

            audio.save()
        except Exception:
            pass

    def tag_opus(self, file_path: Path, track: Track, cover_bytes: Optional[bytes] = None):
        try:
            from mutagen.oggopus import OggOpus

            audio = OggOpus(file_path)
            audio["title"] = track.title
            audio["artist"] = track.artist
            audio["albumartist"] = track.album_artist or track.artist
            audio["album"] = track.album
            audio["tracknumber"] = str(track.track_num)
            audio["discnumber"] = str(track.disc_num)
            if track.year:
                audio["date"] = str(track.year)
            if track.genre:
                audio["genre"] = track.genre
            audio.save()
        except Exception:
            pass

    def tag_file(self, file_path: Path, track: Track, cover_bytes: Optional[bytes] = None):
        ext = file_path.suffix.lower()
        if ext == ".mp3":
            self.tag_mp3(file_path, track, cover_bytes)
        elif ext == ".flac":
            self.tag_flac(file_path, track, cover_bytes)
        elif ext in (".opus", ".ogg"):
            self.tag_opus(file_path, track, cover_bytes)

    def download_track(
        self,
        track: Track,
        target_dir: Optional[Path] = None,
        progress_hook: Optional[Callable[[dict], None]] = None,
        overwrite: bool = False,
    ) -> DownloadResult:
        if not overwrite:
            existing = self.is_track_already_present(track, target_dir)
            if existing:
                self.history.record_download(
                    track=track,
                    file_path=existing,
                    audio_format=existing.suffix.lstrip("."),
                    bitrate=self.config.general.bitrate,
                )
                return DownloadResult(
                    success=True,
                    file_path=existing,
                    track=track,
                    already_exists=True,
                )

        dest_path = self.resolve_destination_path(track, target_dir)
        # 1. Attempt True Lossless FLAC download via Soulseek P2P or Qobuz
        if self.config.general.lossless_first or self.config.general.audio_format.lower() == "flac":
            # A. Soulseek P2P Lossless FLAC
            try:
                tmp_flac = self.soulseek.download_flac(track)
                if tmp_flac and tmp_flac.exists() and tmp_flac.stat().st_size > 1024 * 1024:
                    flac_dest = dest_path.with_suffix(".flac")
                    cover_bytes = self.download_cover_bytes(track.cover_url)
                    self.tag_file(tmp_flac, track, cover_bytes)
                    flac_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(tmp_flac), str(flac_dest))
                    self.history.record_download(
                        track=track,
                        file_path=flac_dest,
                        source_url="soulseek://p2p",
                        audio_format="flac",
                        bitrate="Lossless FLAC",
                    )
                    return DownloadResult(
                        success=True,
                        file_path=flac_dest,
                        track=track,
                    )
            except Exception:
                pass

            # B. Qobuz Hi-Res FLAC fallback
            try:
                stream_info = self.qobuz.resolve_flac_stream(track)
                if stream_info and stream_info.get("download_url"):
                    flac_url = stream_info["download_url"]
                    container = stream_info.get("container", "flac")
                    flac_dest = dest_path.with_suffix(f".{container}")

                    resp = requests.get(flac_url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=30)
                    if resp.status_code == 200:
                        with tempfile.NamedTemporaryFile(suffix=f".{container}", delete=False) as tmp_flac:
                            for chunk in resp.iter_content(chunk_size=65536):
                                if chunk:
                                    tmp_flac.write(chunk)
                            tmp_flac_path = Path(tmp_flac.name)

                        cover_bytes = self.download_cover_bytes(track.cover_url)
                        self.tag_file(tmp_flac_path, track, cover_bytes)
                        flac_dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(tmp_flac_path), str(flac_dest))

                        bitrate_label = f"{stream_info.get('bit_depth', 24)}bit/{stream_info.get('sample_rate', 44100)//1000}kHz"
                        self.history.record_download(
                            track=track,
                            file_path=flac_dest,
                            source_url=flac_url,
                            audio_format=container,
                            bitrate=bitrate_label,
                        )
                        return DownloadResult(
                            success=True,
                            file_path=flac_dest,
                            track=track,
                        )
            except Exception:
                pass

        # 2. Fallback to YouTube Music studio audio extraction via yt-dlp
        source_url = ""
        if track.video_id:
            source_url = f"https://www.youtube.com/watch?v={track.video_id}"
        elif track.source_url and not ("spotify.com" in track.source_url or "spotify.link" in track.source_url):
            source_url = track.source_url
        else:
            from scout.providers.ytmusic import YTMusicProvider
            ytm = YTMusicProvider()
            matched = ytm.search_track(track.artist, track.title, album=track.album)
            if matched and matched.video_id:
                track.video_id = matched.video_id
                source_url = f"https://www.youtube.com/watch?v={matched.video_id}"
                if not track.cover_url and matched.cover_url:
                    track.cover_url = matched.cover_url

        if not source_url:
            return DownloadResult(
                success=False,
                track=track,
                error="No valid YouTube stream or audio source resolved for track",
            )
        audio_format = self.config.general.audio_format.lower()
        bitrate = self.config.general.bitrate.replace("k", "")
        # Prepare yt-dlp options
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": bitrate,
            }
        ]

        # Use temporary file template to ensure clean write and avoid partial file corruption
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_out_tmpl = str(Path(tmpdir) / "download.%(ext)s")

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": tmp_out_tmpl,
                "postprocessors": postprocessors,
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
            }

            if progress_hook:
                ydl_opts["progress_hooks"] = [progress_hook]

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([source_url])

                # Find converted audio file in tmpdir
                downloaded_files = list(Path(tmpdir).glob(f"download.{audio_format}"))
                if not downloaded_files:
                    # check if other ext matched
                    downloaded_files = list(Path(tmpdir).glob("download.*"))

                if not downloaded_files:
                    return DownloadResult(
                        success=False,
                        track=track,
                        error="Audio extraction failed; no output file produced",
                    )

                temp_file = downloaded_files[0]

                # Download cover artwork if available
                cover_bytes = self.download_cover_bytes(track.cover_url)

                # Tag the temporary file before moving
                self.tag_file(temp_file, track, cover_bytes)

                # Move to destination path (using shutil.move for cross-device support)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(temp_file), str(dest_path))
                # Record in history store
                self.history.record_download(
                    track=track,
                    file_path=dest_path,
                    source_url=source_url,
                    audio_format=audio_format,
                    bitrate=self.config.general.bitrate,
                )

                return DownloadResult(
                    success=True,
                    file_path=dest_path,
                    track=track,
                )
            except Exception as e:
                return DownloadResult(
                    success=False,
                    track=track,
                    error=str(e),
                )
