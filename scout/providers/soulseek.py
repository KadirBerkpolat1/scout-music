"""Soulseek Lossless FLAC provider using headless sockseek CLI engine."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from scout.core.config import SoulseekConfig
from scout.core.models import Track


class SoulseekFlacProvider:
    def __init__(self, config: Optional[SoulseekConfig] = None):
        self.config = config or SoulseekConfig()
    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.config.cli_path:
            cli_bin = Path(self.config.cli_path)
            return cli_bin.exists() and os.access(cli_bin, os.X_OK)
        return shutil.which("sockseek") is not None


    def get_executable(self) -> str:
        cli_bin = Path(self.config.cli_path)
        if cli_bin.exists() and os.access(cli_bin, os.X_OK):
            return str(cli_bin)
        which_bin = shutil.which("sockseek")
        if which_bin:
            return which_bin
        return "/home/sevelebeci/.local/bin/sockseek"

    def clean_search_query(self, artist: str, title: str) -> str:
        # Strip featured artists, parentheticals, and punctuation that might confuse P2P searches
        clean_artist = re.sub(r",.*|\s+feat\..*|\s+ft\..*|\s*&.*", "", artist, flags=re.IGNORECASE).strip()
        clean_title = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", "", title).strip()
        # Remove characters that cause strict delimiter matching in soulseek
        clean_artist = re.sub(r"[^a-zA-Z0-9\s\u0080-\uffff]", " ", clean_artist)
        clean_title = re.sub(r"[^a-zA-Z0-9\s\u0080-\uffff]", " ", clean_title)
        query = f"{clean_artist} {clean_title}"
        return re.sub(r"\s+", " ", query).strip()

    def download_flac(
        self,
        track: Track,
        timeout: Optional[int] = None,
    ) -> Optional[Path]:
        """
        Search Soulseek for the track, download genuine lossless FLAC into a temp file,
        and return the Path to the temporary FLAC file.
        """
        if not self.is_available():
            return None

        exe = self.get_executable()
        timeout_sec = timeout or self.config.timeout_seconds
        search_timeout_ms = min(6000, timeout_sec * 1000)

        # Deduplicate search queries
        raw_queries = [
            self.clean_search_query(track.artist, track.title),
        ]
        if " - " in track.title:
            parts = track.title.split(" - ", 1)
            raw_queries.append(self.clean_search_query(track.artist, parts[1].strip()))
            raw_queries.append(self.clean_search_query(track.artist, parts[0].strip()))

        queries_to_try = []
        for q in raw_queries:
            if q and q not in queries_to_try:
                queries_to_try.append(q)

        with tempfile.TemporaryDirectory(prefix="scout_slsk_") as tmpdir:
            tmp_out_dir = Path(tmpdir)

            for q in queries_to_try:
                cmd = [
                    exe,
                    q,
                    "--song",
                    "--user", self.config.username,
                    "--pass", self.config.password,
                    "-o", str(tmp_out_dir),
                    "--search-timeout", str(search_timeout_ms),
                    "--no-progress",
                    "--fast-search",
                ]

                if self.config.strict_flac:
                    cmd.extend(["--pref-format", "flac"])

                try:
                    subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout_sec + 5,
                    )
                    # Check if a .flac file was downloaded in tmp_out_dir
                    flac_files = list(tmp_out_dir.rglob("*.flac"))
                    valid_flacs = [
                        f for f in flac_files
                        if f.is_file() and f.stat().st_size > 1024 * 1024 and not f.name.endswith(".incomplete")
                    ]

                    if valid_flacs:
                        valid_flacs.sort(key=lambda p: p.stat().st_size, reverse=True)
                        best_flac = valid_flacs[0]

                        persistent_tmp = tempfile.NamedTemporaryFile(suffix=".flac", delete=False)
                        persistent_tmp.close()
                        persistent_path = Path(persistent_tmp.name)
                        shutil.copy2(str(best_flac), str(persistent_path))
                        return persistent_path
                except Exception:
                    continue

        return None
