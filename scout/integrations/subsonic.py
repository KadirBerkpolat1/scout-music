"""Subsonic REST API Client compatible with Navidrome, Gonic, Airsonic, and Funkwhale."""

import hashlib
import secrets
from typing import Any, Optional
import requests

from scout.core.config import Config, SubsonicConfig, load_config
from scout.core.models import Track


class SubsonicClient:
    def __init__(self, config: Optional[SubsonicConfig] = None):
        if config is None:
            full_cfg = load_config()
            self.config = full_cfg.subsonic
        else:
            self.config = config

    @property
    def is_enabled(self) -> bool:
        return bool(self.config.enabled and self.config.url and self.config.username)

    def _get_auth_params(self) -> dict[str, str]:
        username = self.config.username
        salt = self.config.salt
        token = self.config.token

        if not token and self.config.password:
            if not salt:
                salt = secrets.token_hex(6)
            token = hashlib.md5((self.config.password + salt).encode("utf-8")).hexdigest()

        return {
            "u": username,
            "t": token,
            "s": salt,
            "v": "1.16.1",
            "c": "scout",
            "f": "json",
        }

    def _call(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        if not self.is_enabled:
            return None

        url = f"{self.config.url.rstrip('/')}/rest/{endpoint}.view"
        query_params = self._get_auth_params()
        if params:
            query_params.update(params)

        try:
            resp = requests.get(url, params=query_params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                sub_response = data.get("subsonic-response", {})
                if sub_response.get("status") == "ok":
                    return sub_response
        except Exception:
            pass
        return None

    def ping(self) -> bool:
        res = self._call("ping")
        return res is not None and res.get("status") == "ok"

    def get_playlists(self) -> list[dict]:
        res = self._call("getPlaylists")
        if not res or "playlists" not in res:
            return []
        playlists = res["playlists"].get("playlist", [])
        if isinstance(playlists, dict):
            playlists = [playlists]
        return playlists

    def get_playlist_by_name(self, name: str) -> Optional[dict]:
        playlists = self.get_playlists()
        for p in playlists:
            if p.get("name", "").lower() == name.lower():
                return p
        return None

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        res = self._call("getPlaylist", {"id": playlist_id})
        if not res or "playlist" not in res:
            return []

        entries = res["playlist"].get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]

        tracks: list[Track] = []
        for idx, e in enumerate(entries, 1):
            title = e.get("title", "")
            artist = e.get("artist", "")
            album = e.get("album", "Single")
            duration = e.get("duration", 0)
            year = str(e.get("year", ""))
            cover_id = e.get("coverArt", "")
            cover_url = ""
            if cover_id:
                cover_url = f"{self.config.url.rstrip('/')}/rest/getCoverArt.view?id={cover_id}&{urllib_auth(self._get_auth_params())}"

            tracks.append(
                Track(
                    title=title,
                    artist=artist,
                    album=album,
                    track_num=idx,
                    duration_seconds=duration,
                    cover_url=cover_url,
                    year=year,
                )
            )
        return tracks

    def get_starred_tracks(self) -> list[Track]:
        res = self._call("getStarred2") or self._call("getStarred")
        if not res:
            return []

        starred = res.get("starred2", {}) or res.get("starred", {})
        songs = starred.get("song", [])
        if isinstance(songs, dict):
            songs = [songs]

        tracks: list[Track] = []
        for idx, s in enumerate(songs, 1):
            tracks.append(
                Track(
                    title=s.get("title", ""),
                    artist=s.get("artist", ""),
                    album=s.get("album", "Single"),
                    track_num=idx,
                    duration_seconds=s.get("duration", 0),
                    year=str(s.get("year", "")),
                )
            )
        return tracks

    def create_playlist(self, name: str, song_ids: Optional[list[str]] = None) -> Optional[str]:
        params = {"name": name}
        if song_ids:
            # multiple songId params
            for sid in song_ids:
                params["songId"] = sid
        res = self._call("createPlaylist", params)
        if res and "playlist" in res:
            return res["playlist"].get("id")
        return None

    def start_scan(self) -> bool:
        res = self._call("startScan")
        return res is not None and res.get("status") == "ok"


def urllib_auth(params: dict) -> str:
    import urllib.parse
    return urllib.parse.urlencode(params)
