"""Tests for CLI arguments and command resolution."""

import pytest
from scout.cli import main


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        import sys
        sys.argv = ["scout", "--help"]
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "Universal Music Discovery" in captured.out
    assert "add" in captured.out
    assert "album" in captured.out
    assert "radio" in captured.out
    assert "mix" in captured.out
    assert "mpris" in captured.out
    assert "stats" in captured.out
