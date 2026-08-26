"""Last.fm recommendation and similarity provider."""

import urllib.parse
from typing import Optional

import requests

from scout.core.config import Config, load_config
from scout.core.models import DiscoveryCandidate, Track


class LastFMProvider:
    BASE_URL = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: Optional[str] = None, config: Optional[Config] = None):
        if api_key:
            self.api_key = api_key
        else:
            cfg = config or load_config()
            self.api_key = cfg.lastfm.api_key

    def _call(self, params: dict) -> Optional[dict]:
        params["api_key"] = self.api_key
        params["format"] = "json"
        try:
            headers = {
                "User-Agent": "ScoutMusicArchiver/1.0 (berk@berkos.local)"
            }
            resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def get_similar_tracks(
        self,
        artist: str,
        title: str,
        limit: int = 10,
    ) -> list[DiscoveryCandidate]:
        params = {
            "method": "track.getsimilar",
            "artist": artist,
            "track": title,
            "limit": limit,
            "autocorrect": 1,
        }
        data = self._call(params)
        if not data or "similartracks" not in data or "track" not in data["similartracks"]:
            return []

        raw_tracks = data["similartracks"]["track"]
        if isinstance(raw_tracks, dict):
            raw_tracks = [raw_tracks]

        candidates: list[DiscoveryCandidate] = []
        for t in raw_tracks:
            t_title = t.get("name", "")
            t_artist = t.get("artist", {}).get("name", "") if isinstance(t.get("artist"), dict) else str(t.get("artist", ""))
            match_score = float(t.get("match", 0.0))

            if not t_title or not t_artist:
                continue

            track = Track(
                title=t_title,
                artist=t_artist,
                source_url=t.get("url", ""),
            )

            candidates.append(
                DiscoveryCandidate(
                    track=track,
                    similarity_score=match_score,
                    seed_track=f"{artist} - {title}",
                    reason=f"Last.fm similarity to {artist} - {title}",
                )
            )

        return candidates

    def get_similar_artists(self, artist: str, limit: int = 10) -> list[dict]:
        params = {
            "method": "artist.getsimilar",
            "artist": artist,
            "limit": limit,
            "autocorrect": 1,
        }
        data = self._call(params)
        if not data or "similarartists" not in data or "artist" not in data["similarartists"]:
            return []

        raw_artists = data["similarartists"]["artist"]
        if isinstance(raw_artists, dict):
            raw_artists = [raw_artists]

        results = []
        for a in raw_artists:
            name = a.get("name", "")
            match = float(a.get("match", 0.0))
            if name:
                results.append({"artist": name, "match": match})
        return results

    def get_top_tags(self, artist: str, title: Optional[str] = None) -> list[str]:
        if title:
            params = {
                "method": "track.gettoptags",
                "artist": artist,
                "track": title,
                "autocorrect": 1,
            }
        else:
            params = {
                "method": "artist.gettoptags",
                "artist": artist,
                "autocorrect": 1,
            }

        data = self._call(params)
        if not data or "toptags" not in data or "tag" not in data["toptags"]:
            return []

        raw_tags = data["toptags"]["tag"]
        if isinstance(raw_tags, dict):
            raw_tags = [raw_tags]

        tags = []
        for tag in raw_tags:
            tag_name = tag.get("name", "")
            if tag_name:
                tags.append(tag_name.lower())
        return tags[:5]
