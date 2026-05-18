"""
ToonTalk VideoDB Service — the heart of the application.

STORAGE STRATEGY: Local JSON cache + VideoDB as source of truth.

The video content, indexes, and voice clones all live in VideoDB cloud.
We store a tiny JSON file locally that maps video_id → processing state
(scene_index_id, spoken_word_indexed flag, voice ref IDs).

This JSON is purely a CACHE — you can always re-derive it by re-running
the ingest pipeline. The actual heavy assets are in VideoDB.

Recovery path: if local JSON is lost, re-run ingest_pipeline.py --video-id <id>
It will skip already-completed steps (scene index already exists on the video).

JSON shape per video (stored in backend/video_metadata/<video_id>.json):
{
  "video_id": "m-...",
  "name": "shinchan_ep1.mp4",
  "duration": 1320.5,
  "collection_id": "c-...",
  "scene_index_id": "si-...",
  "spoken_word_indexed": true,
  "character_voices": {
    "shinchan": {"ref_audio_url": "...", "ref_audio_id": "...", ...},
    ...
  },
  "processing_status": "ready"
}
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from videodb import (
    IndexType,
    SearchType,
    SceneExtractionType,
)

# SandboxModel removed from videodb 0.4.5 — define constants locally
class SandboxModel:
    GEMMA_4_31B = "gemma-4-31b"
    OMNIVOICE   = "omnivoice"

from sandbox_manager import get_sandbox_manager

logger = logging.getLogger(__name__)

# ─── Scene index VLM prompt ───────────────────────────────────────────────────

SCENE_INDEX_PROMPT = """Analyze this frame from a Hindi cartoon and describe:
1. Which characters are VISIBLE (name them exactly — Shinchan, Doraemon, Nobita, etc.)
2. WHERE each character is on screen (left, center, right, top, bottom)
3. What is HAPPENING in this scene (actions, events)
4. The MOOD/EMOTION of each character (happy, angry, scared, excited, etc.)
5. Any DIALOGUE or speech happening

Respond in this JSON format:
{
  "characters": [
    {"name": "character_name", "position": "left/center/right", "emotion": "emotion", "speaking": true/false}
  ],
  "scene_description": "brief scene description in English",
  "scene_description_hindi": "brief scene description in Hindi",
  "action": "what is happening",
  "mood": "overall scene mood"
}"""

# ─── Local metadata cache ─────────────────────────────────────────────────────

METADATA_DIR = Path(__file__).parent / "video_metadata"
METADATA_DIR.mkdir(exist_ok=True)


class VideoDBService:
    def __init__(self):
        self._manager = get_sandbox_manager()

    def _conn(self):
        return self._manager.get_connection()

    def _coll(self, collection_id: Optional[str] = None):
        conn = self._conn()
        if collection_id:
            return conn.get_collection(collection_id)
        return conn.get_collection()

    # ─── Metadata cache (local JSON) ──────────────────────────────────────────

    def _save_metadata(self, video_id: str, data: dict):
        path = METADATA_DIR / f"{video_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_metadata(self, video_id: str) -> Optional[dict]:
        """
        Load metadata from local JSON cache.
        Returns None if this video has not been processed by ToonTalk yet.
        Fast — pure disk read, no API call needed.
        """
        path = METADATA_DIR / f"{video_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read metadata for {video_id}: {e}")
            return None

    def list_videos(self) -> list[dict]:
        """
        List all ToonTalk-processed videos from local cache.
        Instant — no API call, just reads JSON files.
        """
        videos = []
        for path in sorted(METADATA_DIR.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    videos.append(json.load(f))
            except Exception:
                pass
        return videos

    # ─── Video helper ─────────────────────────────────────────────────────────

    async def _get_video(self, video_id: str, collection_id: Optional[str] = None):
        coll = self._coll(collection_id)
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: coll.get_video(video_id)
        )

    # ─── Video Upload ─────────────────────────────────────────────────────────

    async def upload_video(
        self,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        collection_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> dict:
        """Upload a cartoon episode to VideoDB. Saves initial metadata cache."""
        coll = self._coll(collection_id)
        logger.info(f"Uploading video: {file_path or url}")

        if file_path:
            video = await asyncio.get_event_loop().run_in_executor(
                None, lambda: coll.upload(file_path=file_path)
            )
        elif url:
            video = await asyncio.get_event_loop().run_in_executor(
                None, lambda: coll.upload(url=url)
            )
        else:
            raise ValueError("Either file_path or url must be provided")

        display_name = title.strip() if title and title.strip() else video.name
        metadata = {
            "video_id": video.id,
            "name": display_name,
            "duration": video.length,
            "collection_id": coll.id,
            "scene_index_id": None,
            "spoken_word_indexed": False,
            "character_voices": {},
            "processing_status": "uploaded",
        }
        self._save_metadata(video.id, metadata)
        logger.info(f"Video uploaded: {video.id} (title={display_name})")
        return metadata

    # ─── Scene Indexing ───────────────────────────────────────────────────────

    async def index_scenes(
        self,
        video_id: str,
        collection_id: Optional[str] = None,
    ) -> str:
        """VLM scene indexing using pro model. Saves scene_index_id to cache."""
        video = await self._get_video(video_id, collection_id)
        logger.info(f"Starting scene indexing for {video_id}...")

        index_id = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: video.index_scenes(
                extraction_type=SceneExtractionType.time_based,
                extraction_config={
                    "time": 10,
                    "select_frames": ["first", "middle"],
                    "frame_count": 2,
                },
                model_name="pro",
                prompt=SCENE_INDEX_PROMPT,
            ),
        )

        logger.info(f"Scene index created: {index_id}")
        meta = self.get_metadata(video_id) or {}
        meta["scene_index_id"] = index_id
        meta["processing_status"] = "scene_indexed"
        self._save_metadata(video_id, meta)
        return index_id

    # ─── Spoken Word Indexing ─────────────────────────────────────────────────

    async def index_spoken_words(
        self,
        video_id: str,
        collection_id: Optional[str] = None,
    ) -> bool:
        """Transcribe + index all spoken words. Saves state to cache."""
        video = await self._get_video(video_id, collection_id)
        logger.info(f"Starting spoken word indexing for {video_id}...")

        await asyncio.get_event_loop().run_in_executor(
            None, lambda: video.index_spoken_words()
        )

        meta = self.get_metadata(video_id) or {}
        meta["spoken_word_indexed"] = True
        meta["processing_status"] = "fully_indexed"
        self._save_metadata(video_id, meta)
        logger.info("Spoken word indexing complete.")
        return True

    # ─── Character Auto-Detection ─────────────────────────────────────────────

    async def detect_characters_from_scene_index(
        self,
        video_id: str,
        collection_id: Optional[str] = None,
    ) -> list[str]:
        """
        Scan all VLM scene descriptions to detect which characters appear in this video.

        The VLM scene prompt returns JSON like:
            {"characters": [{"name": "Shinchan", ...}, {"name": "Hiroshi", ...}], ...}

        We parse every scene, collect unique character names, then map them to
        known character keys via ALIAS_TO_CHARACTER registry.

        Returns a list of character_key strings (e.g. ["shinchan", "misae", "kazama"])
        """
        from character_config import ALIAS_TO_CHARACTER, CHARACTER_PERSONAS

        meta = self.get_metadata(video_id)
        if not meta or not meta.get("scene_index_id"):
            logger.warning(f"No scene index for {video_id} — cannot auto-detect characters")
            return []

        video = await self._get_video(video_id, collection_id)
        detected_keys: set[str] = set()
        raw_names_seen: set[str] = set()

        try:
            scene_index = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: video.get_scene_index(meta["scene_index_id"]),
            )
            scenes = scene_index if isinstance(scene_index, list) else []

            for scene in scenes:
                description = (
                    scene.get("description", "")
                    if isinstance(scene, dict)
                    else getattr(scene, "description", "")
                )
                if not description:
                    continue

                # Try parsing as structured JSON first
                try:
                    parsed = json.loads(description)
                    chars_in_scene = parsed.get("characters", [])
                    for c in chars_in_scene:
                        name = (
                            c.get("name", "") if isinstance(c, dict) else str(c)
                        ).strip().lower()
                        if name:
                            raw_names_seen.add(name)
                            if name in ALIAS_TO_CHARACTER:
                                detected_keys.add(ALIAS_TO_CHARACTER[name])
                except (json.JSONDecodeError, AttributeError):
                    # Fallback: scan raw description text for known aliases.
                    # Use whole-word matching only — "dora" must not match "endora",
                    # "mama" must not match "panorama", etc.
                    import re as _re
                    desc_lower = description.lower()
                    for alias, char_key in ALIAS_TO_CHARACTER.items():
                        if alias and len(alias) >= 4:  # skip very short aliases
                            if _re.search(r'\b' + _re.escape(alias) + r'\b', desc_lower):
                                detected_keys.add(char_key)

            # Remove generic fallback from auto-detected set
            detected_keys.discard("generic")

            logger.info(
                f"Auto-detected {len(detected_keys)} characters in {video_id}: "
                f"{sorted(detected_keys)}"
            )

            # Save BOTH mapped keys AND raw VLM names — raw names are used for
            # unknown characters (e.g. Light Yagami, Naruto) not in our registry
            cleaned_raw = sorted({
                n for n in raw_names_seen
                if n and len(n) > 1 and n not in ("unknown", "character", "person")
            })
            logger.info(f"Raw VLM names in {video_id}: {cleaned_raw}")

            meta = self.get_metadata(video_id) or {}
            meta["detected_characters"]     = sorted(detected_keys)
            meta["detected_characters_raw"] = cleaned_raw
            self._save_metadata(video_id, meta)

            return sorted(detected_keys)

        except Exception as e:
            logger.error(f"Character detection from scene index failed: {e}", exc_info=True)
            return []

    # ─── Character Voice Cloning ──────────────────────────────────────────────

    async def clone_character_voice(
        self,
        video_id: str,
        character_name: str,
        collection_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Clone a character's voice using OmniVoice.

        Strategy:
        1. Search the spoken word index using Hindi + English name variants
        2. Take the best 30-45s speech segment as reference audio
        3. Upload the clip to VideoDB as ref_audio
        4. Validate by running a short OmniVoice test generation
        5. Save ref_audio_url + meta to local cache for future use
        """
        coll = self._coll(collection_id)
        video = await self._get_video(video_id, collection_id)
        meta = self.get_metadata(video_id) or {}

        # Already cloned — skip
        if character_name in meta.get("character_voices", {}):
            logger.info(f"Voice clone already exists for {character_name}")
            return meta["character_voices"][character_name].get("ref_audio_url")

        # Check spoken word index exists
        if not meta.get("spoken_word_indexed"):
            logger.warning(f"Spoken word index not ready for {video_id} — skipping voice clone")
            return None

        # ── Step 1: Collect candidate segments from spoken word index ──────────
        # Search with multiple character-specific Hindi queries.
        # Collect up to 10 shots across all queries so we can pick the BEST one.
        VOICE_QUERIES = {
            "shinchan": ["शिनचान", "shin chan", "shinchain", "action kamen", "मम्मा"],
            "misae":    ["मिसाए", "misae", "shinchan", "mama scolding"],
            "hiroshi":  ["हिरोशी", "hiroshi", "papa", "nohara"],
            "nene":     ["नेने", "नेनेचन", "nene", "good girl"],
            "kazama":   ["काज़ामा", "kazama", "friendship"],
            "masao":    ["मासाओ", "masao", "scared"],
            "bo":       ["बो", "bo-chan", "sumo"],
            "doraemon": ["डोरेमोन", "doraemon", "pocket gadget"],
            "nobita":   ["नोबिता", "nobita"],
            "shizuka":  ["शिज़ुका", "shizuka"],
            "gian":     ["जियान", "gian", "takeshi"],
            "suneo":    ["सुनेओ", "suneo"],
        }
        queries = VOICE_QUERIES.get(character_name, [character_name])

        all_shots = []
        for query in queries:
            try:
                results = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda q=query: video.search(
                        q, index_type=IndexType.spoken_word, search_type=SearchType.semantic
                    ),
                )
                shots = getattr(results, "shots", []) or []
                all_shots.extend(shots[:3])  # top 3 per query
                if len(all_shots) >= 9:
                    break
            except Exception:
                continue

        # ── Step 2: Cross-reference with VLM scene index for clean isolation ──
        # For each candidate shot, check: how many OTHER characters are ALSO speaking at that time?
        # Pick the shot with the least cross-speaker contamination.

        best_start, best_end = None, None

        if all_shots and meta.get("scene_index_id"):
            from character_config import ALIAS_TO_CHARACTER
            try:
                scene_index = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: video.get_scene_index(meta["scene_index_id"])
                )
                scenes = scene_index if isinstance(scene_index, list) else []

                # Build a map: video_time → count of OTHER speaking characters
                def count_other_speakers_at(t: float) -> int:
                    for scene in scenes:
                        s_start = scene.get("start", getattr(scene, "start", 0))
                        s_end = scene.get("end", getattr(scene, "end", 0))
                        if s_start <= t <= s_end:
                            desc = scene.get("description", "") if isinstance(scene, dict) else getattr(scene, "description", "")
                            try:
                                parsed = json.loads(desc)
                                others_speaking = sum(
                                    1 for c in parsed.get("characters", [])
                                    if c.get("speaking", False)
                                    and ALIAS_TO_CHARACTER.get(c.get("name", "").lower()) != character_name
                                )
                                return others_speaking
                            except Exception:
                                return 99  # can't parse → skip
                    return 99  # no scene found → skip

                # Score each shot: lower is better (fewer other speakers)
                best_score = 999
                for shot in all_shots:
                    t = getattr(shot, "start", 0)
                    score = count_other_speakers_at(t)
                    if score < best_score:
                        best_score = score
                        best_start = max(0, t)
                        best_end = min(getattr(video, "length", t + 30), t + 30)

                if best_start is not None:
                    logger.info(
                        f"Best segment for {character_name}: [{best_start:.1f}s-{best_end:.1f}s] "
                        f"(other_speakers={best_score})"
                    )
            except Exception as e:
                logger.error(f"VLM cross-ref failed for {character_name}: {e}")

        # Fallback if VLM cross-ref failed or no shots at all
        if best_start is None:
            if all_shots:
                shot = all_shots[0]
                best_start = max(0, getattr(shot, "start", 0))
                best_end = min(getattr(video, "length", best_start + 30), best_start + 30)
                logger.info(f"Fallback: first shot [{best_start:.1f}s-{best_end:.1f}s] for {character_name}")
            else:
                # Absolute last resort: first 30 seconds
                best_start, best_end = 0, min(30, getattr(video, "length", 30))
                logger.warning(f"No speech found for {character_name} — using first 30s")

        start, end = best_start, best_end
        logger.info(f"Extracting [{start:.1f}s - {end:.1f}s] as voice ref for {character_name}")



        try:
            import subprocess
            import tempfile

            # Step A: Get the HLS stream URL for the segment
            stream_url = await asyncio.get_event_loop().run_in_executor(
                None, lambda: video.generate_stream(timeline=[(start, end)])
            )
            logger.info(f"Stream URL for segment [{start:.0f}s-{end:.0f}s]: {str(stream_url)[:80]}")

            # Step B: Download HLS → local MP3 via ffmpeg
            # (VideoDB upload-by-url cannot handle .m3u8 playlists — must download first)
            tmp_audio_path = tempfile.mktemp(suffix=".mp3")

            def _ffmpeg_download():
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(stream_url),
                    "-vn",                   # audio only — strip video track
                    "-acodec", "libmp3lame",
                    "-ar", "22050",          # 22 kHz is enough for voice cloning
                    "-ab", "64k",
                    "-t", str(int(end - start)),
                    tmp_audio_path,
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=120)
                if result.returncode != 0:
                    raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:300]}")
                logger.info(f"ffmpeg extracted audio → {tmp_audio_path}")
                return tmp_audio_path

            await asyncio.get_event_loop().run_in_executor(None, _ffmpeg_download)

            # Step C: Upload the local MP3 to VideoDB as an Audio asset
            ref_audio = await asyncio.get_event_loop().run_in_executor(
                None, lambda: coll.upload(file_path=tmp_audio_path, media_type="audio"),
            )

            # Clean up temp file
            try:
                import os as _os
                _os.unlink(tmp_audio_path)
            except Exception:
                pass

            ref_audio_url = ref_audio.generate_url()
            logger.info(f"Ref audio uploaded for {character_name}: {ref_audio_url[:80]}")

            # Step D: Save to metadata cache immediately
            # No sandbox/OmniVoice needed here — validation happens lazily on first TTS call
            meta = self.get_metadata(video_id) or {}
            meta.setdefault("character_voices", {})[character_name] = {
                "ref_audio_url": ref_audio_url,
                "ref_audio_id": ref_audio.id,
                "sample_start": start,
                "sample_end": end,
            }
            meta["processing_status"] = "ready"
            self._save_metadata(video_id, meta)
            logger.info(f"✅ Voice clone saved for {character_name} — ref_audio ready")

            return ref_audio_url


        except Exception as e:
            logger.error(f"Voice cloning failed for {character_name}: {e}", exc_info=True)
            return None

    # ─── Context Retrieval ────────────────────────────────────────────────────

    def _parse_scene_description(self, description: str) -> Optional[dict]:
        """Parse a VLM scene description string into a dict, stripping markdown fences."""
        clean = description.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            clean = "\n".join(lines).strip()
        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return next(
                    (item for item in parsed if isinstance(item, dict) and item.get("characters")),
                    next((item for item in parsed if isinstance(item, dict)), None),
                )
        except Exception:
            pass
        return {"scene_description": clean, "characters": [], "raw": True}

    async def get_scene_context(
        self,
        video_id: str,
        timestamp: float,
        collection_id: Optional[str] = None,
        window_seconds: float = 10.0,
    ) -> dict:
        """
        Get VLM scene context for a ±window_seconds window around timestamp.
        Merges all scenes that overlap the window so the LLM sees the full
        action happening at that exact moment, not just a single 10s chunk.
        """
        meta = self.get_metadata(video_id)
        if not meta or not meta.get("scene_index_id"):
            return {"scene_description": "Unknown scene", "characters": []}

        video = await self._get_video(video_id, collection_id)
        try:
            scene_index = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: video.get_scene_index(meta["scene_index_id"]),
            )

            scenes = scene_index if isinstance(scene_index, list) else []
            t_min = max(0, timestamp - window_seconds)
            t_max = timestamp + window_seconds

            # Collect all scenes that overlap the ±window window
            window_scenes = []
            fallback_scene = None
            min_diff = float("inf")

            for scene in scenes:
                s_start = scene.get("start", 0) if isinstance(scene, dict) else getattr(scene, "start", 0)
                s_end   = scene.get("end",   0) if isinstance(scene, dict) else getattr(scene, "end",   0)

                if s_start <= t_max and s_end >= t_min:
                    window_scenes.append(scene)

                diff = abs(((s_start + s_end) / 2) - timestamp)
                if diff < min_diff:
                    min_diff = diff
                    fallback_scene = scene

            target_scenes = window_scenes or ([fallback_scene] if fallback_scene else [])
            if not target_scenes:
                return {"scene_description": "Scene at this moment", "characters": []}

            # Parse all scenes and merge into one context dict
            parsed_list = []
            for scene in target_scenes:
                desc = scene.get("description", "") if isinstance(scene, dict) else getattr(scene, "description", "")
                p = self._parse_scene_description(desc)
                if p:
                    parsed_list.append(p)

            if not parsed_list:
                return {"scene_description": "Scene at this moment", "characters": []}

            if len(parsed_list) == 1:
                return parsed_list[0]

            # Merge: union characters, concatenate scene descriptions
            all_chars = []
            seen_names = set()
            descriptions = []
            actions = []
            for p in parsed_list:
                d = p.get("scene_description") or p.get("scene_description_hindi", "")
                if d:
                    descriptions.append(d)
                a = p.get("action", "")
                if a:
                    actions.append(a)
                for c in p.get("characters", []):
                    name = (c.get("name", "") if isinstance(c, dict) else str(c)).lower()
                    if name and name not in seen_names:
                        seen_names.add(name)
                        all_chars.append(c)

            merged = dict(parsed_list[0])
            merged["characters"] = all_chars
            merged["scene_description"] = " | ".join(dict.fromkeys(descriptions))
            if actions:
                merged["action"] = " | ".join(dict.fromkeys(actions))
            logger.info(f"[scene] merged {len(parsed_list)} scenes for t={timestamp:.1f}s window ±{window_seconds}s")
            return merged

        except Exception as e:
            logger.error(f"Scene context retrieval failed: {e}")

        return {"scene_description": "Scene at this moment", "characters": []}

    async def get_detected_characters(
        self,
        video_id: str,
        collection_id: Optional[str] = None,
    ) -> list[str]:
        """Parse all scenes in the scene index to detect which characters are in the video."""
        from character_config import CHARACTER_PERSONAS, CHARACTER_DETECTION_KEYWORDS
        
        meta = self.get_metadata(video_id)
        if not meta or not meta.get("scene_index_id"):
            return []

        video = await self._get_video(video_id, collection_id)
        try:
            scene_index = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: video.get_scene_index(meta["scene_index_id"]),
            )

            scenes = scene_index if isinstance(scene_index, list) else []
            full_text = []
            
            for scene in scenes:
                description = (
                    scene.get("description", "")
                    if isinstance(scene, dict)
                    else getattr(scene, "description", "")
                )
                full_text.append(description)

            scene_text = " ".join(full_text).lower()
            detected_chars = []
            
            for char_key in CHARACTER_PERSONAS.keys():
                if char_key == "generic":
                    continue
                keywords = CHARACTER_DETECTION_KEYWORDS.get(char_key, [char_key])
                if any(kw.lower() in scene_text for kw in keywords):
                    detected_chars.append(char_key)
                    
            return detected_chars

        except Exception as e:
            logger.error(f"Character detection from scene index failed: {e}")
            return []

    async def find_speaking_characters(
        self,
        video_id: str,
        anime_info: dict,
        collection_id: Optional[str] = None,
    ) -> list[str]:
        """
        For each character in anime_info, search their typical_dialogue in the
        spoken word index. Only return slugs of characters who actually have
        matching speech in this specific video clip.

        This prevents extracting 3 voices when only 1 character is speaking
        (e.g. a single-character Death Note clip).
        """
        meta = self.get_metadata(video_id)
        if not meta or not meta.get("spoken_word_indexed"):
            return []

        characters = anime_info.get("characters", [])
        if not characters:
            return []

        video = await self._get_video(video_id, collection_id)
        confirmed_speakers: list[str] = []

        for char in characters:
            slug = char.get("slug", "")
            queries = char.get("typical_dialogue", []) + [slug]
            found = False

            # Semantic search always returns something — check score threshold.
            # A genuine match scores > 0.5; a "closest available" false-positive
            # typically scores < 0.35. We use 0.45 as a conservative cutoff.
            SCORE_THRESHOLD = 0.45
            best_score = 0.0

            for query in queries[:4]:
                if not query.strip():
                    continue
                try:
                    results = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda q=query: video.search(
                            q,
                            index_type=IndexType.spoken_word,
                            search_type=SearchType.semantic,
                        ),
                    )
                    shots = getattr(results, "shots", []) or []
                    for shot in shots[:3]:
                        score = getattr(shot, "score", 0) or 0
                        if score > best_score:
                            best_score = score
                    if best_score >= SCORE_THRESHOLD:
                        found = True
                        break
                except Exception:
                    continue

            logger.info(f"[speaker-check] {slug} best_score={best_score:.3f} → {'✅' if found else '❌'}")

            if found:
                confirmed_speakers.append(slug)
                logger.info(f"[speaker-check] ✅ {slug} has speech in {video_id}")
            else:
                logger.info(f"[speaker-check] ❌ {slug} — no speech found in {video_id}")

        logger.info(
            f"[speaker-check] {len(confirmed_speakers)}/{len(characters)} characters "
            f"confirmed speaking in {video_id}: {confirmed_speakers}"
        )
        return confirmed_speakers

    async def detect_language_from_spoken_index(
        self,
        video_id: str,
        collection_id: Optional[str] = None,
    ) -> str:
        """
        Sample a few lines from the spoken word index and determine whether
        the video's audio is Hindi or English based on character script.

        Returns "hindi", "english", or "unknown".
        """
        meta = self.get_metadata(video_id)
        if not meta or not meta.get("spoken_word_indexed"):
            return "unknown"

        video = await self._get_video(video_id, collection_id)
        try:
            # Search for generic speech to get real dialogue samples
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: video.search(
                    "speaking dialogue",
                    index_type=IndexType.spoken_word,
                    search_type=SearchType.semantic,
                ),
            )
            shots = getattr(results, "shots", []) or []
            sample_lines = [
                getattr(s, "text", "").strip()
                for s in shots[:10]
                if getattr(s, "text", "").strip()
            ]

            if not sample_lines:
                return "unknown"

            combined = " ".join(sample_lines)
            total_chars = len(combined)
            if total_chars == 0:
                return "unknown"

            # Count Devanagari characters (Hindi script: U+0900–U+097F)
            devanagari_count = sum(1 for ch in combined if "ऀ" <= ch <= "ॿ")
            # Count basic ASCII letters (likely English)
            ascii_letter_count = sum(1 for ch in combined if ch.isascii() and ch.isalpha())

            deva_ratio  = devanagari_count / total_chars
            ascii_ratio = ascii_letter_count / total_chars

            if deva_ratio > 0.15:
                lang = "hindi"
            elif ascii_ratio > 0.4:
                lang = "english"
            else:
                lang = "unknown"

            logger.info(
                f"[lang-detect] spoken index sample ({len(sample_lines)} lines): "
                f"deva={deva_ratio:.2f} ascii={ascii_ratio:.2f} → {lang}"
            )
            return lang

        except Exception as e:
            logger.warning(f"[lang-detect] spoken index language detection failed: {e}")
            return "unknown"

    async def get_character_dialogue(
        self,
        video_id: str,
        character_name: str,
        query: str,
        collection_id: Optional[str] = None,
        num_results: int = 5,
        timestamp: Optional[float] = None,
        window_seconds: float = 90.0,
    ) -> list[dict]:
        """
        Semantic search over spoken word index, filtered to ±window_seconds
        of the current timestamp so dialogue is from the actual scene.
        """
        meta = self.get_metadata(video_id)
        if not meta or not meta.get("spoken_word_indexed"):
            return []

        video = await self._get_video(video_id, collection_id)
        try:
            # If character_name is empty, search by question text only (all-speaker mode)
            search_query = f"{character_name} {query}".strip() if character_name else query
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: video.search(
                    search_query,
                    index_type=IndexType.spoken_word,
                    search_type=SearchType.semantic,
                ),
            )

            shots = results.shots if results else []

            # Filter to ±window_seconds of current timestamp if provided
            if timestamp is not None:
                t_min = max(0, timestamp - window_seconds)
                t_max = timestamp + window_seconds
                shots = [
                    s for s in shots
                    if t_min <= getattr(s, "start", 0) <= t_max
                ]
                logger.info(f"[dialogue] {len(shots)} shots near t={timestamp:.0f}s (±{window_seconds:.0f}s)")

            return [
                {
                    "text":  getattr(shot, "text", ""),
                    "start": shot.start,
                    "end":   shot.end,
                    "score": getattr(shot, "score", 0),
                }
                for shot in shots[:num_results]
            ]
        except Exception as e:
            logger.error(f"Dialogue search failed: {e}")
            return []

    # ─── TTS with Voice Clone ──────────────────────────────────────────────

    # Voice design instructions per character
    _VOICE_INSTRUCTIONS = {
        "shinchan": "Young 5-year-old boy, very playful and mischievous, high-pitched squeaky voice, energetic Hindi-speaking child",
        "misae":    "Adult Indian woman, energetic and expressive, sometimes scolding, warm caring mother voice in Hindi",
        "hiroshi":  "Adult Indian man, tired office worker, calm and mild-mannered Hindi-speaking man",
        "kazama":   "Young intelligent boy, well-spoken and slightly formal, confident Hindi-speaking child",
        "nene":     "Young girl, bossy but sweet, confident and assertive Hindi-speaking child",
        "masao":    "Young timid boy, nervous and slightly whiny, gentle soft Hindi voice",
        "bo":       "Young chubby quiet boy, very few words, calm deep Hindi voice",
        "doraemon": "Friendly robot cat, warm and helpful, slightly robotic but kind Hindi voice",
        "nobita":   "Young boy, slightly whiny and nervous, gentle kind-hearted Hindi voice",
        "shizuka":  "Young girl, sweet and gentle, well-spoken soft Hindi voice",
        "gian":     "Young boy, loud and bold, confident aggressive Hindi voice",
        "suneo":    "Young boy, smug and show-off, slightly nasal Hindi voice",
        "generic":  "Friendly cartoon character, energetic and fun Hindi voice",
    }

    async def generate_character_voice(
        self,
        text: str,
        character_name: str,
        video_id: str,
        collection_id: Optional[str] = None,
        language: str = "hi",
    ) -> Optional[str]:
        """
        FAST path: OmniVoice voice design with character instructions.
        No ref_audio needed — just instructions describing the voice.
        ~30-60s with warm sandbox. Called from /api/generate-tts.
        """
        coll = self._coll(collection_id)
        instructions = self._VOICE_INSTRUCTIONS.get(character_name, self._VOICE_INSTRUCTIONS["generic"])

        try:
            sandbox_id = await self._manager.get_sandbox_id()
            logger.info(f"[TTS] OmniVoice DESIGN for {character_name}...")
            job = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: coll.generate_voice(
                    text=text,
                    model_name=SandboxModel.OMNIVOICE,
                    sandbox_id=sandbox_id,
                    config={
                        "instructions": instructions,
                        "language": language,
                    },
                ),
            )
            audio = await asyncio.get_event_loop().run_in_executor(
                None, lambda: job.wait(timeout=300, interval=5)
            )
            if audio is None:
                logger.warning(f"[TTS] OmniVoice design returned None for {character_name}")
                return None
            url = audio.generate_url()
            logger.info(f"[TTS] OmniVoice design ready for {character_name}: {url[:60]}")
            return url
        except Exception as e:
            logger.error(f"[TTS] OmniVoice design failed for {character_name}: {e}", exc_info=True)
            return None

    async def clone_character_voice(
        self,
        text: str,
        character_name: str,
        video_id: str,
        collection_id: Optional[str] = None,
        language: str = "hi",
    ) -> Optional[str]:
        """
        SLOW path: OmniVoice zero-shot voice clone from episode ref_audio.
        TRUE character voice. Called from /api/clone-voice in background.
        Timeout 900s (15 min) per SDK docs. Returns None if no ref_audio.
        """
        coll = self._coll(collection_id)
        meta = self.get_metadata(video_id)
        voice_data = meta.get("character_voices", {}).get(character_name) if meta else None

        if not voice_data or not (voice_data.get("ref_audio_url") or voice_data.get("ref_audio_id")):
            logger.info(f"[Clone] No ref_audio for {character_name} — skipping clone")
            return None

        # Refresh signed URL via asset ID (GCS URLs expire in 7 days)
        ref_url = voice_data.get("ref_audio_url", "")
        if voice_data.get("ref_audio_id"):
            try:
                ref_audio_asset = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: coll.get_audio(voice_data["ref_audio_id"])
                )
                ref_url = ref_audio_asset.generate_url()
                logger.info(f"[Clone] Refreshed ref_audio URL for {character_name}")
            except Exception as e:
                logger.warning(f"[Clone] Could not refresh ref URL, using cached: {e}")

        ref_text = voice_data.get("ref_text", "")

        try:
            sandbox_id = await self._manager.get_sandbox_id()
            logger.info(f"[Clone] OmniVoice CLONE for {character_name} (sandbox={sandbox_id})...")
            job = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: coll.generate_voice(
                    text=text,
                    model_name=SandboxModel.OMNIVOICE,
                    sandbox_id=sandbox_id,
                    config={
                        "ref_audio": ref_url,
                        "ref_text": ref_text,
                        "language": language,
                    },
                ),
            )
            audio = await asyncio.get_event_loop().run_in_executor(
                None, lambda: job.wait(timeout=900, interval=5)
            )
            if audio is None:
                logger.warning(f"[Clone] OmniVoice returned None for {character_name}")
                return None
            url = audio.generate_url()
            logger.info(f"[Clone] OmniVoice clone ready for {character_name}: {url[:60]}")
            return url
        except Exception as e:
            logger.error(f"[Clone] OmniVoice failed for {character_name}: {e}", exc_info=True)
            return None


    # ─── Per-video voice ref extraction ──────────────────────────────────────────

    REF_AUDIO_DIR = Path(__file__).parent / "char_ref_audio"

    VOICE_QUERIES = {
        "shinchan": ["शिनचान", "shin chan", "shinchain", "action kamen", "मम्मा"],
        "misae":    ["मिसाए", "misae", "shinchan mama", "scolding"],
        "hiroshi":  ["हिरोशी", "hiroshi", "papa", "nohara"],
        "doraemon": ["डोरेमोन", "doraemon", "pocket"],
        "nobita":   ["नोबिता", "nobita"],
        "shizuka":  ["शिज़ुका", "shizuka"],
        "gian":     ["जियान", "gian"],
        "suneo":    ["सुनेओ", "suneo"],
        "kazama":   ["काज़ामा", "kazama"],
        "nene":     ["नेने", "nene"],
    }

    # Generic speech queries used when a character is not in VOICE_QUERIES
    # (e.g. Light Yagami, Naruto, any anime character detected by VLM)
    _GENERIC_SPEECH_QUERIES = ["speaking", "dialogue", "says", "voice", "monologue", "speech"]

    async def extract_character_ref_audio(
        self,
        video_id: str,
        character_name: str,
        collection_id: Optional[str] = None,
        clip_seconds: float = 12.0,
        anime_info: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Find the cleanest solo-speech segment for a character in this video,
        download it as MP3, and save locally.
        anime_info: LLM-inferred character data (includes typical_dialogue used as search queries).
        Returns the local file path, or None on failure. Idempotent.
        """
        self.REF_AUDIO_DIR.mkdir(exist_ok=True)
        out_dir = self.REF_AUDIO_DIR / video_id
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{character_name}.mp3"

        if out_path.exists():
            logger.info(f"[ref-audio] already extracted: {out_path}")
            return str(out_path)

        meta  = self.get_metadata(video_id)
        if not meta or not meta.get("spoken_word_indexed"):
            logger.warning(f"[ref-audio] spoken word index not ready for {video_id}")
            return None

        video = await self._get_video(video_id, collection_id)

        # Build search queries — priority order:
        # 1. LLM-inferred typical_dialogue from anime_info (most accurate for unknown chars)
        # 2. Hardcoded VOICE_QUERIES for known Shinchan/Doraemon chars
        # 3. Generic speech queries as last resort
        anime_char_info = next(
            (c for c in (anime_info or {}).get("characters", []) if c.get("slug") == character_name),
            None,
        )
        if anime_char_info and anime_char_info.get("typical_dialogue"):
            queries = anime_char_info["typical_dialogue"] + [character_name]
            logger.info(f"[ref-audio] using anime_info dialogue queries for {character_name}: {queries[:3]}")
        else:
            queries = self.VOICE_QUERIES.get(
                character_name,
                [character_name] + self._GENERIC_SPEECH_QUERIES,
            )

        # Collect candidate shots
        all_shots = []
        for q in queries:
            try:
                results = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda _q=q: video.search(
                        _q, index_type=IndexType.spoken_word, search_type=SearchType.semantic
                    ),
                )
                shots = getattr(results, "shots", []) or []
                all_shots.extend(shots[:3])
                if len(all_shots) >= 9:
                    break
            except Exception:
                continue

        if not all_shots:
            logger.warning(f"[ref-audio] no speech shots found for {character_name} in {video_id}")
            return None

        # Pick best shot — fewest other simultaneous speakers
        best_start = max(0.0, getattr(all_shots[0], "start", 0.0))
        if meta.get("scene_index_id"):
            from character_config import ALIAS_TO_CHARACTER
            try:
                scene_index = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: video.get_scene_index(meta["scene_index_id"])
                )
                scenes = scene_index if isinstance(scene_index, list) else []

                def _other_speakers(t):
                    for sc in scenes:
                        ss = sc.get("start", getattr(sc, "start", 0)) if isinstance(sc, dict) else getattr(sc, "start", 0)
                        se = sc.get("end",   getattr(sc, "end",   0)) if isinstance(sc, dict) else getattr(sc, "end",   0)
                        if ss <= t <= se:
                            desc = sc.get("description", "") if isinstance(sc, dict) else getattr(sc, "description", "")
                            try:
                                parsed = json.loads(desc)
                                return sum(
                                    1 for c in parsed.get("characters", [])
                                    if c.get("speaking") and ALIAS_TO_CHARACTER.get(c.get("name","").lower()) != character_name
                                )
                            except Exception:
                                return 99
                    return 99

                best_score = 999
                for shot in all_shots:
                    t = max(0.0, getattr(shot, "start", 0.0))
                    score = _other_speakers(t)
                    if score < best_score:
                        best_score = score
                        best_start = t
            except Exception as e:
                logger.warning(f"[ref-audio] VLM cross-ref failed: {e}")

        best_end = min(getattr(video, "length", best_start + clip_seconds), best_start + clip_seconds)
        logger.info(f"[ref-audio] extracting [{best_start:.1f}s-{best_end:.1f}s] for {character_name}")

        try:
            import subprocess, tempfile
            stream_url = await asyncio.get_event_loop().run_in_executor(
                None, lambda: video.generate_stream(timeline=[(best_start, best_end)])
            )
            tmp = tempfile.mktemp(suffix=".mp3")

            def _ffmpeg():
                cmd = [
                    "ffmpeg", "-y", "-i", str(stream_url),
                    "-vn", "-acodec", "libmp3lame",
                    "-ar", "22050", "-ab", "64k",
                    "-t", str(int(best_end - best_start)),
                    tmp,
                ]
                r = subprocess.run(cmd, capture_output=True, timeout=120)
                if r.returncode != 0:
                    raise RuntimeError(f"ffmpeg: {r.stderr.decode()[:200]}")

            await asyncio.get_event_loop().run_in_executor(None, _ffmpeg)

            import shutil
            shutil.move(tmp, str(out_path))
            logger.info(f"[ref-audio] saved {out_path} ({out_path.stat().st_size // 1024} kB)")

            # Save path into metadata
            meta = self.get_metadata(video_id) or {}
            meta.setdefault("character_ref_audio", {})[character_name] = str(out_path)
            self._save_metadata(video_id, meta)
            return str(out_path)

        except Exception as e:
            logger.error(f"[ref-audio] extraction failed for {character_name}: {e}")
            return None

        # ─── Stream URL + Frame ───────────────────────────────────────────────────

    async def get_stream_url(
        self,
        video_id: str,
        collection_id: Optional[str] = None,
    ) -> Optional[str]:
        """Get the HLS stream URL for the full video."""
        video = await self._get_video(video_id, collection_id)
        try:
            return video.generate_stream()
        except Exception as e:
            logger.error(f"Stream URL failed: {e}")
            return None

    async def get_video_frame(
        self,
        video_id: str,
        timestamp: float,
        collection_id: Optional[str] = None,
    ) -> Optional[str]:
        """Get a clip/frame URL around the given timestamp."""
        video = await self._get_video(video_id, collection_id)
        try:
            return video.generate_stream(
                timeline=[(max(0, timestamp - 0.5), timestamp + 0.5)]
            )
        except Exception as e:
            logger.error(f"Frame extraction failed: {e}")
            return None
