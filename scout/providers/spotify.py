"""Zero-API Spotify metadata parser extracting high-res covers and track/album info."""

import json
import re
from typing import Optional, Union
import requests

from scout.core.models import Album, Playlist, Track

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class SpotifyProvider:
    @staticmethod
    def is_spotify_url(url: str) -> bool:
        return "open.spotify.com" in url or "spotify.link" in url

    @staticmethod
    def parse_url_type(url: str) -> tuple[Optional[str], Optional[str]]:
        """Returns (entity_type, entity_id) where entity_type is 'track', 'album', or 'playlist'."""
        match = re.search(r"open\.spotify\.com/(track|album|playlist|intl-[a-z]+/track|intl-[a-z]+/album|intl-[a-z]+/playlist)/([a-zA-Z0-9]+)", url)
        if match:
            raw_type, item_id = match.groups()
            entity_type = raw_type.split("/")[-1]
            return entity_type, item_id
        return None, None

    def fetch_page_content(self, url: str) -> Optional[str]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return None

    def fetch_embed_content(self, entity_type: str, item_id: str) -> Optional[str]:
        embed_url = f"https://open.spotify.com/embed/{entity_type}/{item_id}"
        try:
            resp = requests.get(embed_url, headers=HEADERS, timeout=12)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return None

    def get_track(self, url: str) -> Optional[Track]:
        entity_type, item_id = self.parse_url_type(url)
        if entity_type != "track" and not entity_type:
            # Maybe it's a raw query
            return None

        # 1. Try embed page (clean and structured)
        if item_id:
            embed_html = self.fetch_embed_content("track", item_id)
            if embed_html:
                track = self._parse_track_embed(embed_html, item_id)
                if track:
                    return track

        # 2. Try main page
        html = self.fetch_page_content(url)
        if html:
            track = self._parse_track_main(html, item_id or "")
            if track:
                return track

        return None

    def _parse_track_embed(self, html: str, item_id: str) -> Optional[Track]:
        try:
            # Check for __NEXT_DATA__ or json-ld or direct script
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                if entity:
                    title = entity.get("name", "")
                    artists = entity.get("artists", [])
                    artist = ", ".join(a.get("name", "") for a in artists if a.get("name"))
                    album_obj = entity.get("album", {})
                    album = album_obj.get("name", "Single")
                    cover_url = ""
                    images = album_obj.get("images", []) or entity.get("images", [])
                    if images:
                        cover_url = images[0].get("url", "")
                    duration_ms = entity.get("duration", 0)
                    track_num = entity.get("track_number", 1)
                    release_date = album_obj.get("release_date", "")
                    year = release_date[:4] if release_date else ""

                    return Track(
                        title=title,
                        artist=artist,
                        album=album,
                        track_num=track_num,
                        duration_seconds=duration_ms // 1000,
                        cover_url=cover_url,
                        source_url=f"https://open.spotify.com/track/{item_id}",
                        spotify_id=item_id,
                        year=year,
                    )

            # Try JSON-LD
            match = re.search(r'<script type="application/ld\+json">({.*?})</script>', html, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                if data.get("@type") == "MusicRecording":
                    title = data.get("name", "")
                    by_artist = data.get("byArtist", [])
                    if isinstance(by_artist, list):
                        artist = ", ".join(a.get("name", "") for a in by_artist)
                    elif isinstance(by_artist, dict):
                        artist = by_artist.get("name", "")
                    else:
                        artist = str(by_artist)
                    album = data.get("inAlbum", {}).get("name", "Single")
                    cover_url = data.get("image", "")
                    duration_str = data.get("duration", "")  # e.g. PT3M24S
                    return Track(
                        title=title,
                        artist=artist,
                        album=album,
                        cover_url=cover_url,
                        source_url=f"https://open.spotify.com/track/{item_id}",
                        spotify_id=item_id,
                    )
        except Exception:
            pass
        return None

    def _parse_track_main(self, html: str, item_id: str) -> Optional[Track]:
        try:
            # Extract OpenGraph meta tags
            og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            og_desc = re.search(r'<meta property="og:description" content="([^"]+)"', html)
            og_image = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            og_album = re.search(r'<meta property="music:album" content="([^"]+)"', html)

            if og_title:
                title = og_title.group(1).strip()
                artist = ""
                album = "Single"

                if og_desc:
                    desc = og_desc.group(1)
                    # Often "Artist · Song · Year" or "Listen to Title on Spotify. Artist · Song · Year."
                    parts = [p.strip() for p in desc.split("·")]
                    if len(parts) >= 2:
                        artist = parts[0]
                    elif "by" in desc:
                        # e.g., "Song by Artist"
                        m = re.search(r"by\s+([^,.]+)", desc)
                        if m:
                            artist = m.group(1).strip()

                if not artist and " - " in title:
                    # fallback title - artist
                    parts = title.split(" - ")
                    title = parts[0].strip()
                    artist = parts[1].strip()

                cover_url = og_image.group(1) if og_image else ""
                album_name = og_album.group(1) if og_album else album

                return Track(
                    title=title,
                    artist=artist or "Unknown Artist",
                    album=album_name,
                    cover_url=cover_url,
                    source_url=f"https://open.spotify.com/track/{item_id}" if item_id else "",
                    spotify_id=item_id,
                )
        except Exception:
            pass
        return None

    def get_album(self, url: str) -> Optional[Album]:
        entity_type, item_id = self.parse_url_type(url)
        if entity_type != "album" and not entity_type:
            return None
        if item_id:
            embed_html = self.fetch_embed_content("album", item_id)
            if embed_html:
                album = self._parse_album_embed(embed_html, item_id)
                if album:
                    return album

        # Fallback to main page
        html = self.fetch_page_content(url)
        if html:
            album = self._parse_album_main(html, item_id or "")
            if album:
                return album

        return None

    def _parse_album_embed(self, html: str, item_id: str) -> Optional[Album]:
        try:
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                if entity:
                    album_title = entity.get("name", "")
                    artists = entity.get("artists", [])
                    artist_name = ", ".join(a.get("name", "") for a in artists if a.get("name"))
                    release_date = entity.get("release_date", "")
                    year = release_date[:4] if release_date else ""
                    images = entity.get("images", [])
                    cover_url = images[0].get("url", "") if images else ""

                    raw_tracks = entity.get("trackList", [])
                    tracks: list[Track] = []
                    for idx, t in enumerate(raw_tracks, 1):
                        t_name = t.get("title", "") or t.get("name", "")
                        t_artists = t.get("artists", [])
                        t_artist = ", ".join(a.get("name", "") for a in t_artists if a.get("name")) or artist_name
                        t_dur = t.get("duration", 0) // 1000
                        t_id = t.get("uri", "").split(":")[-1] if "uri" in t else ""
                        tracks.append(
                            Track(
                                title=t_name,
                                artist=t_artist,
                                album=album_title,
                                album_artist=artist_name,
                                track_num=idx,
                                duration_seconds=t_dur,
                                cover_url=cover_url,
                                source_url=f"https://open.spotify.com/track/{t_id}" if t_id else "",
                                spotify_id=t_id,
                                year=year,
                            )
                        )

                    return Album(
                        title=album_title,
                        artist=artist_name,
                        year=year,
                        cover_url=cover_url,
                        tracks=tracks,
                        source_url=f"https://open.spotify.com/album/{item_id}",
                    )
        except Exception:
            pass
        return None

    def _parse_album_main(self, html: str, item_id: str) -> Optional[Album]:
        try:
            og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            og_desc = re.search(r'<meta property="og:description" content="([^"]+)"', html)
            og_image = re.search(r'<meta property="og:image" content="([^"]+)"', html)

            if og_title:
                album_title = og_title.group(1).strip()
                artist = ""
                year = ""
                if og_desc:
                    desc = og_desc.group(1)
                    parts = [p.strip() for p in desc.split("·")]
                    if len(parts) >= 2:
                        artist = parts[0]
                        for p in parts[1:]:
                            if re.match(r"^\d{4}$", p):
                                year = p

                cover_url = og_image.group(1) if og_image else ""
                return Album(
                    title=album_title,
                    artist=artist or "Unknown Artist",
                    year=year,
                    cover_url=cover_url,
                    source_url=f"https://open.spotify.com/album/{item_id}" if item_id else "",
                )
        except Exception:
            pass
        return None

    def get_playlist(self, url: str) -> Optional[Playlist]:
        entity_type, item_id = self.parse_url_type(url)
        if entity_type != "playlist" or not item_id:
            return None
        embed_html = self.fetch_embed_content("playlist", item_id)
        if embed_html:
            pl = self._parse_playlist_embed(embed_html, item_id)
            if pl and pl.tracks:
                return pl
        return None

    def _parse_playlist_embed(self, html: str, item_id: str) -> Optional[Playlist]:
        try:
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group(1))
            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
            if not entity:
                return None

            title = entity.get("title") or entity.get("name") or "Spotify Playlist"
            desc = (entity.get("subtitle") or entity.get("description") or "").replace("\xa0", " ").strip()

            # High-res cover image resolution
            cover_url = ""
            visual_images = entity.get("visualIdentity", {}).get("image", [])
            if visual_images:
                cover_url = visual_images[-1].get("url", "")
            if not cover_url:
                cover_sources = entity.get("coverArt", {}).get("sources", [])
                if cover_sources:
                    cover_url = cover_sources[-1].get("url", "")
            if not cover_url and entity.get("images"):
                cover_url = entity["images"][0].get("url", "")

            tracks: list[Track] = []
            raw_tracks = entity.get("trackList", [])
            for idx, t in enumerate(raw_tracks, 1):
                t_name = t.get("title", "") or t.get("name", "")
                t_subtitle = (t.get("subtitle", "") or "").replace("\xa0", " ").strip()
                t_artists = t.get("artists", [])
                t_artist = ", ".join(a.get("name", "") for a in t_artists if a.get("name"))
                if not t_artist and t_subtitle:
                    t_artist = t_subtitle

                t_dur = t.get("duration", 0) // 1000
                t_id = t.get("uri", "").split(":")[-1] if "uri" in t else ""
                t_cover = ""
                if "album" in t and "images" in t["album"] and t["album"]["images"]:
                    t_cover = t["album"]["images"][0].get("url", "")
                elif cover_url:
                    t_cover = cover_url

                tracks.append(
                    Track(
                        title=t_name,
                        artist=t_artist or "Unknown Artist",
                        track_num=idx,
                        duration_seconds=t_dur,
                        cover_url=t_cover,
                        source_url=f"https://open.spotify.com/track/{t_id}" if t_id else "",
                        spotify_id=t_id,
                    )
                )

            return Playlist(
                title=title,
                tracks=tracks,
                description=desc,
                cover_url=cover_url,
                source_url=f"https://open.spotify.com/playlist/{item_id}",
                spotify_id=item_id,
            )
        except Exception:
            pass
        return None

    def get_playlist_tracks(self, url: str) -> list[Track]:
        pl = self.get_playlist(url)
        return pl.tracks if pl else []
