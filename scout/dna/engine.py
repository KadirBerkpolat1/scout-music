"""Playlist DNA Engine: builds affinity graph across seed tracks, resolves diversity constraints, and yields discovery mixes."""

import collections
from typing import Callable, Optional

from scout.core.config import Config, load_config
from scout.core.dedupe import HistoryStore, normalize_key
from scout.core.models import DiscoveryCandidate, Track
from scout.providers.lastfm import LastFMProvider
from scout.providers.ytmusic import YTMusicProvider


class PlaylistDNAEngine:
    def __init__(
        self,
        config: Optional[Config] = None,
        history_store: Optional[HistoryStore] = None,
        ytmusic_provider: Optional[YTMusicProvider] = None,
        lastfm_provider: Optional[LastFMProvider] = None,
    ):
        self.config = config or load_config()
        self.history = history_store or HistoryStore()
        self.ytm = ytmusic_provider or YTMusicProvider()
        self.lastfm = lastfm_provider or LastFMProvider(config=self.config)

    def generate_mix(
        self,
        seeds: list[Track],
        target_count: int = 20,
        max_per_artist: int = 2,
        similarity_threshold: float = 0.15,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> list[DiscoveryCandidate]:
        """
        Generate an intelligent discovery mix based on seed tracks.
        """
        if not seeds:
            return []

        total_seeds = len(seeds)
        if progress_callback:
            progress_callback(f"Analyzing {total_seeds} seed tracks...", 0, total_seeds)

        # Build active seed keys to exclude
        seed_keys = {seed.clean_key for seed in seeds}

        # Gather all existing tracks in library (Navidrome DB + local filesystem + history)
        existing_library_keys: set[str] = set(seed_keys)

        try:
            from scout.integrations.navidrome import NavidromeScanner
            scanner = NavidromeScanner(config=self.config.navidrome)
            for lib_track in scanner.get_all_library_tracks():
                existing_library_keys.add(lib_track.clean_key)
        except Exception:
            pass

        # Scan local music and discovery directories for existing files
        for base_dir in [self.config.general.music_dir, self.config.general.discovery_dir]:
            if base_dir and base_dir.exists():
                for ext in ["*.mp3", "*.flac", "*.opus", "*.m4a", "*.ogg"]:
                    for f in base_dir.rglob(ext):
                        stem = f.stem
                        if " - " in stem:
                            parts = stem.split(" - ", 1)
                            clean_artist, clean_title = parts[0].strip(), parts[1].strip()
                            # Strip leading track numbers like "01 - Title"
                            import re
                            clean_artist = re.sub(r"^\d+\s*", "", clean_artist)
                            clean_title = re.sub(r"^\d+\s*", "", clean_title)
                            existing_library_keys.add(normalize_key(clean_artist, clean_title))
                        else:
                            existing_library_keys.add(normalize_key("", stem))

        # Add historical downloads to library keys
        existing_library_keys.update(self.history.get_all_downloaded_keys())

        # Gather all blacklisted / deleted keys
        blacklisted_keys = self.history.get_all_blacklist_keys()

        # Step 1: Feature Extraction across seeds
        candidate_pool: dict[str, list[DiscoveryCandidate]] = collections.defaultdict(list)
        seed_frequencies: dict[str, int] = collections.defaultdict(int)

        for idx, seed in enumerate(seeds, 1):
            if progress_callback:
                progress_callback(f"Extracting DNA for {seed.display_name}...", idx, total_seeds)

            # Record seed in history store
            self.history.record_seed(seed.artist, seed.title, reason="dna_mix_generator")

            # Try Last.fm first
            similar = self.lastfm.get_similar_tracks(seed.artist, seed.title, limit=15)

            # Fallback to YouTube Music Radio if Last.fm yielded zero
            if not similar:
                # Find video_id for seed if missing
                v_id = seed.video_id
                if not v_id:
                    matched = self.ytm.search_track(seed.artist, seed.title)
                    if matched:
                        v_id = matched.video_id

                if v_id:
                    radio_tracks = self.ytm.get_radio_tracks(v_id, limit=15)
                    for r_idx, r_track in enumerate(radio_tracks):
                        # Approximate similarity decay: 1.0 for first track down to 0.4
                        sim_score = max(0.4, 1.0 - (r_idx * 0.04))
                        similar.append(
                            DiscoveryCandidate(
                                track=r_track,
                                similarity_score=sim_score,
                                seed_track=seed.display_name,
                                reason=f"YouTube Music Radio for {seed.display_name}",
                            )
                        )

            for cand in similar:
                c_key = cand.track.clean_key
                # Filter out seeds & existing library tracks
                if c_key in existing_library_keys:
                    continue

                # Filter out blacklisted / deleted tracks
                if c_key in blacklisted_keys or self.history.is_blacklisted(cand.track.artist, cand.track.title):
                    continue

                # Filter out below threshold
                if cand.similarity_score < similarity_threshold:
                    continue

                candidate_pool[c_key].append(cand)
                seed_frequencies[c_key] += 1

        # Step 2: Affinity Graph & Cross-Seed Reinforcement Weighting
        weighted_candidates: list[tuple[float, DiscoveryCandidate]] = []
        recent_downloaded_keys = self.history.get_downloaded_within_days(days=30)

        for c_key, cand_list in candidate_pool.items():
            # Skip if downloaded within last 30 days
            if c_key in recent_downloaded_keys:
                continue

            base_candidate = cand_list[0]
            # Sum of similarity scores
            sum_similarity = sum(c.similarity_score for c in cand_list)

            # Cross-seed reinforcement bonus:
            # If multiple distinct seeds suggested this candidate, it's a taste nexus!
            num_seeds = seed_frequencies[c_key]
            reinforcement_multiplier = 1.0
            if num_seeds == 2:
                reinforcement_multiplier = 1.3
            elif num_seeds >= 3:
                reinforcement_multiplier = 1.6

            composite_weight = sum_similarity * reinforcement_multiplier

            # Reason description
            if num_seeds > 1:
                seeds_str = ", ".join({c.seed_track for c in cand_list if c.seed_track})
                base_candidate.reason = f"Cross-pollinated from {num_seeds} seeds: {seeds_str}"

            base_candidate.similarity_score = composite_weight
            weighted_candidates.append((composite_weight, base_candidate))

        # Sort candidates descending by score
        weighted_candidates.sort(key=lambda x: x[0], reverse=True)

        # Step 3: Artist Diversity Constraint Solving
        selected_candidates: list[DiscoveryCandidate] = []
        artist_counts: dict[str, int] = collections.defaultdict(int)

        # Look for up to target_count * 2 to account for resolution failures
        pool_to_resolve: list[DiscoveryCandidate] = []
        for weight, cand in weighted_candidates:
            norm_artist = cand.track.artist.lower().strip()
            if artist_counts[norm_artist] < max_per_artist:
                artist_counts[norm_artist] += 1
                pool_to_resolve.append(cand)
                if len(pool_to_resolve) >= target_count * 2:
                    break

        if progress_callback:
            progress_callback(
                f"Resolving studio audio for top {len(pool_to_resolve)} candidates...",
                0,
                len(pool_to_resolve),
            )

        # Step 4: Studio Audio Resolution via YouTube Music
        resolved_count = 0
        final_artist_counts: dict[str, int] = collections.defaultdict(int)

        for idx, cand in enumerate(pool_to_resolve, 1):
            if len(selected_candidates) >= target_count:
                break

            if progress_callback:
                progress_callback(
                    f"Verifying studio match for {cand.track.display_name}...",
                    idx,
                    len(pool_to_resolve),
                )

            # If already has valid video_id, check exclusions and keep it
            cand_key = cand.track.clean_key
            if cand_key in existing_library_keys or cand_key in blacklisted_keys:
                continue

            if cand.track.video_id:
                norm_artist = cand.track.artist.lower().strip()
                if final_artist_counts[norm_artist] < max_per_artist:
                    final_artist_counts[norm_artist] += 1
                    selected_candidates.append(cand)
                continue

            # Otherwise resolve against YTM
            matched = self.ytm.search_track(cand.track.artist, cand.track.title)
            if matched and matched.video_id:
                m_key = matched.clean_key
                if m_key in existing_library_keys or m_key in blacklisted_keys:
                    continue

                norm_artist = matched.artist.lower().strip()
                if final_artist_counts[norm_artist] < max_per_artist:
                    final_artist_counts[norm_artist] += 1
                    # Preserve recommendation metadata
                    cand.track = matched
                    selected_candidates.append(cand)

        return selected_candidates
