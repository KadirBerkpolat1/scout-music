"""Tests for Soulseek Lossless FLAC provider."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from scout.core.config import SoulseekConfig
from scout.core.models import Track
from scout.providers.soulseek import SoulseekFlacProvider


def test_clean_search_query():
    provider = SoulseekFlacProvider()
    assert provider.clean_search_query("Daft Punk feat. Pharrell", "Get Lucky (Radio Edit)") == "Daft Punk Get Lucky"
    assert provider.clean_search_query("Ado, Imagine Dragons", "Show [Official Audio]") == "Ado Show"
    assert provider.clean_search_query("Aimer", "Zankyosanka - TV Version") == "Aimer Zankyosanka TV Version"


def test_soulseek_availability(tmp_path: Path):
    cfg = SoulseekConfig(enabled=True, cli_path=str(tmp_path / "mock_sockseek"))
    provider = SoulseekFlacProvider(config=cfg)
    assert provider.is_available() is False

    # Create mock executable
    mock_bin = tmp_path / "mock_sockseek"
    mock_bin.write_text("#!/bin/sh\nexit 0\n")
    mock_bin.chmod(0o755)
    assert provider.is_available() is True
def test_soulseek_download_mock(tmp_path: Path):
    mock_bin = tmp_path / "mock_sockseek"
    mock_bin.write_text("#!/bin/sh\nexit 0\n")
    mock_bin.chmod(0o755)

    cfg = SoulseekConfig(enabled=True, cli_path=str(mock_bin), timeout_seconds=5)
    provider = SoulseekFlacProvider(config=cfg)

    track = Track(title="Show", artist="Ado")

    with patch("subprocess.run") as mock_run:
        def fake_run(cmd, **kwargs):
            out_dir = Path(cmd[cmd.index("-o") + 1])
            fake_flac = out_dir / "Ado - Show.flac"
            fake_flac.write_bytes(b"fLaC" + b"\x00" * (1024 * 1024 * 2))
            return MagicMock(returncode=0)

        mock_run.side_effect = fake_run
        res_path = provider.download_flac(track)
        assert res_path is not None
        assert res_path.exists()
        assert res_path.suffix == ".flac"
        if res_path.exists():
            res_path.unlink()
