"""
One-time voice registration script.
Registers Shinchan, Misae, Hiroshi with Mistral's audio/voices API.
Saves resulting voice_ids to voice_ids.json for use by voxtral_service.py.

Voice CREATION is free — you only pay for speech synthesis (via OpenRouter).
Run once: venv/Scripts/python.exe register_voices.py
"""

import base64
import json
import os
import sys
from pathlib import Path

# ── Hard spend limit guard ────────────────────────────────────────────────────
# Voice creation is free, but add a check just in case.
MISTRAL_SPEND_LIMIT_USD = 1.00

# ── Character reference audio files ──────────────────────────────────────────
BASE_DIR = Path(__file__).parent

CHAR_REF_FILES = {
    "shinchan": BASE_DIR / "../shinchain_10s_opt.mp3",
    "misae":    BASE_DIR / "../misae_10s_opt.mp3",
    "hiroshi":  BASE_DIR / "../hiroshi_10s_opt.mp3",
}

OUTPUT_FILE = BASE_DIR / "voice_ids.json"

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "Your Misral API Key")


def main():
    from mistralai.client import Mistral

    client = Mistral(api_key=MISTRAL_API_KEY)

    # Load existing voice_ids if any
    existing = {}
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            print(f"Existing voice IDs: {list(existing.keys())}")
        except Exception:
            pass

    voice_ids = dict(existing)

    for char, ref_path in CHAR_REF_FILES.items():
        ref_path = ref_path.resolve()

        if char in voice_ids:
            print(f"[{char}] Already registered: {voice_ids[char]} — skipping")
            continue

        if not ref_path.exists():
            print(f"[{char}] WARNING: ref audio not found at {ref_path} — skipping")
            continue

        audio_bytes = ref_path.read_bytes()
        audio_b64   = base64.b64encode(audio_bytes).decode()
        filename    = ref_path.name

        print(f"[{char}] Registering voice from {filename} ({len(audio_bytes)//1024} kB)...")

        try:
            voice = client.audio.voices.create(
                name=f"toontalk-{char}",
                sample_audio=audio_b64,
                sample_filename=filename,
                languages=["hi"],
            )
            vid = voice.id
            voice_ids[char] = vid
            print(f"[{char}] ✅ voice_id = {vid}")
        except Exception as e:
            print(f"[{char}] ❌ Registration failed: {e}")
            sys.exit(1)

    OUTPUT_FILE.write_text(
        json.dumps(voice_ids, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved voice IDs to {OUTPUT_FILE}")
    print(json.dumps(voice_ids, indent=2))


if __name__ == "__main__":
    main()
