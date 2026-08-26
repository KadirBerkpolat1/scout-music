"""YouTube Music studio searcher and track/album metadata resolver."""

import re
from typing import Optional

from ytmusicapi import YTMusic

from scout.core.models import Album, Artist, Track


def clean_text_for_matching(text: str) -> str:
    cleaned = re.sub(r"[\(\[\{].*?[\)\]\}]", "", text)  # remove parentheticals
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.lower().strip()


def calculate_match_score(
    target_artist: str,
    target_title: str,
    candidate_artist: str,
    candidate_title: str,
    result_type: str = "song",
) -> float:
    score = 0.0
    c_t_art = clean_text_for_matching(target_artist)
    c_t_tit = clean_text_for_matching(target_title)
    c_c_art = clean_text_for_matching(candidate_artist)
    c_c_tit = clean_text_for_matching(candidate_title)

    # Title match
    if c_t_tit == c_c_tit:
        score += 50.0
    elif c_t_tit in c_c_tit or c_c_tit in c_t_tit:
        score += 35.0

    # Artist match
    if c_t_art == c_c_art:
        score += 40.0
    elif c_t_art in c_c_art or c_c_art in c_t_art:
        score += 25.0

    # Bonus for official song vs generic video
    if result_type == "song":
        score += 20.0

    # Penalties for undesirable content
    lowered_cand_title = candidate_title.lower()
    negative_keywords = [
        "live",
        "concert",
        "8d audio",
        "slowed",
        "reverb",
        "sped up",
        "cover",
        "remix",
        "karaoke",
        "instrumental",
        "acoustic",
        "reaction",
    ]
    for kw in negative_keywords:
        if kw in lowered_cand_title and kw not in target_title.lower():
            score -= 45.0

    return score


class YTMusicProvider:
    def __init__(self):
        self._ytm: Optional[YTMusic] = None

    @property
    def ytm(self) -> YTMusic:
        if self._ytm is None:
            self._ytm = YTMusic()
        return self._ytm

    def _extract_cover_url(self, thumbnails: list) -> str:
        if not thumbnails:
            return ""
        # Get highest resolution thumbnail and upgrade resolution if possible
        best = thumbnails[-1].get("url", "")
        if "w120-h120" in best or "w60-h60" in best:
            best = re.sub(r"w\d+-h\d+", "w800-h800", best)
        return best

    def _parse_duration(self, duration_str: str) -> int:
        if not duration_str:
            return 0
        parts = duration_str.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except Exception:
            pass
        return 0

    def search_track(
        self,
        artist: str,
        title: str,
        album: Optional[str] = None,
    ) -> Optional[Track]:
        query = f"{artist} {title}".strip()
        try:
            results = self.ytm.search(query, filter="songs", limit=10)
        except Exception:
            results = []

        if not results:
            # Fallback to general search without filter
            try:
                results = self.ytm.search(query, limit=10)
            except Exception:
                results = []

        if not results:
            return None

        best_match = None
        best_score = -100.0

        for r in results:
            r_type = r.get("resultType", "song")
            r_title = r.get("title", "")
            r_artists = r.get("artists", [])
            r_artist = ", ".join(a.get("name", "") for a in r_artists if a.get("name"))
            r_video_id = r.get("videoId", "")
            if not r_video_id:
                continue

            score = calculate_match_score(
                target_artist=artist,
                target_title=title,
                candidate_artist=r_artist,
                candidate_title=r_title,
                result_type=r_type,
            )

            if score > best_score:
                best_score = score
                r_album = r.get("album", {}).get("name", album or "Single") if r.get("album") else (album or "Single")
                r_thumbnails = r.get("thumbnails", [])
                r_cover = self._extract_cover_url(r_thumbnails)
                r_dur = self._parse_duration(r.get("duration", ""))
                r_year = r.get("year", "")

                best_match = Track(
                    title=r_title,
                    artist=r_artist or artist,
                    album=r_album,
                    album_artist=r_artist or artist,
                    duration_seconds=r_dur,
                    cover_url=r_cover,
                    video_id=r_video_id,
                    source_url=f"https://www.youtube.com/watch?v={r_video_id}",
                    year=str(r_year) if r_year else "",
                    is_studio=(r_type == "song"),
                )

        return best_match

    def search_tracks(self, query: str, limit: int = 10) -> list[Track]:
        tracks: list[Track] = []
        try:
            results = self.ytm.search(query, filter="songs", limit=limit)
        except Exception:
            results = []

        if not results:
            try:
                results = self.ytm.search(query, limit=limit)
            except Exception:
                results = []

        for r in results:
            r_video_id = r.get("videoId", "")
            if not r_video_id:
                continue
            r_title = r.get("title", "")
            r_artists = r.get("artists", [])
            r_artist = ", ".join(a.get("name", "") for a in r_artists if a.get("name"))
            r_album = r.get("album", {}).get("name", "Single") if r.get("album") else "Single"
            r_cover = self._extract_cover_url(r.get("thumbnails", []))
            r_dur = self._parse_duration(r.get("duration", ""))
            r_year = r.get("year", "")

            tracks.append(
                Track(
                    title=r_title,
                    artist=r_artist or "Unknown Artist",
                    album=r_album,
                    album_artist=r_artist or "Unknown Artist",
                    duration_seconds=r_dur,
                    cover_url=r_cover,
                    video_id=r_video_id,
                    source_url=f"https://www.youtube.com/watch?v={r_video_id}",
                    year=str(r_year) if r_year else "",
                    is_studio=(r.get("resultType") == "song"),
                )
            )

        return tracks

    def search_album(self, artist: str, album_title: str) -> Optional[Album]:
        query = f"{artist} {album_title}".strip()
        try:
            results = self.ytm.search(query, filter="albums", limit=5)
        except Exception:
            return None

        if not results:
            return None

        # Pick best album candidate
        best_browse_id = None
        for r in results:
            browse_id = r.get("browseId", "")
            if browse_id:
                best_browse_id = browse_id
                break

        if best_browse_id:
            return self.get_album_by_browse_id(best_browse_id)

        return None

    def get_album_by_browse_id(self, browse_id: str) -> Optional[Album]:
        try:
            album_data = self.ytm.get_album(browse_id)
            if not album_data:
                return None

            title = album_data.get("title", "")
            artists = album_data.get("artists", [])
            artist_name = ", ".join(a.get("name", "") for a in artists if a.get("name"))
            year = str(album_data.get("year", ""))
            cover_url = self._extract_cover_url(album_data.get("thumbnails", []))

            tracks: list[Track] = []
            raw_tracks = album_data.get("tracks", [])
            for idx, t in enumerate(raw_tracks, 1):
                t_video_id = t.get("videoId", "")
                t_title = t.get("title", "")
                t_artists = t.get("artists", [])
                t_artist = ", ".join(a.get("name", "") for a in t_artists if a.get("name")) or artist_name
                t_dur = self._parse_duration(t.get("duration", ""))
                t_num = t.get("trackNumber", idx)

                tracks.append(
                    Track(
                        title=t_title,
                        artist=t_artist,
                        album=title,
                        album_artist=artist_name,
                        track_num=int(t_num),
                        duration_seconds=t_dur,
                        cover_url=cover_url,
                        video_id=t_video_id,
                        source_url=f"https://www.youtube.com/watch?v={t_video_id}" if t_video_id else "",
                        year=year,
                        is_studio=True,
                    )
                )

            return Album(
                title=title,
                artist=artist_name,
                year=year,
                cover_url=cover_url,
                tracks=tracks,
                browse_id=browse_id,
            )
        except Exception:
            return None

    def search_artist(self, artist_name: str) -> Optional[Artist]:
        try:
            results = self.ytm.search(artist_name, filter="artists", limit=3)
            if not results:
                return None

            browse_id = results[0].get("browseId", "")
            if not browse_id:
                return None

            artist_data = self.ytm.get_artist(browse_id)
            if not artist_data:
                return None

            name = artist_data.get("name", artist_name)
            albums: list[Album] = []
            singles: list[Album] = []

            # Extract albums
            if "albums" in artist_data and "results" in artist_data["albums"]:
                for a in artist_data["albums"]["results"]:
                    a_title = a.get("title", "")
                    a_year = str(a.get("year", ""))
                    a_browse_id = a.get("browseId", "")
                    a_cover = self._extract_cover_url(a.get("thumbnails", []))
                    albums.append(
                        Album(
                            title=a_title,
                            artist=name,
                            year=a_year,
                            cover_url=a_cover,
                            browse_id=a_browse_id,
                        )
                    )

            # Extract singles
            if "singles" in artist_data and "results" in artist_data["singles"]:
                for s in artist_data["singles"]["results"]:
                    s_title = s.get("title", "")
                    s_year = str(s.get("year", ""))
                    s_browse_id = s.get("browseId", "")
                    s_cover = self._extract_cover_url(s.get("thumbnails", []))
                    singles.append(
                        Album(
                            title=s_title,
                            artist=name,
                            year=s_year,
                            cover_url=s_cover,
                            browse_id=s_browse_id,
                        )
                    )

            return Artist(
                name=name,
                browse_id=browse_id,
                albums=albums,
                singles=singles,
            )
        except Exception:
            return None

    def get_radio_tracks(self, video_id: str, limit: int = 10) -> list[Track]:
        tracks: list[Track] = []
        try:
            watch_playlist = self.ytm.get_watch_playlist(videoId=video_id, limit=limit + 5)
            if not watch_playlist or "tracks" not in watch_playlist:
                return []

            for t in watch_playlist.get("tracks", []):
                t_video_id = t.get("videoId", "")
                if not t_video_id or t_video_id == video_id:
                    continue  # skip original seed track

                t_title = t.get("title", "")
                t_artists = t.get("artists", [])
                t_artist = ", ".join(a.get("name", "") for a in t_artists if a.get("name"))
                t_album = t.get("album", {}).get("name", "Single") if t.get("album") else "Single"
                t_cover = self._extract_cover_url(t.get("thumbnail", []))
                t_dur = self._parse_duration(t.get("length", ""))

                tracks.append(
                    Track(
                        title=t_title,
                        artist=t_artist or "Unknown Artist",
                        album=t_album,
                        album_artist=t_artist or "Unknown Artist",
                        duration_seconds=t_dur,
                        cover_url=t_cover,
                        video_id=t_video_id,
                        source_url=f"https://www.youtube.com/watch?v={t_video_id}",
                        is_studio=True,
                    )
                )
                if len(tracks) >= limit:
                    break
        except Exception:
            pass
        return tracks
