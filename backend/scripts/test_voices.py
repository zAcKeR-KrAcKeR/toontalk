"""Quick test: generate TTS for shinchan, misae, hiroshi using their clean MP3 clones."""
import os, json
from dotenv import load_dotenv
load_dotenv("../.env")
import videodb

conn = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
coll = conn.get_collection("c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a")

with open("video_metadata/m-z-019e30d5-934a-7ea3-881a-10e3e5618279.json") as f:
    meta = json.load(f)

TEST_LINES = {
    "shinchan": "हाय! मैं शिनचान हूँ, मुझे चॉकलेट चाहिए!",
    "misae":    "शिनचान! अभी आ जाओ, खाना ठंडा हो रहा है!",
    "hiroshi":  "बेटा, आज ऑफिस में बहुत काम था।",
}

for char, text in TEST_LINES.items():
    voice_data = meta.get("character_voices", {}).get(char)
    if not voice_data:
        print(f"[SKIP] {char}: no voice data")
        continue
    src = voice_data.get("source", "unknown")
    ref_url = voice_data["ref_audio_url"]
    print(f"[TEST] {char} (source={src}): {text}")
    job = coll.generate_voice(
        text=text,
        model_name="elevenlabs",
        config={"ref_audio": ref_url, "language": "hi"},
    )
    audio = job if not hasattr(job, "wait") else job.wait(60)
    if audio:
        url = audio.generate_url()
        print(f"  -> OK: {url[:100]}")
    else:
        print(f"  -> FAILED: no audio returned")
    print()
