"""
Test fresh URL approach for all 3 characters with cleaned ref audio.
Verifies the URL expiry fix works end-to-end.
"""
import os, json
from dotenv import load_dotenv
load_dotenv("../.env")
import videodb
from videodb import SandboxModel

conn = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
coll = conn.get_collection("c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a")

with open("video_metadata/m-z-019e30d5-934a-7ea3-881a-10e3e5618279.json") as f:
    meta = json.load(f)

tests = {
    "shinchan": "Mummy mujhe aaj chocolate chahiye!",
    "misae":    "Shinchan andar aa jao, khana thanda ho raha hai!",
    "hiroshi":  "Aaj office mein bahut thakaan hui.",
}

for char, text in tests.items():
    voice_data = meta["character_voices"][char]
    ref_audio_id = voice_data["ref_audio_id"]
    print(f"[{char}] Fetching fresh URL for audio_id={ref_audio_id}...")

    fresh_url = coll.get_audio(ref_audio_id).generate_url()
    print(f"[{char}] Fresh URL OK. Generating OmniVoice clone...")

    result = coll.generate_voice(
        text=text,
        model_name=SandboxModel.OMNIVOICE,
        config={"ref_audio": fresh_url, "ref_text": "", "language": "hi"},
        wait=True,
        timeout=120,
    )

    if result:
        out_url = result.generate_url()
        print(f"[{char}] SUCCESS -> {out_url[:80]}")
    else:
        print(f"[{char}] FAILED - None returned")
    print()
