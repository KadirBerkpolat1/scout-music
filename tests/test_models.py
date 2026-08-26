"""Tests for domain models."""

from scout.core.models import Album, Artist, DiscoveryCandidate, DownloadResult, Track


def test_track_creation_and_clean_key():
    t = Track(
        title="Get Lucky (feat. Pharrell Williams)",
        artist="Daft Punk",
        album="Random Access Memories",
        track_num=8,
    )
    assert t.title == "Get Lucky (feat. Pharrell Williams)"
    assert t.artist == "Daft Punk"
    assert t.album_artist == "Daft Punk"
    assert t.display_name == "Daft Punk - Get Lucky (feat. Pharrell Williams)"
    assert t.clean_key == "daftpunk:getlucky"


def test_track_dict_roundtrip():
    t1 = Track(
        title="Underdog",
        artist="Eve",
        album="Underdog",
        duration_seconds=193,
        video_id="abc123xyz",
        spotify_id="sp123",
        year="2024",
    )
    d = t1.to_dict()
    t2 = Track.from_dict(d)
    assert t1.title == t2.title
    assert t1.artist == t2.artist
    assert t1.duration_seconds == t2.duration_seconds
    assert t1.video_id == t2.video_id
    assert t1.spotify_id == t2.spotify_id
    assert t1.year == t2.year


def test_album_and_artist_models():
    t1 = Track(title="Song 1", artist="Artist A", track_num=1)
    t2 = Track(title="Song 2", artist="Artist A", track_num=2)
    album = Album(title="Great Album", artist="Artist A", year="2022", tracks=[t1, t2])
    assert album.display_name == "Artist A - Great Album (2022)"
    assert len(album.tracks) == 2

    artist = Artist(name="Artist A", albums=[album])
    assert artist.name == "Artist A"
    assert len(artist.albums) == 1


def test_discovery_candidate_and_download_result():
    t = Track(title="Discovery 1", artist="Artist B")
    c = DiscoveryCandidate(track=t, similarity_score=0.85, seed_track="Seed Artist - Seed Song")
    assert "85%" in c.display_name
    assert c.seed_track == "Seed Artist - Seed Song"

    res = DownloadResult(success=True, track=t)
    assert res.success is True
    assert res.track == t
