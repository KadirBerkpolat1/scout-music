"""Tests for SQLite history store and deduplication."""

import json
from pathlib import Path
from scout.core.dedupe import HistoryStore, normalize_key
from scout.core.models import Track


def test_normalize_key():
    assert normalize_key("Daft Punk", "Get Lucky!") == "daftpunk:getlucky"
    assert normalize_key("Eve", "Underdog (Official)") == "eve:underdog"


def test_get_track_keys_variants():
    from scout.core.dedupe import get_track_keys

    keys_ado_simple = get_track_keys("Ado", "Show")
    keys_ado_bilingual = get_track_keys("Ado", "唱 - Show")
    keys_ado_paren = get_track_keys("Ado", "唱 (Show)")
    assert "ado:show" in keys_ado_simple
    assert "ado:show" in keys_ado_bilingual
    assert "ado:show" in keys_ado_paren
    assert bool(keys_ado_simple & keys_ado_bilingual) is True

    keys_aimer_romaji = get_track_keys("Aimer", "Zankyosanka")
    keys_aimer_kanji = get_track_keys("Aimer", "残響散歌 - Zankyosanka")
    assert bool(keys_aimer_romaji & keys_aimer_kanji) is True

    keys_creepy_romaji = get_track_keys("Creepy Nuts", "Daten")
    keys_creepy_kanji = get_track_keys("Creepy Nuts", "堕天 - Daten")
    assert bool(keys_creepy_romaji & keys_creepy_kanji) is True
def test_dedupe_record_and_query(tmp_path: Path):
    db_file = tmp_path / "test_history.db"
    store = HistoryStore(db_path=db_file)

    t = Track(title="Show", artist="Ado", album="Zanmu")
    assert store.is_downloaded("Ado", "Show") is False

    store.record_download(t, file_path=tmp_path / "Ado - Show.mp3")
    assert store.is_downloaded("Ado", "Show") is True
    assert store.is_downloaded("ado", "show!") is True
    # Cross-match variant title (e.g. 唱 - Show)
    assert store.is_downloaded("Ado", "唱 - Show") is True
    assert store.is_downloaded("Ado", "唱 (Show)") is True

    # Check all downloaded keys expansion
    all_keys = store.get_all_downloaded_keys()
    assert "ado:show" in all_keys
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
