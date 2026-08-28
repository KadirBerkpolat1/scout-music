"""Tests for downloader path resolution, sanitization, and Mutagen tagging."""

from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB

from scout.core.config import Config
from scout.core.downloader import AudioDownloader, sanitize_filename
from scout.core.models import Track


def test_sanitize_filename():
    assert sanitize_filename('AC/DC: Back in Black [Remastered] *?<>|"') == "ACDC Back in Black [Remastered]"
    assert sanitize_filename("  Artist   -   Title  ") == "Artist - Title"


def test_resolve_destination_path(tmp_path: Path):
    cfg = Config()
    cfg.general.music_dir = tmp_path
    cfg.general.audio_format = "mp3"
    cfg.general.folder_template = "{artist}/{album}/{track_num:02d} - {title}"

    downloader = AudioDownloader(config=cfg)
    track = Track(
        title="Get Lucky",
        artist="Daft Punk",
        album="Random Access Memories",
        track_num=8,
    )
    dest = downloader.resolve_destination_path(track)
    expected = tmp_path / "Daft Punk" / "Random Access Memories" / "08 - Get Lucky.mp3"
    assert dest == expected


def test_is_track_already_present_and_skip(tmp_path: Path):
    cfg = Config()
    cfg.general.music_dir = tmp_path
    cfg.general.discovery_dir = tmp_path / "Keşif"
    cfg.general.discovery_dir.mkdir(parents=True, exist_ok=True)

    downloader = AudioDownloader(config=cfg)
    track = Track(title="Show", artist="Ado")

    # Create mock existing file in discovery_dir as "Ado - 唱 - Show.mp3"
    existing_file = cfg.general.discovery_dir / "Ado - 唱 - Show.mp3"
    existing_file.write_bytes(b"dummy audio content" * 100)

    found = downloader.is_track_already_present(track, target_dir=cfg.general.discovery_dir)
    assert found == existing_file

    # Test download_track skips network when overwrite=False
    res = downloader.download_track(track, target_dir=cfg.general.discovery_dir, overwrite=False)
    assert res.success is True
    assert res.already_exists is True
    assert res.file_path == existing_file
