"""
One-shot script: upload curated MP3 voice samples to VideoDB and register
them as ref_audio for each character in the local metadata cache.

Run: python upload_voices.py
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv("../.env")
import videodb

VIDEO_ID     = "m-z-019e30d5-934a-7ea3-881a-10e3e5618279"
COLLECTION_ID = "c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a"
META_PATH    = Path(__file__).parent / f"video_metadata/{VIDEO_ID}.json"
AUDIO_DIR    = Path(__file__).parent.parent  # toontalk/

# Map character key → filename (cleaned/normalized versions for best clone quality)
CHARACTER_FILES = {
    "shinchan": AUDIO_DIR / "shinchain_voice_clean.mp3",
    "misae":    AUDIO_DIR / "misae_clean.mp3",
    "hiroshi":  AUDIO_DIR / "hiroshi_clean.mp3",
}

def main():
    conn  = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
    coll  = conn.get_collection(COLLECTION_ID)

    with open(META_PATH, encoding="utf-8") as f:
        meta = json.load(f)

    meta.setdefault("character_voices", {})

    for char, filepath in CHARACTER_FILES.items():
        if not filepath.exists():
            print(f"[SKIP] {char}: file not found -> {filepath}")
            continue

        # Force overwrite — re-upload cleaned version
        if char in meta["character_voices"]:
            print(f"[OVERWRITE] {char}: replacing previous ref_audio")
        size_kb = filepath.stat().st_size // 1024
        print(f"[UPLOAD] {char}: {filepath.name} ({size_kb} KB) ...", end="", flush=True)

        audio = coll.upload(file_path=str(filepath), media_type="audio")
        ref_url = audio.generate_url()

        meta["character_voices"][char] = {
            "ref_audio_url": ref_url,
            "ref_audio_id":  audio.id,
            "source":        "manual_mp3",
            "file":          filepath.name,
        }
        print(f" OK  {audio.id}")

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print()
    print("=== Registered voices ===")
    for char, data in meta["character_voices"].items():
        src = data.get("source", "video_extract")
        print(f"  {char:12s} | {src:15s} | {data.get('file', data.get('ref_audio_id',''))}")

if __name__ == "__main__":
    main()
