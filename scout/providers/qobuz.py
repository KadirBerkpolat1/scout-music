"""Qobuz Hi-Res and 16-bit Lossless FLAC provider via FlacDownloader API."""

import re
import time
from typing import Optional

import requests

from scout.core.models import Track
from scout.providers.ytmusic import calculate_match_score


class QobuzFlacProvider:
    BASE_URL = "https://flacdownloader.com"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://flacdownloader.com/",
            "Origin": "https://flacdownloader.com",
            "Accept": "application/json, text/plain, */*",
        }

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search Qobuz catalog via FlacDownloader API."""
        if not query.strip():
            return []

        url = f"{self.BASE_URL}/api/qobuz/search"
        params = {"q": query.strip(), "offset": 0, "limit": limit}

        try:
            resp = self.session.get(url, params=params, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "tracks" in data:
                    return data["tracks"]
        except Exception:
            pass
        return []

    def search_track(self, artist: str, title: str) -> Optional[Track]:
        """Find best matching Qobuz track with studio metadata."""
        query = f"{artist} {title}".strip()
        results = self.search(query, limit=10)
        if not results:
            return None

        best_match = None
        best_score = -100.0

        for r in results:
            r_title = r.get("title", "")
            r_artist = r.get("artist", "")
            r_url = r.get("url", "")
            if not r_url:
                continue

            score = calculate_match_score(
                target_artist=artist,
                target_title=title,
                candidate_artist=r_artist,
                candidate_title=r_title,
                result_type="song",
            )

            if score > best_score:
                best_score = score
                dur_ms = r.get("durationMs", 0)
                dur_sec = dur_ms // 1000 if dur_ms else 0
                cover = r.get("cover", "")
                album = r.get("album", "Single")

                best_match = Track(
                    title=r_title,
                    artist=r_artist or artist,
                    album=album,
                    album_artist=r_artist or artist,
                    duration_seconds=dur_sec,
                    cover_url=cover,
                    source_url=r_url,
                    is_studio=True,
                )

        return best_match

    def get_token(self) -> Optional[str]:
        """Fetch X-DL-Token from prepare endpoint."""
        url = f"{self.BASE_URL}/prepare"
        try:
            resp = self.session.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "t" in data:
                    return data["t"]
        except Exception:
            pass
        return None

    def queue_download(
        self,
        qobuz_url: str,
        title: str,
        artist: str,
        format_id: int = 27,
        token: Optional[str] = None,
    ) -> Optional[str]:
        """Queue track conversion job on server. Returns job_id."""
        auth_token = token or self.get_token()
        if not auth_token:
            return None

        url = f"{self.BASE_URL}/api/qobuz/queue"
        req_headers = dict(self.headers)
        req_headers["X-DL-Token"] = auth_token
        req_headers["Content-Type"] = "application/json"

        payload = {
            "url": qobuz_url,
            "title": title,
            "artist": artist,
            "formatId": format_id,
        }

        try:
            resp = self.session.post(url, json=payload, headers=req_headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "id" in data:
                    return data["id"]
        except Exception:
            pass
        return None

    def poll_job(self, job_id: str, format_id: int = 27, max_retries: int = 20, delay: float = 1.5) -> Optional[dict]:
        """Poll job status until file is ready."""
        url = f"{self.BASE_URL}/api/qobuz/jobs/{job_id}"

        for _ in range(max_retries):
            try:
                resp = self.session.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "done" and "file" in data:
                        filename = data["file"]
                        pretty_name = data.get("pretty_name", filename)
                        download_url = f"{self.BASE_URL}/qobuz/files/{filename}?name={pretty_name}"

                        sample_rate = 192000 if format_id == 27 else (96000 if format_id == 7 else 44100)
                        bit_depth = 24 if format_id in (27, 7) else 16
                        container = "mp3" if format_id == 5 else "flac"

                        return {
                            "download_url": download_url,
                            "container": container,
                            "bit_depth": bit_depth,
                            "sample_rate": sample_rate,
                            "bitrate": 320000 if format_id == 5 else 1411200,
                            "filename": filename,
                        }
                    elif data.get("status") == "error":
                        return None
            except Exception:
                pass
            time.sleep(delay)

        return None

    def resolve_flac_stream(
        self,
        track: Track,
        preferred_format_ids: Optional[list[int]] = None,
    ) -> Optional[dict]:
        """
        Attempts to resolve a true lossless FLAC stream URL for the given track.
        Tries 24-bit 192kHz (27), 24-bit 96kHz (7), and 16-bit 44.1kHz (6) with automatic fallback.
        """
        qobuz_url = track.source_url
        if not qobuz_url or "qobuz.com" not in qobuz_url:
            # Search Qobuz first
            matched = self.search_track(track.artist, track.title)
            if not matched or not matched.source_url:
                return None
            qobuz_url = matched.source_url
            if not track.cover_url and matched.cover_url:
                track.cover_url = matched.cover_url
            if not track.album or track.album == "Single":
                track.album = matched.album

        format_candidates = preferred_format_ids or [27, 7, 6]
        token = self.get_token()

        for fmt in format_candidates:
            job_id = self.queue_download(
                qobuz_url=qobuz_url,
                title=track.title,
                artist=track.artist,
                format_id=fmt,
                token=token,
            )
            if job_id:
                stream_info = self.poll_job(job_id, format_id=fmt)
                if stream_info:
                    return stream_info

        return None
