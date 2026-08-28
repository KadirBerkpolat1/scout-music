"""Metadata and discovery providers for Spotify, YouTube Music, and Last.fm."""

from scout.providers.lastfm import LastFMProvider
from scout.providers.qobuz import QobuzFlacProvider
from scout.providers.soulseek import SoulseekFlacProvider
from scout.providers.spotify import SpotifyProvider
from scout.providers.ytmusic import YTMusicProvider

__all__ = [
    "SpotifyProvider",
    "YTMusicProvider",
    "LastFMProvider",
    "QobuzFlacProvider",
    "SoulseekFlacProvider",
]
