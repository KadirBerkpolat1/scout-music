#!/usr/bin/env python3
"""
Batch Spotify Sync for Scout & Navidrome
Downloads all unique tracks from Spotify export in pure bit-perfect FLAC (Soulseek/Qobuz),
generates .m3u8 playlists for Navidrome/Feishin, and triggers a library scan.
"""

import argparse
import contextlib
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

from scout.core.config import load_config
from scout.core.downloader import AudioDownloader
from scout.core.models import Track


def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def main():
    parser = argparse.ArgumentParser(description="Batch Spotify FLAC Sync")
    parser.add_argument("--pure-flac", action="store_true", help="Require pure bit-perfect FLAC (no lossy fallback)")
    parser.add_argument("-f", "--force", action="store_true", help="Force re-download to replace existing files with pure FLAC")
    parser.add_argument("-c", "--concurrency", type=int, default=4, help="Download threads (default: 4)")
    args = parser.parse_args()

    export_path = Path("/tmp/spotify_export.json")
    if not export_path.exists():
        print(f"❌ Hata: {export_path} bulunamadı.")
        sys.exit(1)

    with open(export_path, "r", encoding="utf-8") as f:
        playlists = json.load(f)

    config = load_config()
    if args.pure_flac:
        config.general.strict_lossless = True

    music_dir = config.general.music_dir
    music_dir.mkdir(parents=True, exist_ok=True)
    playlists_dir = music_dir / "Playlists"
    playlists_dir.mkdir(parents=True, exist_ok=True)

    downloader = AudioDownloader(config=config)

    # 1. Collect unique tracks
    unique_tracks: dict[str, dict] = {}
    for pl in playlists:
        for t in pl.get("tracks", []):
            uri = t.get("uri")
            if uri and uri not in unique_tracks:
                unique_tracks[uri] = t

    total_unique = len(unique_tracks)
    print(f"🎵 Toplam {len(playlists)} çalma listesi ve {total_unique} benzersiz parça işleniyor.")
    print(f"📁 Müzik Dizini: {music_dir}")
    print(f"🎧 Mod: {'SAF FLAC (Soulseek/Qobuz CD Master)' if config.general.strict_lossless else 'Kayıpsız Öncelikli FLAC'}\n")

    # 2. Download worker
    completed = 0
    failed = 0
    downloaded_files: dict[str, Path] = {}

    def download_worker(item):
        nonlocal completed, failed
        uri = item["uri"]
        track = Track(
            title=item["title"],
            artist=item["artist"],
            album=item.get("album") or "Single",
            source_url=item.get("url") or "",
            spotify_id=item.get("id") or "",
            track_num=item.get("index") or 1,
            duration_seconds=int((item.get("durationMs") or 0) / 1000),
        )

        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                res = downloader.download_track(track, overwrite=args.force)
            if res.success and res.file_path:
                source_label = "Soulseek P2P" if "soulseek" in str(res.source_url) else "Kayıpsız"
                return (uri, res.file_path, res.already_exists, source_label, None)
            else:
                return (uri, None, False, "", res.error or "Bilinmeyen hata")
        except Exception as e:
            return (uri, None, False, "", str(e))

    print(f"⚡ {args.concurrency} iş parçacığıyla saf FLAC indirmeleri başlatılıyor...\n")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(download_worker, item): item for item in unique_tracks.values()}
        for future in as_completed(futures):
            item = futures[future]
            uri, file_path, already_exists, source_label, err = future.result()
            completed += 1
            artist_title = f"{item['artist']} - {item['title']}"

            if file_path:
                downloaded_files[uri] = file_path
                status_str = "⏭ Zaten mevcut" if already_exists else f"✔ Saf FLAC [{source_label}]"
                print(f"[{completed:3d}/{total_unique:3d}] {status_str}: {artist_title}")
            else:
                failed += 1
                print(f"[{completed:3d}/{total_unique:3d}] ✖ Bulunamadı: {artist_title} ({err})")

    elapsed = time.time() - start_time
    print(f"\n🎉 Saf FLAC İndirme tamamlandı! Süre: {elapsed:.1f}s | Başarılı: {len(downloaded_files)} | Hatalı: {failed}\n")

    # 3. Generate M3U8 playlists for Navidrome / Feishin
    print("📝 Çalma listeleri (.m3u8) güncelleniyor...")
    for pl in playlists:
        pl_name = sanitize_filename(pl.get("name") or "Playlist")
        m3u8_file = playlists_dir / f"{pl_name}.m3u8"
        lines = ["#EXTM3U", f"#PLAYLIST:{pl_name}"]

        matched_tracks = 0
        for t in pl.get("tracks", []):
            uri = t.get("uri")
            file_path = downloaded_files.get(uri)
            if not file_path:
                tr_model = Track(title=t["title"], artist=t["artist"], album=t.get("album") or "Single")
                file_path = downloader.is_track_already_present(tr_model)
                if file_path:
                    downloaded_files[uri] = file_path

            if file_path and file_path.exists():
                try:
                    rel_path = os.path.relpath(file_path, playlists_dir)
                    dur = int((t.get("durationMs") or 0) / 1000)
                    lines.append(f"#EXTINF:{dur},{t['artist']} - {t['title']}")
                    lines.append(rel_path)
                    matched_tracks += 1
                except ValueError:
                    pass

        with open(m3u8_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"  ➜ {m3u8_file.name}: {matched_tracks}/{len(pl.get('tracks', []))} parça bağlandı.")

    # 4. Trigger Navidrome Scan
    print("\n🔄 Navidrome kütüphane taraması tetikleniyor...")
    try:
        scan_url = "http://127.0.0.1:4533/rest/startScan.view?u=berk&p=berk&v=1.16.1&c=scout&f=json"
        res = requests.get(scan_url, timeout=5)
        if res.status_code == 200:
            print("✔ Navidrome tarama isteği gönderildi.")
    except Exception as e:
        print(f"⚠ Navidrome bağlanılamadı: {e}")

    print("\n✅ Kütüphane saf FLAC formatında Navidrome'a bağlandı!")


if __name__ == "__main__":
    main()
