"""Shared domain models for tracks, albums, artists, candidates, and download results."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Track:
    title: str
    artist: str
    album: str = "Single"
    album_artist: str = ""
    track_num: int = 1
    disc_num: int = 1
    duration_seconds: int = 0
    cover_url: str = ""
    source_url: str = ""
    video_id: str = ""
    spotify_id: str = ""
    is_studio: bool = True
    year: str = ""
    genre: str = ""

    def __post_init__(self):
        if not self.album_artist:
            self.album_artist = self.artist

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title}"

    @property
    def clean_key(self) -> str:
        from scout.core.dedupe import normalize_key
        return normalize_key(self.artist, self.title)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "track_num": self.track_num,
            "disc_num": self.disc_num,
            "duration_seconds": self.duration_seconds,
            "cover_url": self.cover_url,
            "source_url": self.source_url,
            "video_id": self.video_id,
            "spotify_id": self.spotify_id,
            "is_studio": self.is_studio,
            "year": self.year,
            "genre": self.genre,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        return cls(
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album=data.get("album", "Single"),
            album_artist=data.get("album_artist", ""),
            track_num=data.get("track_num", 1),
            disc_num=data.get("disc_num", 1),
            duration_seconds=data.get("duration_seconds", 0),
            cover_url=data.get("cover_url", ""),
            source_url=data.get("source_url", ""),
            video_id=data.get("video_id", ""),
            spotify_id=data.get("spotify_id", ""),
            is_studio=data.get("is_studio", True),
            year=data.get("year", ""),
            genre=data.get("genre", ""),
        )


@dataclass
class Album:
    title: str
    artist: str
    year: str = ""
    cover_url: str = ""
    tracks: list[Track] = field(default_factory=list)
    source_url: str = ""
    browse_id: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title} ({self.year})" if self.year else f"{self.artist} - {self.title}"


@dataclass
class Artist:
    name: str
    browse_id: str = ""
    albums: list[Album] = field(default_factory=list)
    singles: list[Album] = field(default_factory=list)


@dataclass
class DiscoveryCandidate:
    track: Track
    similarity_score: float = 0.0
    seed_track: str = ""
    genre_tags: list[str] = field(default_factory=list)
    reason: str = "recommendation"

    @property
    def display_name(self) -> str:
        return f"{self.track.artist} - {self.track.title} [match: {int(self.similarity_score * 100)}%]"


@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[Path] = None
    track: Optional[Track] = None
    error: Optional[str] = None
