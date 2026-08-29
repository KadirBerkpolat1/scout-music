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


def test_parse_playlist_embed_json():
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
                    "title": "Epic Rock Playlist",
                    "subtitle": "Best classic and alternative rock",
                    "visualIdentity": {
                      "image": [{"url": "https://image.spotify.com/cover640"}]
                    },
                    "trackList": [
                      {
                        "title": "Bohemian Rhapsody",
                        "subtitle": "Queen",
                        "duration": 354000,
                        "uri": "spotify:track:4u7EnebtmKWzUH433cf5Qv"
                      },
                      {
                        "title": "Hotel California",
                        "subtitle": "Eagles",
                        "duration": 391000,
                        "uri": "spotify:track:59wf2gXgGf4DqR3L01H89h"
                      }
                    ]
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
    pl = provider._parse_playlist_embed(fake_embed_html, "test_playlist_id")
    assert pl is not None
    assert pl.title == "Epic Rock Playlist"
    assert pl.description == "Best classic and alternative rock"
    assert pl.cover_url == "https://image.spotify.com/cover640"
    assert len(pl.tracks) == 2
    assert pl.tracks[0].title == "Bohemian Rhapsody"
    assert pl.tracks[0].artist == "Queen"
    assert pl.tracks[0].track_num == 1
    assert pl.tracks[0].duration_seconds == 354
    assert pl.tracks[1].title == "Hotel California"
    assert pl.tracks[1].artist == "Eagles"
    assert pl.tracks[1].track_num == 2
