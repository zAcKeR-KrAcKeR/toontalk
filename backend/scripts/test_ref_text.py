"""
Quick test: OmniVoice with real ref_text from Whisper transcription.
This should produce clear, intelligible cloned voice output.
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("../.env")
import videodb
from videodb import SandboxModel
from sandbox_manager import get_sandbox_manager
import asyncio

conn = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
coll = conn.get_collection("c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a")

META_PATH = Path(__file__).parent / "video_metadata/m-z-019e30d5-934a-7ea3-881a-10e3e5618279.json"
with open(META_PATH, encoding="utf-8") as f:
    meta = json.load(f)

manager = get_sandbox_manager()
sandbox_id = asyncio.run(manager.get_sandbox_id())
print(f"Sandbox ready: {sandbox_id}\n")

tests = {
    "shinchan": "Mummy mujhe chocolate chahiye, please please!",
    "misae":    "Shinchan andar aa jao, khana thanda ho raha hai!",
    "hiroshi":  "Aaj office mein bahut thakaan ho gayi.",
}

for char, text in tests.items():
    vd = meta["character_voices"][char]
    ref_audio_id = vd["ref_audio_id"]
    ref_text     = vd.get("ref_text", "")
    print(f"[{char}]")
    print(f"  ref_text (first 80): {ref_text[:80]}")
    print(f"  Generating: '{text}'")

    try:
        result = coll.generate_voice(
            text=text,
            model_name=SandboxModel.OMNIVOICE,
            sandbox_id=sandbox_id,
            config={"ref_audio": ref_audio_id, "ref_text": ref_text, "language": "hi"},
            wait=True,
            timeout=180,
        )
        url = result.generate_url() if result else None
        print(f"  Result: {'OK -> ' + url[:80] if url else 'FAILED/None'}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
