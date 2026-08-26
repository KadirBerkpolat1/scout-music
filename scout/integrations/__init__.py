"""External system integrations: Subsonic, MPRIS, Desktop Notifier, and Navidrome."""

from scout.integrations.mpris import MPRISConnector, get_current_playing_track
from scout.integrations.navidrome import NavidromeScanner
from scout.integrations.notifier import notify
from scout.integrations.subsonic import SubsonicClient

__all__ = [
    "SubsonicClient",
    "MPRISConnector",
    "get_current_playing_track",
    "notify",
    "NavidromeScanner",
]
