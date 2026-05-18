"""
ToonTalk Flux Image Service
============================
Generates anime character art using VideoDB's built-in Flux image generation.
Uses the same VIDEO_DB_API_KEY — no separate API key needed.

coll.generate_image(prompt, aspect_ratio='3:4') → Image object with .url / .generate_url()
Caches images to disk — each character is generated once.
"""

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_DIR   = Path(__file__).parent
_IMG_DIR    = _BASE_DIR / "character_images"
_INDEX_FILE = _IMG_DIR / "index.json"

_STYLE_SUFFIX = (
    "anime character art, full body portrait, clean pure white background, "
    "no text, no kanji, no japanese characters, no watermark, no title, no logo, "
    "no speech bubbles, vibrant colors, clean lines, expressive face, dynamic confident pose, "
    "detailed shading, professional anime illustration, single character only"
)


class FluxService:
    def __init__(self):
        _IMG_DIR.mkdir(exist_ok=True)

    def _load_index(self) -> dict:
        if _INDEX_FILE.exists():
            try:
                return json.loads(_INDEX_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_index(self, idx: dict):
        _INDEX_FILE.write_text(json.dumps(idx, indent=2), encoding="utf-8")

    def _cache_key(self, character_name: str, anime_name: str) -> str:
        return hashlib.md5(f"{character_name}:{anime_name}".lower().encode()).hexdigest()[:12]

    def get_cached_url(self, character_name: str, anime_name: str = "") -> Optional[str]:
        idx = self._load_index()
        key = self._cache_key(character_name, anime_name)
        fname = idx.get(key)
        if fname and (_IMG_DIR / fname).exists():
            return f"/character-images/{fname}"
        return None

    def generate_character_image(
        self,
        character_name: str,
        anime_name: str = "",
        description: str = "",
        role: str = "",
        collection_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate an anime character portrait via VideoDB Flux (same VIDEO_DB_API_KEY).
        Returns /character-images/<uuid>.jpg URL on success, None on failure.
        Result is cached to disk — same character+anime returns instantly on subsequent calls.
        """
        # Check cache first
        cached = self.get_cached_url(character_name, anime_name)
        if cached:
            logger.info(f"[Flux] cache hit for {character_name}: {cached}")
            return cached

        # Build prompt
        name_part = character_name.replace("_", " ").title()
        show_part = f" from {anime_name}" if anime_name else ""
        desc_part = f", {description}" if description else ""
        role_part = f", {role}" if role else ""
        prompt = f"{name_part}{show_part}{desc_part}{role_part}, {_STYLE_SUFFIX}"

        logger.info(f"[Flux] generating via VideoDB for '{character_name}': {prompt[:100]}...")

        try:
            from sandbox_manager import get_sandbox_manager
            conn = get_sandbox_manager().get_connection()
            coll = conn.get_collection(collection_id) if collection_id else conn.get_collection()

            # VideoDB Flux — aspect_ratio '3:4' is portrait (character art)
            image_obj = coll.generate_image(prompt=prompt, aspect_ratio="3:4")

            # Get accessible URL — try direct url first, fall back to signed URL
            image_url = getattr(image_obj, "url", None)
            if not image_url:
                image_url = image_obj.generate_url()

            if not image_url:
                logger.error(f"[Flux] no URL from VideoDB for {character_name}")
                return None

            # Download and cache locally (signed URLs expire)
            img_resp = httpx.get(image_url, timeout=60.0, follow_redirects=True)
            if img_resp.status_code != 200:
                logger.error(f"[Flux] image download failed: {img_resp.status_code}")
                return None

            # Detect extension from content-type
            content_type = img_resp.headers.get("content-type", "image/jpeg")
            ext = "jpg" if "jpeg" in content_type else "png" if "png" in content_type else "jpg"
            fname = f"{uuid.uuid4().hex}.{ext}"
            (_IMG_DIR / fname).write_bytes(img_resp.content)

            # Save to index
            idx = self._load_index()
            idx[self._cache_key(character_name, anime_name)] = fname
            self._save_index(idx)

            url = f"/character-images/{fname}"
            logger.info(f"[Flux] ✅ {character_name} → {url} ({len(img_resp.content)//1024}kB)")
            return url

        except Exception as e:
            logger.error(f"[Flux] generation failed for '{character_name}': {e}")
            return None


_flux_service: Optional[FluxService] = None


def get_flux_service() -> FluxService:
    global _flux_service
    if _flux_service is None:
        _flux_service = FluxService()
    return _flux_service
