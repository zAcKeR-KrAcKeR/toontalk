"""
Transcribe the 3 reference audio MP3 files using Groq Whisper
and store the transcriptions as ref_text in the metadata JSON.

OmniVoice REQUIRES ref_text = the actual text spoken in ref_audio.
Without it, phoneme alignment fails → garbled, unintelligible output.
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("../.env")
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

VIDEO_ID  = "m-z-019e30d5-934a-7ea3-881a-10e3e5618279"
META_PATH = Path(__file__).parent / f"video_metadata/{VIDEO_ID}.json"
AUDIO_DIR = Path(__file__).parent.parent  # toontalk/

CHARACTER_FILES = {
    "shinchan": AUDIO_DIR / "shinchain_voice_clean.mp3",
    "misae":    AUDIO_DIR / "misae_clean.mp3",
    "hiroshi":  AUDIO_DIR / "hiroshi_clean.mp3",
}

with open(META_PATH, encoding="utf-8") as f:
    meta = json.load(f)

print("Transcribing reference audio files with Groq Whisper...")
print("(ref_text is required by OmniVoice for correct phoneme alignment)\n")

for char, filepath in CHARACTER_FILES.items():
    if not filepath.exists():
        print(f"[SKIP] {char}: {filepath.name} not found")
        continue

    print(f"[{char}] Transcribing {filepath.name}...")
    with open(filepath, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(filepath.name, f, "audio/mpeg"),
            model="whisper-large-v3-turbo",
            language="hi",           # Hindi
            response_format="text",
        )

    ref_text = result.strip() if isinstance(result, str) else result.text.strip()
    print(f"[{char}] ref_text: {ref_text[:120]}")

    # Save to metadata
    if char in meta.get("character_voices", {}):
        meta["character_voices"][char]["ref_text"] = ref_text
    print()

with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print("=== Done — ref_text stored for all characters ===")
for char in CHARACTER_FILES:
    rt = meta.get("character_voices", {}).get(char, {}).get("ref_text", "MISSING")
    print(f"  {char:12s}: {rt[:80]}")
