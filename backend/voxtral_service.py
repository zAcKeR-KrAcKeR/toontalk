"""
ToonTalk Voxtral TTS Service
============================
Uses Mistral SDK → voxtral-mini-tts-2603 with ref_audio for zero-shot voice
cloning directly in each speech.complete() call. NO voice profile registration
needed. Works on the FREE tier.

GUARDRAILS:
- MISTRAL_API_KEY is read ONLY here. Zero other files use it.
- One SDK call per synthesize(). No retries. No loops.
- Hard $1.00 spend cap on Mistral key (safety net — voice creation is free,
  synthesis via this key is pay-as-you-go $16/M chars).
"""

import base64
import json
import logging
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Spend cap ─────────────────────────────────────────────────────────────────

SPEND_LIMIT_USD  = 1.00
SPEND_WARN_USD   = 0.80
PRICE_PER_M_CHAR = 16.00  # $16 / 1M chars

# ── Mistral preset voices (used when no episode ref audio available) ───────────
# These are Mistral's built-in voices for voxtral-mini-tts-2603
_PRESET_VOICES = {
    # Shinchan characters — mapped to real Mistral voice slugs by personality
    "shinchan":  "en_paul_excited",       # hyperactive kid
    "nobita":    "en_paul_sad",           # whiny, clumsy
    "masao":     "en_paul_sad",           # timid
    "bo":        "en_paul_neutral",       # quiet, odd
    "kazama":    "en_paul_confident",     # studious, proud
    "gian":      "gb_oliver_angry",       # loud bully
    "suneo":     "en_paul_happy",         # smug, sly
    "hiroshi":   "en_paul_sad",           # tired salaryman dad
    "doraemon":  "en_paul_confident",     # calm helper robot
    "misae":     "gb_jane_frustrated",    # scolding mom
    "shizuka":   "gb_jane_neutral",       # sweet, polite girl
    "nene":      "gb_jane_confident",     # bossy girl
    "himawari":  "fr_marie_happy",        # baby / cheerful
    # Common anime characters
    "light yagami": "en_paul_confident",   # calm, calculating genius
    "light":        "en_paul_confident",
    "l":            "en_paul_neutral",      # quiet, eccentric detective
    "naruto":       "en_paul_excited",      # loud, energetic ninja
    "goku":         "en_paul_excited",      # enthusiastic fighter
    "vegeta":       "gb_oliver_angry",      # proud, intense
    "sasuke":       "en_paul_confident",    # cold, serious
    "itachi":       "en_paul_neutral",      # calm, stoic
    "eren":         "en_paul_confident",    # determined, intense
    # fallback
    "generic":      "en_paul_neutral",
}

_BASE_DIR   = Path(__file__).parent
_CACHE_DIR  = _BASE_DIR / "tts_cache"
_USAGE_LOG  = _BASE_DIR / "voxtral_usage.jsonl"
_USAGE_SUMM = _BASE_DIR / "voxtral_usage_summary.json"

_MODEL   = "voxtral-mini-tts-2603"
_API_URL = "https://api.mistral.ai/v1/audio/speech"

# Static reference MP3s — used as fallback when no video-extracted ref exists
# Priority: video-extracted > static ref > preset voice
_STATIC_REFS = {
    "shinchan": "../shinchain_10s_opt.mp3",
    "misae":    "../misae_10s_opt.mp3",
    "hiroshi":  "../hiroshi_10s_opt.mp3",
}


class VoxtralService:
    def __init__(self):
        self._api_key: str = os.getenv("MISTRAL_API_KEY", "")
        self._spend_warned = False

        _CACHE_DIR.mkdir(exist_ok=True)

        if not self._api_key:
            logger.warning("[Voxtral] MISTRAL_API_KEY not set — TTS will be skipped")

    # ── Spend tracking ────────────────────────────────────────────────────────

    def _load_summary(self) -> dict:
        if _USAGE_SUMM.exists():
            try:
                return json.loads(_USAGE_SUMM.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"total_chars": 0, "total_calls": 0, "est_cost_usd": 0.0}

    def _save_summary(self, summary: dict):
        _USAGE_SUMM.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def _compute_cost(self, chars: int) -> float:
        return math.ceil(chars / 1_000_000 * PRICE_PER_M_CHAR * 100) / 100

    def _check_spend_cap(self, summary: dict) -> bool:
        cost = summary.get("est_cost_usd", 0.0)
        if cost >= SPEND_LIMIT_USD:
            logger.warning(
                f"[VOXTRAL-BLOCKED] ${SPEND_LIMIT_USD:.2f} cap reached "
                f"(cumulative=${cost:.4f}). Reset via POST /api/voxtral-usage/reset"
            )
            return True
        if cost >= SPEND_WARN_USD and not self._spend_warned:
            self._spend_warned = True
            logger.warning(
                f"[VOXTRAL-WARN] approaching ${SPEND_LIMIT_USD:.2f} cap: "
                f"${cost:.4f} spent"
            )
        return False

    def _record_call(self, character: str, chars: int, elapsed_ms: int, status: str):
        entry = {
            "ts":        datetime.now(timezone.utc).isoformat(),
            "character": character,
            "chars":     chars,
            "ms":        elapsed_ms,
            "status":    status,
        }
        with open(_USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        summary = self._load_summary()
        if status == "ok":
            summary["total_chars"] += chars
            summary["total_calls"]  = summary.get("total_calls", 0) + 1
            summary["est_cost_usd"] = round(
                summary.get("est_cost_usd", 0.0) + self._compute_cost(chars), 6
            )
        self._save_summary(summary)

    # ── Core synthesize ───────────────────────────────────────────────────────

    def synthesize(self, text: str, character_name: str, ref_audio_path: Optional[str] = None) -> Optional[str]:
        """
        Zero-shot voice clone via Mistral voxtral-mini-tts-2603 REST API.
        ref_audio_path: per-video extracted clip → exact voice clone.
        Falls back to Mistral preset masculine/feminine voice if no ref audio.
        Returns /tts-audio/<uuid>.mp3 URL on success, None on failure/cap.
        """
        if not self._api_key:
            logger.warning("[Voxtral] MISTRAL_API_KEY missing — skipping TTS")
            return None

        summary = self._load_summary()
        if self._check_spend_cap(summary):
            return None

        chars      = len(text)
        start_time = datetime.now(timezone.utc).timestamp()

        ref_b64 = None
        ref_source = None

        # 1. Video-extracted ref (highest priority)
        if ref_audio_path:
            try:
                ref_b64 = base64.b64encode(Path(ref_audio_path).read_bytes()).decode()
                ref_source = f"video-extracted:{ref_audio_path}"
            except Exception as e:
                logger.warning(f"[Voxtral] could not read ref_audio_path {ref_audio_path}: {e}")

        # 2. Static reference MP3 fallback (for known Shinchan characters)
        if not ref_b64 and character_name in _STATIC_REFS:
            static_path = (_BASE_DIR / _STATIC_REFS[character_name]).resolve()
            if static_path.exists():
                try:
                    ref_b64 = base64.b64encode(static_path.read_bytes()).decode()
                    ref_source = f"static:{static_path.name}"
                except Exception as e:
                    logger.warning(f"[Voxtral] could not read static ref for {character_name}: {e}")

        if ref_b64:
            logger.info(f"[Voxtral] cloning voice for {character_name} from {ref_source}")

        preset_voice = _PRESET_VOICES.get(character_name, _PRESET_VOICES["generic"])
        if ref_b64:
            payload = {"model": _MODEL, "input": text, "ref_audio": ref_b64, "response_format": "mp3"}
        else:
            logger.info(f"[Voxtral] no ref audio for {character_name} — preset voice: {preset_voice}")
            payload = {"model": _MODEL, "input": text, "voice": preset_voice, "response_format": "mp3"}

        try:
            resp = httpx.post(
                _API_URL,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=30.0,
            )
            elapsed_ms = int((datetime.now(timezone.utc).timestamp() - start_time) * 1000)

            if resp.status_code != 200:
                logger.error(f"[Voxtral] HTTP {resp.status_code} for {character_name}: {resp.text[:200]}")
                self._record_call(character_name, chars, elapsed_ms, "fail")
                return None

            # Mistral returns {"audio_data": "<base64 mp3>"} — decode it
            try:
                body = resp.json()
                audio_b64 = body.get("audio_data", "")
                if not audio_b64:
                    raise ValueError("No audio_data in response")
                audio_bytes = base64.b64decode(audio_b64)
            except Exception:
                # Fallback: some endpoints return raw binary
                audio_bytes = resp.content

            if not audio_bytes:
                logger.error(f"[Voxtral] Empty audio for {character_name}")
                self._record_call(character_name, chars, elapsed_ms, "fail")
                return None

            url = self._save_audio(audio_bytes)
            self._record_call(character_name, chars, elapsed_ms, "ok")
            logger.info(f"[Voxtral] {character_name} done in {elapsed_ms}ms ({len(audio_bytes)} bytes): {url}")
            return url

        except Exception as e:
            elapsed_ms = int((datetime.now(timezone.utc).timestamp() - start_time) * 1000)
            logger.error(f"[Voxtral] synthesis failed for {character_name}: {e}")
            self._record_call(character_name, chars, elapsed_ms, "fail")
            return None

    def _save_audio(self, audio_bytes: bytes) -> str:
        fname = f"{uuid.uuid4().hex}.mp3"
        (_CACHE_DIR / fname).write_bytes(audio_bytes)
        return f"/tts-audio/{fname}"

    # ── Usage API ─────────────────────────────────────────────────────────────

    def get_usage(self) -> dict:
        summary = self._load_summary()
        summary["spend_limit_usd"] = SPEND_LIMIT_USD
        summary["spend_warn_usd"]  = SPEND_WARN_USD
        summary["cap_reached"]     = summary.get("est_cost_usd", 0.0) >= SPEND_LIMIT_USD
        return summary

    def reset_usage(self):
        if _USAGE_SUMM.exists():
            _USAGE_SUMM.unlink()
        self._spend_warned = False
        logger.info("[Voxtral] Usage counter reset")


# ── Singleton ─────────────────────────────────────────────────────────────────

_voxtral_service: Optional[VoxtralService] = None


def get_voxtral_service() -> VoxtralService:
    global _voxtral_service
    if _voxtral_service is None:
        _voxtral_service = VoxtralService()
    return _voxtral_service
