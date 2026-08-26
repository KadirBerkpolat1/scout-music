"""Tests for Last.fm recommendations parsing."""

from scout.core.models import Track
from scout.providers.lastfm import LastFMProvider


def test_lastfm_parsing_mock(monkeypatch):
    provider = LastFMProvider(api_key="test_key")

    fake_response = {
        "similartracks": {
            "track": [
                {
                    "name": "Lose Yourself to Dance",
                    "match": "0.92",
                    "artist": {"name": "Daft Punk"},
                    "url": "https://www.last.fm/music/Daft+Punk/_/Lose+Yourself+to+Dance",
                },
                {
                    "name": "Instant Crush",
                    "match": "0.85",
                    "artist": {"name": "Daft Punk"},
                    "url": "https://www.last.fm/music/Daft+Punk/_/Instant+Crush",
                },
            ]
        }
    }

    monkeypatch.setattr(provider, "_call", lambda params: fake_response)

    candidates = provider.get_similar_tracks("Daft Punk", "Get Lucky", limit=5)
    assert len(candidates) == 2
    assert candidates[0].track.title == "Lose Yourself to Dance"
    assert candidates[0].track.artist == "Daft Punk"
    assert candidates[0].similarity_score == 0.92
    assert candidates[1].similarity_score == 0.85
