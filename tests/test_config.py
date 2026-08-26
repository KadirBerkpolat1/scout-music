"""Tests for configuration engine."""

from pathlib import Path
from scout.core.config import Config, GeneralConfig, LastFMConfig, SubsonicConfig, NavidromeConfig


def test_config_defaults(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg = Config.load(cfg_file)

    assert cfg.general.audio_format == "mp3"
    assert cfg.general.bitrate == "320k"
    assert cfg.lastfm.api_key == "d37974f8d011df9bf3e7e993b53143a3"
    assert cfg.subsonic.enabled is False
    assert cfg.navidrome.scan_on_download is True
    assert cfg_file.exists()


def test_config_save_and_reload(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg = Config.load(cfg_file)

    cfg.general.audio_format = "flac"
    cfg.general.bitrate = "best"
    cfg.subsonic.enabled = True
    cfg.subsonic.url = "http://navidrome.local:4533"
    cfg.subsonic.username = "berk"
    cfg.save()

    reloaded = Config.load(cfg_file)
    assert reloaded.general.audio_format == "flac"
    assert reloaded.subsonic.enabled is True
    assert reloaded.subsonic.url == "http://navidrome.local:4533"
    assert reloaded.subsonic.username == "berk"
