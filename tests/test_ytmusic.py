"""Tests for YouTube Music matching and score calculation."""

from scout.providers.ytmusic import calculate_match_score, clean_text_for_matching


def test_clean_text_for_matching():
    assert clean_text_for_matching("Get Lucky (Official Audio)") == "get lucky"
    assert clean_text_for_matching("Eve - Underdog [MV]") == "eve underdog"
    assert clean_text_for_matching("Song Title (feat. Artist)") == "song title"


def test_calculate_match_score():
    # Exact official studio track match
    score_exact = calculate_match_score(
        target_artist="Daft Punk",
        target_title="Get Lucky",
        candidate_artist="Daft Punk",
        candidate_title="Get Lucky",
        result_type="song",
    )
    assert score_exact >= 100.0

    # Live or concert should be penalized heavily
    score_live = calculate_match_score(
        target_artist="Daft Punk",
        target_title="Get Lucky",
        candidate_artist="Daft Punk",
        candidate_title="Get Lucky (Live at Grammy Awards 2014)",
        result_type="video",
    )
    assert score_live < score_exact
    assert score_live < 50.0

    # 8d audio / slowed / reverb penalty
    score_8d = calculate_match_score(
        target_artist="Eve",
        target_title="Underdog",
        candidate_artist="Eve",
        candidate_title="Underdog [8D Audio + Slowed + Reverb]",
        result_type="video",
    )
    assert score_8d < 30.0
