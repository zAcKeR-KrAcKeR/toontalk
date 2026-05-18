"""
Register Misae 10s clip with Whisper ref_text.
Run from: backend/
"""
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

clip = Path("../misae_10s_opt.mp3")
print(f"Transcribing {clip.name} ({clip.stat().st_size//1024}KB)...")
with open(clip, "rb") as f:
    resp = client.audio.transcriptions.create(
        file=(clip.name, f, "audio/mpeg"),
        model="whisper-large-v3",
        language="hi",
        response_format="text",
    )
ref_text = resp.strip() if isinstance(resp, str) else resp.text.strip()
print(f"ref_text: {ref_text}")

print("Uploading...")
audio_obj = coll.upload(file_path=str(clip), media_type="audio")
print(f"Uploaded: {audio_obj.id}")

with open(META_PATH, encoding="utf-8") as f:
    meta = json.load(f)
meta["character_voices"]["misae"] = {
    "ref_audio_id":  audio_obj.id,
    "ref_audio_url": audio_obj.generate_url(),
    "ref_text":      ref_text,
    "source":        "manual_mp3",
    "clip_info":     "10s loudnorm only",
}
with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
print(f"\nDone. Misae: {audio_obj.id}")
print(f"ref_text: {ref_text}")
