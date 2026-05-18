"""
Trim misae and hiroshi ref audios to 15s optimal window and re-upload.
Also re-transcribe misae (only 10s before, needs better segment from full 29s available).
"""
import os, json, subprocess
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
AUDIO_DIR = Path(__file__).parent.parent

with open(META_PATH, encoding="utf-8") as f:
    meta = json.load(f)

# misae original is only 10s — use all of it but reprocess at higher quality
# hiroshi original is 26s — trim to 15s middle segment
clips = {
    "misae":   {"src": "misae_clean.mp3",   "ss": 0,  "t": 10},  # use all 10s
    "hiroshi": {"src": "hiroshi_clean.mp3",  "ss": 6,  "t": 15},  # best 15s (6-21s)
}

for char, cfg in clips.items():
    src  = AUDIO_DIR / cfg["src"]
    out  = AUDIO_DIR / f"{char}_15s_final.mp3"

    print(f"\n[{char}] Trimming {cfg['src']} -> {out.name}...")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ss", str(cfg["ss"]), "-t", str(cfg["t"]),
        "-af", "highpass=f=100,lowpass=f=7500,dynaudnorm=f=150:g=15:p=0.9,volume=2.5",
        "-ar", "44100", "-ab", "128k", str(out)
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    size_kb = out.stat().st_size // 1024
    print(f"  OK — {size_kb} KB")

    # Transcribe
    print(f"  Transcribing with whisper-large-v3...")
    with open(out, "rb") as f:
        resp = client.audio.transcriptions.create(
            file=(out.name, f, "audio/mpeg"),
            model="whisper-large-v3",
            language="hi",
            response_format="text",
        )
    ref_text = resp.strip() if isinstance(resp, str) else resp.text.strip()
    print(f"  ref_text: {ref_text[:120]}")

    # Upload
    print(f"  Uploading to VideoDB...")
    audio_obj = coll.upload(file_path=str(out), media_type="audio")
    print(f"  Uploaded: {audio_obj.id}")

    # Update metadata
    meta["character_voices"][char] = {
        "ref_audio_id":  audio_obj.id,
        "ref_audio_url": audio_obj.generate_url(),
        "ref_text":      ref_text,
        "source":        "manual_mp3",
        "clip_info":     f"{cfg['t']}s trimmed from {cfg['src']}",
    }

with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print("\n=== All done ===")
for char in ["shinchan", "misae", "hiroshi"]:
    vd = meta["character_voices"][char]
    print(f"  {char:10s} | id={vd['ref_audio_id']} | ref_text={vd.get('ref_text','')[:60]}")
