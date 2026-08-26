"""Tests for Spotify provider URL detection and parsing logic."""

from scout.providers.spotify import SpotifyProvider


def test_spotify_url_detection():
    assert SpotifyProvider.is_spotify_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") is True
    assert SpotifyProvider.is_spotify_url("https://open.spotify.com/album/4m28RiFD02VwKyEIMvrFsj") is True
    assert SpotifyProvider.is_spotify_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") is True
    assert SpotifyProvider.is_spotify_url("https://www.youtube.com/watch?v=123") is False


def test_spotify_url_type_parser():
    t_type, t_id = SpotifyProvider.parse_url_type("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert t_type == "track"
    assert t_id == "4cOdK2wGLETKBW3PvgPWqT"

    a_type, a_id = SpotifyProvider.parse_url_type("https://open.spotify.com/album/4m28RiFD02VwKyEIMvrFsj")
    assert a_type == "album"
    assert a_id == "4m28RiFD02VwKyEIMvrFsj"


def test_parse_track_embed_json():
    provider = SpotifyProvider()
    fake_embed_html = """
    <html>
      <head>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "state": {
                "data": {
                  "entity": {
                    "name": "Get Lucky",
                    "artists": [{"name": "Daft Punk"}, {"name": "Pharrell Williams"}],
                    "album": {
                      "name": "Random Access Memories",
                      "images": [{"url": "https://i.scdn.co/image/ab67616d0000b273sample"}],
                      "release_date": "2013-05-17"
                    },
                    "duration": 248000,
                    "track_number": 8
                  }
                }
              }
            }
          }
        }
        </script>
      </head>
    </html>
    """
    track = provider._parse_track_embed(fake_embed_html, "test_track_id")
    assert track is not None
    assert track.title == "Get Lucky"
    assert track.artist == "Daft Punk, Pharrell Williams"
    assert track.album == "Random Access Memories"
    assert track.track_num == 8
    assert track.duration_seconds == 248
    assert track.year == "2013"
    assert "sample" in track.cover_url
