"""XDG-compliant configuration engine for Scout."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def get_default_music_dir() -> Path:
    home = Path.home()
    if (home / "Müzik").exists():
        return home / "Müzik"
    return home / "Music"


def get_default_discovery_dir() -> Path:
    home = Path.home()
    if (home / "Müzik" / "Keşif").exists():
        return home / "Müzik" / "Keşif"
    if (home / "Müzik").exists():
        return home / "Müzik" / "Keşif"
    return home / "Music" / "Discovery"


def get_xdg_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "scout"
    return Path.home() / ".config" / "scout"


def get_xdg_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "scout"
    return Path.home() / ".local" / "share" / "scout"


@dataclass
class GeneralConfig:
    music_dir: Path = field(default_factory=get_default_music_dir)
    discovery_dir: Path = field(default_factory=get_default_discovery_dir)
    audio_format: str = "mp3"  # "mp3", "flac", "opus"
    bitrate: str = "320k"
    folder_template: str = "{artist}/{album}/{track_num:02d} - {title}"

    def __post_init__(self):
        if isinstance(self.music_dir, str):
            self.music_dir = Path(os.path.expanduser(self.music_dir))
        if isinstance(self.discovery_dir, str):
            self.discovery_dir = Path(os.path.expanduser(self.discovery_dir))


@dataclass
class LastFMConfig:
    api_key: str = "d37974f8d011df9bf3e7e993b53143a3"


@dataclass
class SubsonicConfig:
    enabled: bool = False
    url: str = "http://localhost:4533"
    username: str = ""
    token: str = ""
    salt: str = ""
    password: str = ""
    seed_playlist: str = "🎯 Scout Seed"
    mix_playlist: str = "✨ Scout Mix"


@dataclass
class NavidromeConfig:
    scan_on_download: bool = True
    cli_path: str = "/usr/bin/navidrome"
    config_path: str = "~/.config/navidrome/navidrome.toml"
    db_path: str = "~/.local/share/navidrome/navidrome.db"

    def get_expanded_config_path(self) -> Path:
        return Path(os.path.expanduser(self.config_path))

    def get_expanded_db_path(self) -> Path:
        return Path(os.path.expanduser(self.db_path))


@dataclass
class Config:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    lastfm: LastFMConfig = field(default_factory=LastFMConfig)
    subsonic: SubsonicConfig = field(default_factory=SubsonicConfig)
    navidrome: NavidromeConfig = field(default_factory=NavidromeConfig)
    config_path: Optional[Path] = None

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        if path is None:
            config_dir = get_xdg_config_dir()
            path = config_dir / "config.toml"

        if not path.exists():
            cfg = cls(config_path=path)
            cfg.save()
            return cfg

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)

            gen_data = data.get("general", {})
            general = GeneralConfig(
                music_dir=gen_data.get("music_dir", get_default_music_dir()),
                discovery_dir=gen_data.get("discovery_dir", get_default_discovery_dir()),
                audio_format=gen_data.get("audio_format", "mp3"),
                bitrate=gen_data.get("bitrate", "320k"),
                folder_template=gen_data.get("folder_template", "{artist}/{album}/{track_num:02d} - {title}"),
            )

            lfm_data = data.get("lastfm", {})
            lastfm = LastFMConfig(
                api_key=lfm_data.get("api_key", "d37974f8d011df9bf3e7e993b53143a3")
            )

            sub_data = data.get("subsonic", {})
            subsonic = SubsonicConfig(
                enabled=sub_data.get("enabled", False),
                url=sub_data.get("url", "http://localhost:4533"),
                username=sub_data.get("username", ""),
                token=sub_data.get("token", ""),
                salt=sub_data.get("salt", ""),
                password=sub_data.get("password", ""),
                seed_playlist=sub_data.get("seed_playlist", "🎯 Scout Seed"),
                mix_playlist=sub_data.get("mix_playlist", "✨ Scout Mix"),
            )

            nav_data = data.get("navidrome", {})
            navidrome = NavidromeConfig(
                scan_on_download=nav_data.get("scan_on_download", True),
                cli_path=nav_data.get("cli_path", "/usr/bin/navidrome"),
                config_path=nav_data.get("config_path", "~/.config/navidrome/navidrome.toml"),
                db_path=nav_data.get("db_path", "~/.local/share/navidrome/navidrome.db"),
            )

            return cls(
                general=general,
                lastfm=lastfm,
                subsonic=subsonic,
                navidrome=navidrome,
                config_path=path,
            )
        except Exception as e:
            # Fallback to default if corrupted
            return cls(config_path=path)

    def save(self, path: Optional[Path] = None):
        target_path = path or self.config_path or (get_xdg_config_dir() / "config.toml")
        target_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# Scout Universal Music Discovery & Archiving Configuration",
            "",
            "[general]",
            f'music_dir = "{self.general.music_dir}"',
            f'discovery_dir = "{self.general.discovery_dir}"',
            f'audio_format = "{self.general.audio_format}"',
            f'bitrate = "{self.general.bitrate}"',
            f'folder_template = "{self.general.folder_template}"',
            "",
            "[lastfm]",
            f'api_key = "{self.lastfm.api_key}"',
            "",
            "[subsonic]",
            f"enabled = {str(self.subsonic.enabled).lower()}",
            f'url = "{self.subsonic.url}"',
            f'username = "{self.subsonic.username}"',
            f'token = "{self.subsonic.token}"',
            f'salt = "{self.subsonic.salt}"',
            f'password = "{self.subsonic.password}"',
            f'seed_playlist = "{self.subsonic.seed_playlist}"',
            f'mix_playlist = "{self.subsonic.mix_playlist}"',
            "",
            "[navidrome]",
            f"scan_on_download = {str(self.navidrome.scan_on_download).lower()}",
            f'cli_path = "{self.navidrome.cli_path}"',
            f'config_path = "{self.navidrome.config_path}"',
            f'db_path = "{self.navidrome.db_path}"',
            "",
        ]

        with open(target_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def ensure_directories(self):
        self.general.music_dir.mkdir(parents=True, exist_ok=True)
        self.general.discovery_dir.mkdir(parents=True, exist_ok=True)
        get_xdg_data_dir().mkdir(parents=True, exist_ok=True)


def load_config(path: Optional[Path] = None) -> Config:
    cfg = Config.load(path)
    cfg.ensure_directories()
    return cfg
