"""Tests for Subsonic REST API client."""

from scout.core.config import SubsonicConfig
from scout.integrations.subsonic import SubsonicClient


def test_subsonic_auth_params():
    cfg = SubsonicConfig(
        enabled=True,
        url="http://localhost:4533",
        username="testuser",
        password="testpassword",
        salt="somesalt",
    )
    client = SubsonicClient(config=cfg)
    params = client._get_auth_params()

    assert params["u"] == "testuser"
    assert params["s"] == "somesalt"
    assert params["v"] == "1.16.1"
    assert params["c"] == "scout"
    assert params["f"] == "json"
    assert "t" in params
    assert len(params["t"]) == 32  # md5 hex length


def test_subsonic_track_parsing(monkeypatch):
    cfg = SubsonicConfig(
        enabled=True,
        url="http://localhost:4533",
        username="testuser",
        token="testtoken",
        salt="testsalt",
    )
    client = SubsonicClient(config=cfg)

    fake_response = {
        "status": "ok",
        "playlist": {
            "id": "pl1",
            "name": "Test Playlist",
            "entry": [
                {
                    "id": "s1",
                    "title": "Subsonic Song",
                    "artist": "Subsonic Artist",
                    "album": "Subsonic Album",
                    "duration": 210,
                    "year": 2023,
                }
            ],
        },
    }

    monkeypatch.setattr(client, "_call", lambda endpoint, params=None: fake_response)

    tracks = client.get_playlist_tracks("pl1")
    assert len(tracks) == 1
    assert tracks[0].title == "Subsonic Song"
    assert tracks[0].artist == "Subsonic Artist"
    assert tracks[0].album == "Subsonic Album"
    assert tracks[0].duration_seconds == 210
    assert tracks[0].year == "2023"
