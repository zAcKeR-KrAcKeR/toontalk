"""
Upload the 10s Shinchan clip (seconds 10-20 from clean.mp3, minimal processing).
10s is OmniVoice's sweet spot: fast (~25s) and no robotic artifacts.
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("../.env")
from groq import Groq
import videodb

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
conn   = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
coll   = conn.get_collection("c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a")

VIDEO_ID  = "m-z-019e30d5-934a-7ea3-881a-10e3e5618279"
META_PATH = Path(__file__).parent / f"video_metadata/{VIDEO_ID}.json"
clip_path = Path(__file__).parent.parent / "shinchain_10s_opt.mp3"

print(f"Clip: {clip_path.name} ({clip_path.stat().st_size // 1024} KB, 10s, minimal processing)")

# Transcribe
print("Transcribing with whisper-large-v3...")
with open(clip_path, "rb") as f:
    resp = client.audio.transcriptions.create(
        file=(clip_path.name, f, "audio/mpeg"),
        model="whisper-large-v3",
        language="hi",
        response_format="text",
    )
ref_text = resp.strip() if isinstance(resp, str) else resp.text.strip()
print(f"ref_text: {ref_text}")

# Upload
print("\nUploading to VideoDB...")
audio_obj = coll.upload(file_path=str(clip_path), media_type="audio")
print(f"Uploaded: {audio_obj.id}")

# Update metadata
with open(META_PATH, encoding="utf-8") as f:
    meta = json.load(f)

meta["character_voices"]["shinchan"] = {
    "ref_audio_id":  audio_obj.id,
    "ref_audio_url": audio_obj.generate_url(),
    "ref_text":      ref_text,
    "source":        "manual_mp3",
    "clip_info":     "10s (ss=10, minimal loudnorm only) - OmniVoice sweet spot",
}
with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"\nDone. Shinchan 10s ref registered.")
print(f"  audio_id: {audio_obj.id}")
print(f"  ref_text: {ref_text[:100]}")
