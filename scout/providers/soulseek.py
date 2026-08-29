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
        clean_artist = re.sub(r",.*|\s+feat\..*|\s+ft\..*|\s*&.*", "", artist, flags=re.IGNORECASE).strip()
        clean_title = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", "", title).strip()
        clean_artist = re.sub(r"[^a-zA-Z0-9\s\u0080-\uffff]", " ", clean_artist)
        clean_title = re.sub(r"[^a-zA-Z0-9\s\u0080-\uffff]", " ", clean_title)
        query = f"{clean_artist} {clean_title}"
        return re.sub(r"\s+", " ", query).strip()

    def generate_search_queries(self, artist: str, title: str) -> list[str]:
        from scout.core.dedupe import extract_title_variants

        clean_artist = re.sub(r",.*|\s+feat\..*|\s+ft\..*|\s*&.*", "", artist, flags=re.IGNORECASE).strip()
        clean_artist = re.sub(r"[^a-zA-Z0-9\s\u0080-\uffff]", " ", clean_artist)
        clean_artist = re.sub(r"\s+", " ", clean_artist).strip()

        title_variants = extract_title_variants(title)
        queries = []

        # 1. First priority: Pure Latin/English title variant if available
        latin_titles = [t for t in title_variants if re.search(r"[a-zA-Z]", t) and not re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", t)]
        if latin_titles:
            best_latin = latin_titles[-1]
            clean_t = re.sub(r"[^a-zA-Z0-9\s]", " ", best_latin)
            clean_t = re.sub(r"\s+", " ", clean_t).strip()
            if clean_artist and clean_t:
                queries.append(f"{clean_artist} - {clean_t}")

        # 2. Second priority: Clean full title without parentheticals
        clean_full = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", "", title).strip()
        if " - " in clean_full:
            clean_full = clean_full.split(" - ", 1)[0].strip()
        clean_full = re.sub(r"[^a-zA-Z0-9\s\u0080-\uffff]", " ", clean_full)
        clean_full = re.sub(r"\s+", " ", clean_full).strip()
        if clean_artist and clean_full:
            q = f"{clean_artist} - {clean_full}"
            if q not in queries:
                queries.append(q)

        if not queries:
            queries.append(f"{clean_artist} - {title}")

        return queries[:2]
    def download_flac(
        self,
        track: Track,
        timeout: Optional[int] = None,
        progress_hook: Optional[any] = None,
    ) -> Optional[Path]:
        """
        Search Soulseek for the track, download genuine lossless FLAC into a temp file,
        and return the Path to the temporary FLAC file.
        """
        if not self.is_available():
            return None

        import random
        exe = self.get_executable()
        timeout_sec = timeout or self.config.timeout_seconds
        search_timeout_ms = min(4000, timeout_sec * 1000)
        queries_to_try = self.generate_search_queries(track.artist, track.title)
        worker_user = f"{self.config.username}_{random.randint(1000, 9999)}"

        with tempfile.TemporaryDirectory(prefix="scout_slsk_") as tmpdir:
            tmp_out_dir = Path(tmpdir)

            for q in queries_to_try:
                cmd = [
                    exe,
                    q,
                    "--song",
                    "--extract-artist",
                    "-d",
                    "--no-listen",
                    "--user", worker_user,
                    "--pass", self.config.password,
                    "-o", str(tmp_out_dir),
                    "--search-timeout", str(search_timeout_ms),
                    "--no-progress",
                    "--fast-search",
                ]

                if self.config.strict_flac:
                    cmd.extend(["--pref-format", "flac"])

                try:
                    import time
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

                    start_t = time.time()
                    max_wait = timeout_sec + 8

                    while proc.poll() is None:
                        files = list(tmp_out_dir.rglob("*.flac*"))
                        if files and progress_hook:
                            curr_bytes = max((f.stat().st_size for f in files if f.is_file()), default=0)
                            if curr_bytes > 0:
                                progress_hook(curr_bytes, 0)

                        time.sleep(0.3)
                        if time.time() - start_t > max_wait:
                            proc.kill()
                            break

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
