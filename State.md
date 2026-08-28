# Scout (`scout-music`) — Project State & Architectural Blueprint

**Son Güncelleme:** 2026-08-28  
**Mimar:** Jony (Baş Yazılım Mimarı)  
**Kullanıcı:** Berk  
**Durum:** v1.0.1 — Çok Varyantlı Çiftleme Koruması (Multi-Variant Deduplication) & Fiziksel Disk Varlık Tespiti (29/29 Test Yeşil)

---

## 1. Yönetici Özeti (Executive Summary)
Scout (`scout-music`); müzik tutkunları, arşivciler ve self-hoster'lar için geliştirilmiş evrensel bir müzik istihbarat, keşif ve kayıpsız arşivleme motorudur. Spotify zero-API metadata ayrıştırma, Qobuz 24-bit Hi-Res / 16-bit Lossless FLAC stüdyo akışları, YouTube Music stüdyo yedeği, Last.fm duygu ve tür etiket ağırlıklı keşif grafiği, Subsonic/Navidrome sunucu senkronizasyonu ve Linux MPRIS masaüstü entegrasyonunu modern bir CLI ve Textual TUI arayüzünde birleştirir.

---

## 2. Mimari Bileşenler & Modüller

### A. Çok Kaynaklı Kayıpsız İndirme Motoru (`scout/core/downloader.py` & `scout/providers/`)
* **Qobuz Hi-Res FLAC Sağlayıcısı (`scout/providers/qobuz.py`):**
  * Spotube plugin tersine mühendisliği ile 24-bit / 192 kHz stüdyo master ve 16-bit / 44.1 kHz kayıpsız FLAC akış tespiti.
  * Direct stream URL çözümleme ve Vorbis yorum / kapak görseli gömme.
* **YouTube Music Stüdyo Sağlayıcısı (`scout/providers/ytmusic.py`):**
  * Qobuz'da bulunmayan parçalar ve özel yüklemeler için otomatik fallback.
  * Resmi stüdyo parçası eşleştirme (`artist - title` + süre toleransı).
* **Spotify Metadata Ayrıştırıcı (`scout/providers/spotify.py`):**
  * Sıfır API anahtarı gerektiren açık uç nokta ayrıştırması (parçalar, albümler, çalma listeleri) ve 640x640 yüksek çözünürlüklü kapak CDN'i.
* **Stüdyo Kalitesinde Etiketleme (`Mutagen`):**
  * MP3: `TIT2`, `TPE1`, `TALB`, `TRCK`, `TDRC`, `APIC` ID3v2.4 etiketleri.
  * FLAC: Tam Vorbis Comment + FLAC Picture bloğu.

### B. Çalma Listesi DNA Motoru & Duygu Filtreleme (`scout/dna/engine.py`)
* **Tohum Tabanlı Benzerlik Grafiği:**
  * Tohum parçaların Last.fm `track.getSimilar` grafiğini çıkarır; birden fazla tohumla kesişen adaylara çapraz güçlendirme çarpanı (`reinforcement multiplier`) uygular.
* **Ruh Hali (Mood) & Tür Ağırlıklandırması:**
  * Tohumların Last.fm etiketlerinden (`sad`, `melancholy`, `dark`, `emo`, `phonk`, `slowed`, `j-rock`, `alt-rock`, `shoegaze` vb.) duygu profili çıkarır.
  * Duygu profiliyle eşleşen adaylara **1.35x (+%35)** puan bonusu verir.
  * Ana akım `dance pop`, `teen pop`, `party`, `club` adaylarına **0.4x (%60 düşüş)** ceza puanı uygulayarak listeyi saflaştırır.
* **2-Hop Derin Sanatçı Keşfi:**
  * Doğrudan parça benzerliği yetersiz olan niş tohumlarda, Last.fm `artist.getSimilar` $\rightarrow$ `artist.getTopTracks` 2 kademeli grafiğini devreye sokar.
* **Çift Otomatik Çalma Listesi (`M3U8`):**
  * `🆕 Scout Yeni Keşifler.m3u8`: Yalnızca son indirilen keşif grubunu içerir.
  * `✨ Scout Mix.m3u8`: Tüm zamanların kümülatif keşif havuzu.
* **Akıllı Negatif Kara Liste (Blacklist):**
  * Kullanıcının diskten sildiği şarkıları SQLite tablosuna (`blacklist`) kaydeder; bir daha asla önerilmez ve indirilmez.
* **Gelişmiş Sıfır Çiftleme (Zero-Duplicate) & Çok Varyantlı Başlık Eşleme Motoru (`scout/core/dedupe.py`):**
  * Kanji/Romaji (örn: `唱 - Show` $\leftrightarrow$ `Show`), çift dilli başlıklar, parantez içi/köşeli varyantlar ve çoklu sanatçı kombinasyonlarını küme tabanlı (`get_track_keys`) dinamik varyant anahtarlarına dönüştürür.
  * Ağ indirmesi öncesinde hedef dizin (`Keşif`, `Müzik` veya özel klasörler) ve desteklenen tüm ses uzantıları (`.mp3`, `.flac`, `.opus`, `.m4a`, `.ogg`, `.wav`) taranır; diskte mevcut parça tespit edildiğinde indirme atlanır (`already_exists`).
  * CLI komutlarına (`add`, `album`, `radio`, `mix`, `artist`, `mpris`) `--force` / `-f` parametresi eklenerek gerektiğinde zorla yeniden indirme esnekliği sağlandı.
### C. Subsonic & Navidrome Entegrasyonu (`scout/integrations/subsonic.py`)
* REST API uyumluluğu (Navidrome, Gonic, Airsonic, Funkwhale).
* Tohum çalma listeleri çekme (`🎯 Scout Seed`), keşif listelerini sunucuya enjekte etme ve anlık kütüphane tarama tetikleyicisi (`navidrome scan`).

### D. Linux MPRIS Canlı Radyo Motoru (`scout/integrations/mpris.py`)
* D-Bus MPRIS arayüzü üzerinden Feishin, Spotify, Clementine vb. anlık çalan parçayı okuma ve 1-komutla (`scout mpris`) anında benzer 10 keşif parçasını indirme.

### E. Arayüzler (`scout/cli.py` & `scout/tui/`)
* **CLI:** `rich` tabloları, canlı ilerleme çubukları ve renkli teşhis çıktıları.
* **TUI (`scout tui`):** `Textual` kütüphanesi ile geliştirilmiş tam ekran interaktif arayüz (arama, keşif üretici, indirme yöneticisi, ayar paneli).

---

## 3. Doğrulama ve Test Durumu
* **Birim & Entegrasyon Testleri (`pytest`):**
  * `test_dna.py` (DNA motoru, mood filtreleme, 2-hop keşif) ✅
  * `test_qobuz.py` (Kayıpsız FLAC akış tespiti ve indirme) ✅
  * `test_lastfm.py` (Similar tracks, artist top tracks, tag parsing) ✅
  * `test_downloader.py`, `test_spotify.py`, `test_ytmusic.py` ✅
  * `test_subsonic.py`, `test_mpris.py`, `test_dedupe.py`, `test_config.py`, `test_cli.py`, `test_models.py` ✅
* **Sonuç:** Toplam **29/29 test %100 başarıyla geçti**.
---

## 4. Bekleyen Görevler (Roadmap)
1. Navidrome / Subsonic kütüphane çift yönlü akıllı senkronizasyonu.
2. TUI ekranında parça önizleme (audio preview) ve canlı log akışının zenginleştirilmesi.
3. PyPI / GitHub Releases üzerinde bağımsız paketleme ve dağıtım.
