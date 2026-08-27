"""Tests for Qobuz Hi-Res / 16-bit FLAC provider."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from scout.core.config import Config
from scout.core.dedupe import HistoryStore
from scout.core.downloader import AudioDownloader
from scout.core.models import Track
from scout.providers.qobuz import QobuzFlacProvider


def test_qobuz_search_parsing(monkeypatch):
    provider = QobuzFlacProvider()

    fake_search_response = MagicMock()
    fake_search_response.status_code = 200
    fake_search_response.json.return_value = {
        "tracks": [
            {
                "title": "Get Lucky",
                "artist": "Daft Punk ft. Pharrell Williams",
                "album": "Random Access Memories",
                "durationMs": 248000,
                "url": "https://open.qobuz.com/track/8767428",
                "cover": "https://static.qobuz.com/images/covers/sample.jpg",
            }
        ]
    }

    monkeypatch.setattr(provider.session, "get", lambda url, **kwargs: fake_search_response)

    results = provider.search("Daft Punk Get Lucky")
    assert len(results) == 1
    assert results[0]["title"] == "Get Lucky"

    track = provider.search_track("Daft Punk", "Get Lucky")
    assert track is not None
    assert track.title == "Get Lucky"
    assert track.source_url == "https://open.qobuz.com/track/8767428"
    assert track.duration_seconds == 248


def test_qobuz_queue_and_poll(monkeypatch):
    provider = QobuzFlacProvider()

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "/prepare" in url:
            resp.json.return_value = {"t": "test_token_123"}
        elif "/jobs/" in url:
            resp.json.return_value = {
                "status": "done",
                "file": "daft_punk_get_lucky_flac.flac",
                "pretty_name": "Daft Punk - Get Lucky.flac",
            }
        return resp

    def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"id": "job_abc_789"}
        return resp

    monkeypatch.setattr(provider.session, "get", fake_get)
    monkeypatch.setattr(provider.session, "post", fake_post)

    token = provider.get_token()
    assert token == "test_token_123"

    job_id = provider.queue_download("https://open.qobuz.com/track/8767428", "Get Lucky", "Daft Punk", format_id=27)
    assert job_id == "job_abc_789"

    stream_info = provider.poll_job(job_id, format_id=27, max_retries=1, delay=0)
    assert stream_info is not None
    assert "daft_punk_get_lucky_flac.flac" in stream_info["download_url"]
    assert stream_info["container"] == "flac"
    assert stream_info["bit_depth"] == 24
    assert stream_info["sample_rate"] == 192000


def test_qobuz_downloader_lossless_priority(tmp_path: Path, monkeypatch):
    cfg = Config()
    cfg.general.music_dir = tmp_path / "Music"
    cfg.general.discovery_dir = tmp_path / "Discovery"
    cfg.general.lossless_first = True

    history = HistoryStore(db_path=tmp_path / "test_hist.db")
    mock_qobuz = MagicMock()

    mock_qobuz.resolve_flac_stream.return_value = {
        "download_url": "https://flacdownloader.com/qobuz/files/sample.flac",
        "container": "flac",
        "bit_depth": 24,
        "sample_rate": 96000,
        "bitrate": 1411200,
    }

    # Mock requests.get for file streaming
    fake_stream_resp = MagicMock()
    fake_stream_resp.status_code = 200
    fake_stream_resp.iter_content.return_value = [b"FAKE_FLAC_AUDIO_BYTES_HEADER"]

    import requests
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: fake_stream_resp)

    downloader = AudioDownloader(config=cfg, history_store=history, qobuz_provider=mock_qobuz)
    track = Track(title="Show", artist="Ado", source_url="https://open.qobuz.com/track/123")

    res = downloader.download_track(track, target_dir=cfg.general.discovery_dir)
    assert res.success is True
    assert res.file_path.exists()
    assert res.file_path.suffix == ".flac"
    assert history.is_downloaded("Ado", "Show") is True
