"""
Find the best 15s Shinchan clip using whisper-large-v3 transcription quality.
Then upload the best one and update metadata.
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
AUDIO_DIR = Path(__file__).parent.parent  # toontalk/

clips = {
    "A (0-15s)":  AUDIO_DIR / "shinchain_15s_a.mp3",
    "B (7-22s)":  AUDIO_DIR / "shinchain_15s_b.mp3",
    "C (14-29s)": AUDIO_DIR / "shinchain_15s_c.mp3",
}

print("Transcribing 3 candidate Shinchan clips with whisper-large-v3...\n")
results = {}

for label, path in clips.items():
    with open(path, "rb") as f:
        resp = client.audio.transcriptions.create(
            file=(path.name, f, "audio/mpeg"),
            model="whisper-large-v3",      # higher accuracy than turbo
            language="hi",
            response_format="verbose_json", # get avg_logprob for quality score
        )
    text = resp.text.strip()
    # avg_logprob: closer to 0 = more confident = cleaner audio
    avg_lp = getattr(resp, "avg_logprob", None)
    if avg_lp is None and hasattr(resp, "segments") and resp.segments:
        avg_lp = sum(s.get("avg_logprob", -1) for s in resp.segments) / len(resp.segments)
    results[label] = {"path": path, "text": text, "avg_logprob": avg_lp or -1.0}
    print(f"Clip {label}:")
    print(f"  avg_logprob: {avg_lp:.4f}" if avg_lp else "  avg_logprob: N/A")
    print(f"  text: {text[:120]}")
    print()

# Best = highest avg_logprob (least negative = most confident)
best_label = max(results, key=lambda k: results[k]["avg_logprob"])
best = results[best_label]
print(f"Best clip: {best_label} (avg_logprob={best['avg_logprob']:.4f})")
print(f"ref_text: {best['text']}")
print()

# Upload best clip
print("Uploading best Shinchan clip to VideoDB...")
audio_obj = coll.upload(file_path=str(best["path"]), media_type="audio")
ref_audio_url = audio_obj.generate_url()
print(f"Uploaded: {audio_obj.id}")

# Update metadata
with open(META_PATH, encoding="utf-8") as f:
    meta = json.load(f)

meta["character_voices"]["shinchan"] = {
    "ref_audio_url": ref_audio_url,
    "ref_audio_id":  audio_obj.id,
    "ref_text":      best["text"],
    "source":        "manual_mp3",
    "clip_window":   best_label,
}
with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"Metadata updated. Shinchan now uses clip {best_label}.")
print(f"ref_text: {best['text'][:100]}")
