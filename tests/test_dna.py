"""Tests for Playlist DNA Engine."""

from pathlib import Path
from unittest.mock import MagicMock
from scout.core.config import Config
from scout.core.dedupe import HistoryStore
from scout.core.models import DiscoveryCandidate, Track
from scout.dna.engine import PlaylistDNAEngine


def test_dna_engine_mix_generation(tmp_path: Path):
    db_file = tmp_path / "dna_test.db"
    store = HistoryStore(db_path=db_file)
    cfg = Config()

    mock_lastfm = MagicMock()
    mock_ytm = MagicMock()

    # Setup seed tracks
    seed1 = Track(title="Song 1", artist="Seed Artist 1")
    seed2 = Track(title="Song 2", artist="Seed Artist 2")

    # Mock similar tracks for Seed 1: Candidate A (0.8), Candidate B (0.7), Candidate C (0.6)
    cand_a = DiscoveryCandidate(track=Track(title="Track A", artist="Artist Alpha", video_id="vid_a"), similarity_score=0.8)
    cand_b = DiscoveryCandidate(track=Track(title="Track B", artist="Artist Beta", video_id="vid_b"), similarity_score=0.7)
    cand_c1 = DiscoveryCandidate(track=Track(title="Track C1", artist="Artist Gamma", video_id="vid_c1"), similarity_score=0.6)
    cand_c2 = DiscoveryCandidate(track=Track(title="Track C2", artist="Artist Gamma", video_id="vid_c2"), similarity_score=0.5)
    cand_c3 = DiscoveryCandidate(track=Track(title="Track C3", artist="Artist Gamma", video_id="vid_c3"), similarity_score=0.4)

    # For Seed 2: Candidate A also recommended (0.9) -> Cross-seed reinforcement!
    cand_a_seed2 = DiscoveryCandidate(track=Track(title="Track A", artist="Artist Alpha", video_id="vid_a"), similarity_score=0.9)
    cand_d = DiscoveryCandidate(track=Track(title="Track D", artist="Artist Delta", video_id="vid_d"), similarity_score=0.75)

    def fake_get_similar(artist, title, limit=15):
        if artist == "Seed Artist 1":
            return [cand_a, cand_b, cand_c1, cand_c2, cand_c3]
        elif artist == "Seed Artist 2":
            return [cand_a_seed2, cand_d]
        return []

    mock_lastfm.get_similar_tracks = fake_get_similar

    engine = PlaylistDNAEngine(
        config=cfg,
        history_store=store,
        ytmusic_provider=mock_ytm,
        lastfm_provider=mock_lastfm,
    )

    # Run DNA mix generator with max_per_artist=2, count=10
    mix = engine.generate_mix(
        seeds=[seed1, seed2],
        target_count=10,
        max_per_artist=2,
    )

    # 1. Candidate A should be top-ranked due to cross-seed reinforcement (0.8 + 0.9) * 1.3 = 2.21
    assert len(mix) > 0
    assert mix[0].track.title == "Track A"
    assert "Cross-pollinated from 2 seeds" in mix[0].reason

    # 2. Artist Gamma has 3 candidates (C1, C2, C3). With max_per_artist=2, only 2 should be in mix
    gamma_tracks = [m for m in mix if m.track.artist == "Artist Gamma"]
    assert len(gamma_tracks) <= 2

    # 3. Verify seeds were recorded
    assert store.is_seed_processed("Seed Artist 1", "Song 1") is True
    assert store.is_seed_processed("Seed Artist 2", "Song 2") is True

def test_dna_engine_excludes_existing_and_blacklisted(tmp_path: Path):
    db_file = tmp_path / "dna_exclusions.db"
    store = HistoryStore(db_path=db_file)
    cfg = Config()
    cfg.general.music_dir = tmp_path / "Music"
    cfg.general.discovery_dir = tmp_path / "Discovery"

    # 1. Simulate an existing downloaded track in library
    existing_track = Track(title="Existing Song", artist="Existing Artist", video_id="vid_exist")
    store.record_download(existing_track)

    # 2. Simulate a blacklisted (deleted) track
    store.blacklist("Deleted Artist", "Deleted Song", reason="user_deleted")

    mock_lastfm = MagicMock()
    mock_ytm = MagicMock()

    seed = Track(title="My Seed", artist="Seed Artist")

    # Recommendations include:
    # - existing track (should be excluded)
    # - blacklisted/deleted track (should be excluded)
    # - brand new discovery track (should be included)
    cand_exist = DiscoveryCandidate(track=existing_track, similarity_score=0.9)
    cand_deleted = DiscoveryCandidate(track=Track(title="Deleted Song", artist="Deleted Artist", video_id="vid_del"), similarity_score=0.85)
    cand_new = DiscoveryCandidate(track=Track(title="Fresh Discovery", artist="New Artist", video_id="vid_new"), similarity_score=0.8)

    mock_lastfm.get_similar_tracks = MagicMock(return_value=[cand_exist, cand_deleted, cand_new])

    engine = PlaylistDNAEngine(
        config=cfg,
        history_store=store,
        ytmusic_provider=mock_ytm,
        lastfm_provider=mock_lastfm,
    )

    mix = engine.generate_mix(seeds=[seed], target_count=5)

    # Assert only the fresh discovery track made it through!
    assert len(mix) == 1
    assert mix[0].track.title == "Fresh Discovery"
    assert mix[0].track.artist == "New Artist"
