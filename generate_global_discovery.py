#!/usr/bin/env python3
"""
Global Discovery Engine for Scout & Navidrome
Analyzes Berk's entire music library (136 tracks), builds a global taste matrix,
identifies 25 pure FLAC discovery candidates via Last.fm DNA & Soulseek P2P,
saves them to ~/Music/Keşif/, and creates the "✨ Haftalık Keşif" playlist.
"""

import os
import random
import re
import sys
import time
from pathlib import Path
import requests

from scout.core.config import load_config
from scout.core.downloader import AudioDownloader
from scout.core.models import Track
from scout.dna.engine import PlaylistDNAEngine
from scout.integrations.navidrome import NavidromeScanner


def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def main():
    print("🧠 BerkOS Global Müzik Zevki Analizi Başlatılıyor...")
    config = load_config()
    config.general.strict_lossless = True

    scanner = NavidromeScanner(config=config.navidrome)
    all_tracks = scanner.get_all_library_tracks()

    if not all_tracks:
        print("❌ Kütüphanede hiç parça bulunamadı.")
        sys.exit(1)

    print(f"📊 Kütüphanedeki toplam parça: {len(all_tracks)}")

    # Group tracks by artist to select diverse seeds
    by_artist: dict[str, list[Track]] = {}
    for t in all_tracks:
        by_artist.setdefault(t.artist, []).append(t)

    # Pick top seed candidates across all diverse artists
    seed_pool: list[Track] = []
    for artist, tracks in by_artist.items():
        # Pick up to 2 tracks per artist
        sample = random.sample(tracks, min(2, len(tracks)))
        seed_pool.extend(sample)

    # Shuffle seeds and cap to 40 representative seeds for fast graph traversal
    random.seed(42)
    random.shuffle(seed_pool)
    selected_seeds = seed_pool[:35]

    print(f"🧬 Zevk DNA'sı için {len(selected_seeds)} tohum parça seçildi:")
    for s in selected_seeds[:5]:
        print(f"   • {s.display_name}")
    print("   • ...")

    print("\n🔍 Last.fm & Duygu Haritası üzerinden 25 taze keşif adayı taranıyor...")
    dna_engine = PlaylistDNAEngine(config=config)

    def progress_cb(msg, cur, tot):
        if cur % 5 == 0 or cur == tot:
            print(f"   [{cur}/{tot}] {msg}")

    candidates = dna_engine.generate_mix(
        seeds=selected_seeds,
        target_count=25,
        max_per_artist=2,
        similarity_threshold=0.15,
        progress_callback=progress_cb,
    )

    if not candidates:
        print("⚠ Yeterli keşif adayı bulunamadı, eşik düşürülüyor...")
        candidates = dna_engine.generate_mix(
            seeds=selected_seeds,
            target_count=25,
            max_per_artist=2,
            similarity_threshold=0.08,
        )

    print(f"\n🎯 {len(candidates)} Keşif Adayı Belirlendi:")
    for idx, c in enumerate(candidates, 1):
        print(f"   {idx:2d}. {c.track.display_name} (Puan: {c.similarity_score:.2f} | {c.reason})")

    # 3. Download via Soulseek P2P in pure FLAC
    discovery_dir = config.general.discovery_dir
    discovery_dir.mkdir(parents=True, exist_ok=True)
    downloader = AudioDownloader(config=config)

    print(f"\n⚡ Soulseek P2P üzerinden saf CD Master FLAC indirmeleri başlıyor...")
    print(f"📁 Hedef Klasör: {discovery_dir}\n")

    downloaded_files: list[Path] = []
    for idx, cand in enumerate(candidates, 1):
        track = cand.track
        print(f"[{idx:2d}/{len(candidates):2d}] 🔍 Aranıyor & İndiriliyor: {track.display_name}...")
        try:
            res = downloader.download_track(track, target_dir=discovery_dir)
            if res.success and res.file_path and res.file_path.exists():
                downloaded_files.append(res.file_path)
                size_mb = res.file_path.stat().st_size / (1024 * 1024)
                print(f"     ✔ Saf FLAC İndirildi ({size_mb:.1f} MB): {res.file_path.name}")
            else:
                print(f"     ✖ Atlandı / Bulunamadı: {res.error or 'Soulseek FLAC yok'}")
        except Exception as e:
            print(f"     ✖ Hata: {e}")

    print(f"\n🎉 Toplam {len(downloaded_files)}/{len(candidates)} saf FLAC keşif parçası indirildi!")

    # 4. Generate M3U8 Playlist
    playlists_dir = config.general.music_dir / "Playlists"
    playlists_dir.mkdir(parents=True, exist_ok=True)
    m3u8_path = playlists_dir / "✨ Haftalık Keşif.m3u8"

    lines = ["#EXTM3U", "#PLAYLIST:✨ Haftalık Keşif"]
    for f in downloaded_files:
        try:
            rel_path = os.path.relpath(f, playlists_dir)
            lines.append(f"#EXTINF:-1,{f.stem}")
            lines.append(rel_path)
        except ValueError:
            pass

    with open(m3u8_path, "w", encoding="utf-8") as out_f:
        out_f.write("\n".join(lines) + "\n")

    # Also write to '🆕 Scout Yeni Keşifler.m3u8'
    with open(playlists_dir / "🆕 Scout Yeni Keşifler.m3u8", "w", encoding="utf-8") as out_f:
        out_f.write("\n".join(lines) + "\n")

    print(f"📝 Çalma listesi güncellendi: {m3u8_path.name}")

    # 5. Trigger Navidrome Scan
    print("🔄 Navidrome kütüphanesi taranıyor...")
    try:
        res = requests.get(
            "http://127.0.0.1:4533/rest/startScan.view?u=berk&p=berk&v=1.16.1&c=scout&f=json",
            timeout=5,
        )
        if res.status_code == 200:
            print("✔ Navidrome taraması başlatıldı.")
    except Exception as e:
        print(f"⚠ Navidrome tarama hatası: {e}")

    print("\n✅ Haftalık Keşif kütüphaneye eklendi! Feishin'de dinlemeye hazır.")


if __name__ == "__main__":
    main()
