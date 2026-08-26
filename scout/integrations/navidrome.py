"""Navidrome local scanner CLI trigger and SQLite DB direct reader."""

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Optional

from scout.core.config import Config, NavidromeConfig, load_config
from scout.core.models import Track


class NavidromeScanner:
    def __init__(self, config: Optional[NavidromeConfig] = None):
        if config is None:
            full_cfg = load_config()
            self.config = full_cfg.navidrome
        else:
            self.config = config

    def trigger_scan(
        self,
        cli_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> bool:
        """Trigger instant Navidrome library scan using the navidrome CLI binary."""
        binary = cli_path or self.config.cli_path
        cfg_file = config_path or self.config.config_path
        expanded_cfg = Path(os.path.expanduser(cfg_file))

        if not os.path.exists(binary):
            return False

        cmd = [binary, "scan"]
        if expanded_cfg.exists():
            cmd.extend(["--configfile", str(expanded_cfg)])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return res.returncode == 0
        except Exception:
            return False

    def get_starred_tracks(self, db_path: Optional[Path] = None) -> list[Track]:
        """Read starred tracks directly from Navidrome SQLite DB."""
        target_db = db_path or self.config.get_expanded_db_path()
        if not target_db.exists():
            return []

        tracks: list[Track] = []
        try:
            # Read-only URI connection to prevent locking or WAL contention
            conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            music_dir = Path.home() / "Müzik"
            query = """
                SELECT mf.title, mf.artist, mf.album, mf.year, mf.duration, mf.track_number, mf.path
                FROM annotation a
                JOIN media_file mf ON a.item_id = mf.id
                WHERE a.starred = 1 AND (mf.missing IS NULL OR mf.missing = 0)
                ORDER BY a.starred_at DESC
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            for r in rows:
                # Verify physical existence on disk
                rel_path = r["path"]
                if (music_dir / rel_path).exists():
                    tracks.append(
                        Track(
                            title=r["title"],
                            artist=r["artist"],
                            album=r["album"],
                            track_num=r["track_number"] or 1,
                            duration_seconds=int(r["duration"] or 0),
                            year=str(r["year"] or ""),
                        )
                    )
            conn.close()
        except Exception:
            pass
        return tracks
    def get_recently_played_tracks(self, db_path: Optional[Path] = None, limit: int = 20) -> list[Track]:
        """Read recently played tracks directly from Navidrome SQLite DB."""
        target_db = db_path or self.config.get_expanded_db_path()
        if not target_db.exists():
            return []

        tracks: list[Track] = []
        try:
            conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            music_dir = Path.home() / "Müzik"
            query = """
                SELECT mf.title, mf.artist, mf.album, mf.year, mf.duration, mf.track_number, mf.path
                FROM annotation a
                JOIN media_file mf ON a.item_id = mf.id
                WHERE a.play_count > 0 AND a.play_date IS NOT NULL AND (mf.missing IS NULL OR mf.missing = 0)
                ORDER BY a.play_date DESC
                LIMIT ?
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            for r in rows:
                rel_path = r["path"]
                if (music_dir / rel_path).exists():
                    tracks.append(
                        Track(
                            title=r["title"],
                            artist=r["artist"],
                            album=r["album"],
                            track_num=r["track_number"] or 1,
                            duration_seconds=int(r["duration"] or 0),
                            year=str(r["year"] or ""),
                        )
                    )
            conn.close()
        except Exception:
            pass
        return tracks

    def get_all_library_tracks(self, db_path: Optional[Path] = None) -> list[Track]:
        """Read all active non-missing tracks currently in Navidrome library."""
        target_db = db_path or self.config.get_expanded_db_path()
        if not target_db.exists():
            return []

        tracks: list[Track] = []
        try:
            conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            music_dir = Path.home() / "Müzik"
            query = """
                SELECT mf.title, mf.artist, mf.album, mf.year, mf.duration, mf.track_number, mf.path
                FROM media_file mf
                WHERE (mf.missing IS NULL OR mf.missing = 0)
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            for r in rows:
                rel_path = r["path"]
                if (music_dir / rel_path).exists():
                    tracks.append(
                        Track(
                            title=r["title"],
                            artist=r["artist"],
                            album=r["album"],
                            track_num=r["track_number"] or 1,
                            duration_seconds=int(r["duration"] or 0),
                            year=str(r["year"] or ""),
                        )
                    )
            conn.close()
        except Exception:
            pass
        return tracks
