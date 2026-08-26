"""Tests for SQLite history store and deduplication."""

import json
from pathlib import Path
from scout.core.dedupe import HistoryStore, normalize_key
from scout.core.models import Track


def test_normalize_key():
    assert normalize_key("Daft Punk", "Get Lucky!") == "daftpunk:getlucky"
    assert normalize_key("Eve", "Underdog (Official)") == "eve:underdog"


def test_dedupe_record_and_query(tmp_path: Path):
    db_file = tmp_path / "test_history.db"
    store = HistoryStore(db_path=db_file)

    t = Track(title="Show", artist="Ado", album="Zanmu")
    assert store.is_downloaded("Ado", "Show") is False

    store.record_download(t, file_path=tmp_path / "Ado - Show.mp3")
    assert store.is_downloaded("Ado", "Show") is True
    assert store.is_downloaded("ado", "show!") is True

    # Check stats
    stats = store.get_stats()
    assert stats["total_downloads"] == 1
    assert stats["total_seeds"] == 0

    # Seed processing
    assert store.is_seed_processed("Ado", "Show") is False
    store.record_seed("Ado", "Show", reason="test_seed")
    assert store.is_seed_processed("Ado", "Show") is True

    stats = store.get_stats()
    assert stats["total_seeds"] == 1

    # Blacklist
    assert store.is_blacklisted("Spam Artist", "Spam Song") is False
    store.blacklist("Spam Artist", "Spam Song", reason="bad_quality")
    assert store.is_blacklisted("Spam Artist", "Spam Song") is True


def test_legacy_json_migration(tmp_path: Path):
    legacy_json = tmp_path / "scout_history.json"
    legacy_data = {
        "processed_seeds": ["Eve - Underdog", "Ado - Show"],
        "downloaded_tracks": ["Bernth - The Shrine"],
    }
    with open(legacy_json, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)

    db_file = tmp_path / "migrated_history.db"
    store = HistoryStore(db_path=db_file)
    store.migrate_from_legacy_json(legacy_json)

    assert store.is_seed_processed("Eve", "Underdog") is True
    assert store.is_seed_processed("Ado", "Show") is True
    assert store.is_downloaded("Bernth", "The Shrine") is True
