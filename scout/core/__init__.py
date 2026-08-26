"""Core subsystems: configuration, models, history deduplication, and downloader."""

from scout.core.config import Config, load_config
from scout.core.dedupe import HistoryStore
from scout.core.downloader import AudioDownloader
from scout.core.models import Album, Artist, DiscoveryCandidate, DownloadResult, Track

__all__ = [
    "Config",
    "load_config",
    "HistoryStore",
    "AudioDownloader",
    "Track",
    "Album",
    "Artist",
    "DiscoveryCandidate",
    "DownloadResult",
]
