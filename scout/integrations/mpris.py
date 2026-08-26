"""Linux MPRIS DBus connector for querying currently playing media tracks."""

import re
import subprocess
from typing import Optional

from scout.core.models import Track


def list_mpris_players() -> list[str]:
    """Find all active MPRIS DBus service names."""
    try:
        cmd = [
            "dbus-send",
            "--session",
            "--dest=org.freedesktop.DBus",
            "--type=method_call",
            "--print-reply",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus.ListNames",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode != 0:
            return []

        names = re.findall(r'string "(org\.mpris\.MediaPlayer2\.[^"]+)"', res.stdout)
        # Prioritize popular/dedicated players
        priority_order = ["feishin", "spotify", "clementine", "amberol", "rhythmbox", "vlc"]

        def sort_key(name: str) -> int:
            lower = name.lower()
            for idx, p in enumerate(priority_order):
                if p in lower:
                    return idx
            return len(priority_order)

        names.sort(key=sort_key)
        return names
    except Exception:
        return []


def parse_dbus_metadata(output: str) -> dict[str, str]:
    """Parse dbus-send metadata reply text into a key-value dictionary."""
    metadata: dict[str, str] = {}

    # Extract title
    title_match = re.search(r'string "xesam:title"\s+variant\s+string "([^"]+)"', output)
    if title_match:
        metadata["title"] = title_match.group(1).strip()

    # Extract artist (often inside array [ string "..." ])
    artist_match = re.search(r'string "xesam:artist"\s+variant\s+array \[\s+string "([^"]+)"', output)
    if artist_match:
        metadata["artist"] = artist_match.group(1).strip()
    else:
        # Single string fallback
        artist_single = re.search(r'string "xesam:artist"\s+variant\s+string "([^"]+)"', output)
        if artist_single:
            metadata["artist"] = artist_single.group(1).strip()

    # Extract album
    album_match = re.search(r'string "xesam:album"\s+variant\s+string "([^"]+)"', output)
    if album_match:
        metadata["album"] = album_match.group(1).strip()

    # Extract artUrl
    art_match = re.search(r'string "mpris:artUrl"\s+variant\s+string "([^"]+)"', output)
    if art_match:
        metadata["artUrl"] = art_match.group(1).strip()

    return metadata


class MPRISConnector:
    def __init__(self, preferred_player: Optional[str] = None):
        self.preferred_player = preferred_player

    def get_active_player(self) -> Optional[str]:
        players = list_mpris_players()
        if not players:
            return None
        if self.preferred_player:
            for p in players:
                if self.preferred_player.lower() in p.lower():
                    return p
        return players[0]

    def get_playback_status(self, player_service: str) -> str:
        try:
            cmd = [
                "dbus-send",
                "--session",
                f"--dest={player_service}",
                "--type=method_call",
                "--print-reply",
                "/org/mpris/MediaPlayer2",
                "org.freedesktop.DBus.Properties.Get",
                "string:org.mpris.MediaPlayer2.Player",
                "string:PlaybackStatus",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                match = re.search(r'variant\s+string "([^"]+)"', res.stdout)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return "Unknown"

    def get_current_track(self) -> Optional[Track]:
        player = self.get_active_player()
        if not player:
            return None

        try:
            cmd = [
                "dbus-send",
                "--session",
                f"--dest={player}",
                "--type=method_call",
                "--print-reply",
                "/org/mpris/MediaPlayer2",
                "org.freedesktop.DBus.Properties.Get",
                "string:org.mpris.MediaPlayer2.Player",
                "string:Metadata",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode != 0:
                return None

            metadata = parse_dbus_metadata(res.stdout)
            title = metadata.get("title", "")
            artist = metadata.get("artist", "")
            album = metadata.get("album", "Single")
            art_url = metadata.get("artUrl", "")

            if not title or not artist:
                return None

            return Track(
                title=title,
                artist=artist,
                album=album,
                cover_url=art_url,
            )
        except Exception:
            return None


def get_current_playing_track() -> Optional[Track]:
    connector = MPRISConnector()
    return connector.get_current_track()
