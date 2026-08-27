# 🎯 Scout (`scout-music`)
> **Universal Music Discovery & Archiving Engine**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: >=3.10](https://img.shields.io/badge/Python->=3.10-green.svg)](https://python.org)

Scout is an open-source, modular music intelligence and archival system designed for audiophiles, self-hosters, and power listeners. It unites Spotify zero-API metadata parsing, YouTube Music official studio track matching, Last.fm recommendation graph weighting, Subsonic/Navidrome server synchronization, and Linux MPRIS desktop integration into an intuitive CLI and Textual TUI.

---

## ✨ Key Features

1. **Universal Lossless & Studio Downloader**
   - **Qobuz 24-bit Hi-Res & 16-bit Lossless FLAC:** Direct studio master stream extraction up to 24-bit / 192 kHz.
   - **YouTube Music Studio Audio:** Automated fallback to 320kbps MP3 / Opus official studio tracks.
   - Zero-API Spotify parser (tracks, albums, playlists) with 640x640 CDN artwork.
   - Studio-grade tagging with Mutagen: `TIT2`, `TPE1`, `TALB`, `TRCK`, `TDRC`, `APIC` cover embedding & Vorbis FLAC tags.
2. **🧬 Playlist DNA Engine & Mood Tag Affinity**
   - Takes your favorite seed tracks, Navidrome starred songs, or Subsonic playlists.
   - Computes an affinity graph across Last.fm similar tracks and genre tags with cross-seed reinforcement multipliers.
   - **Mood & Tag Affinity Filtering:** Analyzes emotional depth (`melancholy`, `dark`, `sad`, `emo`, `phonk`, `slowed`, `j-rock`, `alt-rock`) and boosts matching candidates (+35%) while suppressing generic pop (-60%).
   - **2-Hop Deep Discovery:** Automatically queries related artist discographies when direct similarities are sparse for underground tracks.
   - **Dual Auto-Playlists:** Generates `🆕 Scout Yeni Keşifler.m3u8` (strictly contains the latest downloaded discovery batch) and `✨ Scout Mix.m3u8` (the full ongoing discovery mix archive) for instant playback in Feishin/Navidrome.
   - **Smart Negative Blacklist:** Automatically detects when you delete a disliked track from disk or library, adding it to SQLite blacklist so it is never re-suggested or re-downloaded.
   - **Zero-Duplicate Guarantee:** Multi-layer check against Navidrome database, local filesystem, and history database before any download occurs.
3. **📡 Subsonic & Local Library Integration**
   - Full REST API client compatible with **Navidrome**, **Gonic**, **Airsonic**, and **Funkwhale**.
   - Syncs seed playlists (`🎯 Scout Seed`), injects discovery mixes, and triggers instant library rescans (`navidrome scan`).
   - Runs in Standalone Local Folder mode (`~/Music`) if Subsonic is not configured.

4. **⚡ Linux MPRIS Connector**
   - One-command instant radio: `scout mpris` reads currently playing track from Feishin, Spotify, Clementine, or other MPRIS media players and downloads 10 similar discovery tracks.

5. **🖥️ Interactive CLI & Terminal UI (TUI)**
   - Beautiful CLI built with `rich` tables and progress bars.
   - Full-screen interactive Textual TUI (`scout tui`) featuring live search, discovery generator, active downloads, and in-app settings editor.
---

## 🚀 Installation

```bash
git clone https://github.com/KadirBerkpolat1/scout-music.git
cd scout-music
pip install -e .
```

### Dependencies
- Python `>= 3.10`
- `ffmpeg` installed on your system PATH (for audio conversion and tagging).

---

## 🛠️ Usage

### Interactive TUI
```bash
# Launch full discovery mix based on your active favorites (Default)
scout

# Or launch interactive full-screen TUI Dashboard
scout tui
```

### Command Line Interface
```bash
# Add a single track from Spotify URL or search query
scout add "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
scout add "Daft Punk - Get Lucky"

# Download a complete album into {Artist}/{Album}/
scout album "https://open.spotify.com/album/4m28RiFD02VwKyEIMvrFsj"
scout album "Daft Punk - Random Access Memories"

# Download artist discography
scout artist "Daft Punk"

# Generate 10 similar discovery tracks from a seed track
scout radio "Daft Punk - Get Lucky"

# Run Playlist DNA Engine on Subsonic seed playlist
scout mix --count 20

# Generate discovery radio from currently playing song in Feishin/MPRIS
scout mpris

# Background watcher for Navidrome starred tracks
scout watch

# View download stats and history
scout stats
```

---

## ⚙️ Configuration

Configuration is stored according to XDG standards at `~/.config/scout/config.toml`:

```toml
[general]
music_dir = "~/Music"
discovery_dir = "~/Music/Discovery"
audio_format = "mp3"       # "mp3" (320kbps), "flac", or "opus"
bitrate = "320k"
lossless_first = true      # Try Qobuz 24-bit/16-bit Hi-Res FLAC before YouTube Music
folder_template = "{artist}/{album}/{track_num:02d} - {title}"

[lastfm]
api_key = "d37974f8d011df9bf3e7e993b53143a3"

[subsonic]
enabled = false
url = "http://localhost:4533"
username = "your_user"
token = "your_token"
salt = "your_salt"
seed_playlist = "🎯 Scout Seed"
mix_playlist = "✨ Scout Mix"

[navidrome]
scan_on_download = true
cli_path = "/usr/bin/navidrome"
config_path = "~/.config/navidrome/navidrome.toml"
db_path = "~/.local/share/navidrome/navidrome.db"
```

---

## 🧪 Running Tests

```bash
pytest
```

---

## 📄 License
MIT © Berk
