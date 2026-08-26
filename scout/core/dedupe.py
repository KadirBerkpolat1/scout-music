"""SQLite-backed history, deduplication, and seed tracking store for Scout."""

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from scout.core.config import get_xdg_data_dir
from scout.core.models import Track


def normalize_key(artist: str, title: str) -> str:
    # Strip parentheticals and bracketed tags from artist
    norm_artist = re.sub(r"\s*\(.*?\)", "", artist)
    norm_artist = re.sub(r"\s*\[.*?\]", "", norm_artist)
    norm_artist = re.sub(r"[^a-zA-Z0-9\u0080-\uffff]", "", norm_artist.lower())

    # Strip parentheticals, brackets, and feat/remaster/official tags from title
    norm_title = re.sub(r"\s*\(.*?\)", "", title)
    norm_title = re.sub(r"\s*\[.*?\]", "", norm_title)
    norm_title = re.sub(r"\b(feat|ft|featuring|official|audio|mv|remastered)\b.*", "", norm_title, flags=re.IGNORECASE)
    norm_title = re.sub(r"[^a-zA-Z0-9\u0080-\uffff]", "", norm_title.lower())

    return f"{norm_artist}:{norm_title}"

class HistoryStore:
    def __init__(self, db_path: Optional[Path] = None):
        is_custom_path = db_path is not None
        if db_path is None:
            data_dir = get_xdg_data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "history.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        if not is_custom_path:
            self._check_legacy_migration()
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downloaded_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clean_key TEXT UNIQUE,
                    artist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    album TEXT,
                    source_url TEXT,
                    file_path TEXT,
                    audio_format TEXT,
                    bitrate TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_seeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seed_key TEXT UNIQUE,
                    artist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reason TEXT,
                    date_processed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovery_blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clean_key TEXT UNIQUE,
                    artist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reason TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    def _check_legacy_migration(self):
        # Check standard legacy cache paths
        legacy_paths = [
            Path.home() / ".local" / "share" / "navidrome" / "scout_history.json",
            Path.home() / ".local" / "share" / "scout" / "scout_history.json",
        ]
        for p in legacy_paths:
            if p.exists():
                self.migrate_from_legacy_json(p)
                break

    def migrate_from_legacy_json(self, json_path: Path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            processed_seeds = data.get("processed_seeds", [])
            downloaded_tracks = data.get("downloaded_tracks", [])

            with self._get_connection() as conn:
                for seed in processed_seeds:
                    if " - " in seed:
                        parts = seed.split(" - ", 1)
                        artist, title = parts[0].strip(), parts[1].strip()
                    else:
                        artist, title = "Unknown", seed.strip()
                    key = normalize_key(artist, title)
                    conn.execute("""
                        INSERT OR IGNORE INTO processed_seeds (seed_key, artist, title, reason)
                        VALUES (?, ?, ?, ?)
                    """, (key, artist, title, "legacy_migration"))

                for track in downloaded_tracks:
                    if " - " in track:
                        parts = track.split(" - ", 1)
                        artist, title = parts[0].strip(), parts[1].strip()
                    else:
                        artist, title = "Unknown", track.strip()
                    key = normalize_key(artist, title)
                    conn.execute("""
                        INSERT OR IGNORE INTO downloaded_tracks (clean_key, artist, title)
                        VALUES (?, ?, ?)
                    """, (key, artist, title))

                conn.commit()
        except Exception:
            pass

    def is_downloaded(self, artist: str, title: str) -> bool:
        key = normalize_key(artist, title)
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM downloaded_tracks WHERE clean_key = ?", (key,)
            )
            return cursor.fetchone() is not None

    def record_download(
        self,
        track: Track,
        file_path: Optional[Path] = None,
        source_url: str = "",
        audio_format: str = "mp3",
        bitrate: str = "320k",
    ):
        key = track.clean_key
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO downloaded_tracks 
                (clean_key, artist, title, album, source_url, file_path, audio_format, bitrate, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                key,
                track.artist,
                track.title,
                track.album,
                source_url or track.source_url,
                str(file_path) if file_path else "",
                audio_format,
                bitrate,
            ))
            conn.commit()

    def is_seed_processed(self, artist: str, title: str) -> bool:
        key = normalize_key(artist, title)
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_seeds WHERE seed_key = ?", (key,)
            )
            return cursor.fetchone() is not None

    def record_seed(self, artist: str, title: str, reason: str = "discovery"):
        key = normalize_key(artist, title)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO processed_seeds (seed_key, artist, title, reason, date_processed)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, artist, title, reason))
            conn.commit()

    def is_blacklisted(self, artist: str, title: str) -> bool:
        key = normalize_key(artist, title)
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM discovery_blacklist WHERE clean_key = ?", (key,)
            )
            return cursor.fetchone() is not None

    def blacklist(self, artist: str, title: str, reason: str = ""):
        key = normalize_key(artist, title)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO discovery_blacklist (clean_key, artist, title, reason, date_added)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, artist, title, reason))
            conn.commit()

    def get_recent_downloads(self, limit: int = 50) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, artist, title, album, source_url, file_path, audio_format, bitrate, date_added
                FROM downloaded_tracks
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_recent_seeds(self, limit: int = 50) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, artist, title, reason, date_processed
                FROM processed_seeds
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_downloaded_within_days(self, days: int = 30) -> set[str]:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT clean_key FROM downloaded_tracks WHERE date_added >= ?
            """, (since,))
            return {row["clean_key"] for row in cursor.fetchall()}

    def get_all_blacklist_keys(self) -> set[str]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT clean_key FROM discovery_blacklist")
            return {row["clean_key"] for row in cursor.fetchall() if row["clean_key"]}

    def get_all_downloaded_keys(self) -> set[str]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT clean_key FROM downloaded_tracks")
            return {row["clean_key"] for row in cursor.fetchall() if row["clean_key"]}

    def sync_deleted_files_to_blacklist(self, active_seed_keys: Optional[set[str]] = None) -> list[dict]:
        """
        Inspect all recorded downloads. If a physical file has been deleted by the user
        and is not in the active starred favorites, automatically blacklist it so Scout
        never re-downloads or re-suggests it.
        """
        active_keys = active_seed_keys or set()
        blacklisted_now = []

        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, clean_key, artist, title, file_path
                FROM downloaded_tracks
                WHERE file_path IS NOT NULL AND file_path != ''
            """)
            rows = cursor.fetchall()

            for r in rows:
                fpath = Path(r["file_path"])
                c_key = r["clean_key"]

                # If user deleted the physical file and didn't re-star it
                if not fpath.exists() and c_key not in active_keys:
                    if not self.is_blacklisted(r["artist"], r["title"]):
                        self.blacklist(r["artist"], r["title"], reason="deleted_by_user")
                        blacklisted_now.append({"artist": r["artist"], "title": r["title"]})

        return blacklisted_now

    def get_stats(self) -> dict:
        with self._get_connection() as conn:
            total_downloads = conn.execute("SELECT COUNT(*) FROM downloaded_tracks").fetchone()[0]
            total_seeds = conn.execute("SELECT COUNT(*) FROM processed_seeds").fetchone()[0]
            total_blacklist = conn.execute("SELECT COUNT(*) FROM discovery_blacklist").fetchone()[0]
            return {
                "total_downloads": total_downloads,
                "total_seeds": total_seeds,
                "total_blacklist": total_blacklist,
            }
