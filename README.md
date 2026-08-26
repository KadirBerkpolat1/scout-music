# 🎯 Scout (`scout-music`)
> **Universal Music Discovery & Archiving Engine**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: >=3.10](https://img.shields.io/badge/Python->=3.10-green.svg)](https://python.org)

Scout is an open-source, modular music intelligence and archival system designed for audiophiles, self-hosters, and power listeners. It unites Spotify zero-API metadata parsing, YouTube Music official studio track matching, Last.fm recommendation graph weighting, Subsonic/Navidrome server synchronization, and Linux MPRIS desktop integration into an intuitive CLI and Textual TUI.

---

## ✨ Key Features

1. **Universal Downloader & Studio ID3 Tagger**
   - Downloads official 320kbps MP3 / FLAC / Opus tracks via `yt-dlp`.
   - Zero-API Spotify parser (tracks, albums, playlists) with 640x640 CDN artwork.
   - Smart YouTube Music studio audio matching (filters out live recordings, phone covers, and low-res rips).
   - Studio-grade tagging with Mutagen: `TIT2`, `TPE1`, `TALB`, `TRCK`, `TDRC`, `APIC` cover embedding.

2. **🧬 Playlist DNA Engine (`Scout Mix`)**
   - Takes your favorite seed tracks or Subsonic seed playlists.
   - Computes an affinity graph across Last.fm similar tracks and genre tags.
   - Enforces artist diversity constraints (max 2 tracks per artist) and deduplicates against your history SQLite DB.
   - Resolves candidates to official studio tracks and prepares a clean discovery mix.

3. **📡 Subsonic & Local Library Integration**
   - Full REST API client compatible with **Navidrome**, **Gonic**, **Airsonic**, and **Funkwhale**.
   - Syncs seed playlists (`🎯 Scout Seed`), injects discovery mixes (`✨ Scout Mix`), and triggers library rescans.
   - Runs in Standalone Local Folder mode (`~/Music`) if Subsonic is not configured.

4. **⚡ Linux MPRIS Connector**
   - One-command instant radio: `scout mpris` reads currently playing track from Feishin, Spotify, Clementine, or other MPRIS media players and downloads 10 similar discovery tracks.

5. **🖥️ Interactive CLI & Terminal UI (TUI)**
   - Beautiful CLI built with `rich` tables and progress bars.
   - Full-screen interactive Textual TUI (`scout tui`) featuring live search, discovery generator, active downloads, and in-app settings editor.

---

## 🚀 Installation

```bash
git clone https://github.com/berkos/scout-music.git
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
scout tui
# or simply
scout
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
