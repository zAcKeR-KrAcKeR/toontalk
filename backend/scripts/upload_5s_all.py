"""Upload all 3 five-second ref clips for faster OmniVoice generation."""
import os, json, sys
sys.path.insert(0, '.')
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("../.env")
from groq import Groq
import videodb

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
conn   = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
coll   = conn.get_collection("c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a")
META_PATH = Path("video_metadata/m-z-019e30d5-934a-7ea3-881a-10e3e5618279.json")

clips = {
    "shinchan": Path("../shinchain_5s.mp3"),
    "misae":    Path("../misae_5s.mp3"),
    "hiroshi":  Path("../hiroshi_5s.mp3"),
}

with open(META_PATH, encoding="utf-8") as f:
    meta = json.load(f)

for char, clip in clips.items():
    print(f"[{char}] Transcribing {clip.name}...")
    with open(clip, "rb") as f:
        resp = client.audio.transcriptions.create(
            file=(clip.name, f, "audio/mpeg"),
            model="whisper-large-v3", language="hi", response_format="text",
        )
    ref_text = resp.strip() if isinstance(resp, str) else resp.text.strip()
    print(f"  ref_text: {ref_text}")

    print(f"  Uploading...")
    audio_obj = coll.upload(file_path=str(clip), media_type="audio")
    print(f"  id: {audio_obj.id}")

    meta["character_voices"][char] = {
        "ref_audio_id":  audio_obj.id,
        "ref_audio_url": audio_obj.generate_url(),
        "ref_text":      ref_text,
        "source":        "manual_mp3",
        "clip_info":     "5s loudnorm only",
    }
    print()

with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print("=== Done ===")
for char in ["shinchan", "misae", "hiroshi"]:
    vd = meta["character_voices"][char]
    print(f"  {char:10s} | {vd['ref_audio_id']} | {vd['ref_text'][:60]}")
