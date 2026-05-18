"""Quick live test: does the 29s clean Shinchan clip complete within 240s?"""
import os, json, time, asyncio
from dotenv import load_dotenv
load_dotenv("../.env")
import videodb
from videodb import SandboxModel
from sandbox_manager import get_sandbox_manager

conn = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
coll = conn.get_collection("c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a")

with open("video_metadata/m-z-019e30d5-934a-7ea3-881a-10e3e5618279.json", encoding="utf-8") as f:
    meta = json.load(f)

vd = meta["character_voices"]["shinchan"]
print("ref_audio_id:", vd["ref_audio_id"])
print("ref_text (first 80):", vd["ref_text"][:80])
print()

manager = get_sandbox_manager()
sandbox_id = asyncio.run(manager.get_sandbox_id())
print("Sandbox:", sandbox_id)
print("Running OmniVoice clone (29s clean clip)...")

t0 = time.time()
try:
    result = coll.generate_voice(
        text="Mummy mujhe chocolate chahiye! Main Action Kamen dekhunga!",
        model_name=SandboxModel.OMNIVOICE,
        sandbox_id=sandbox_id,
        config={
            "ref_audio": vd["ref_audio_id"],
            "ref_text":  vd["ref_text"],
            "language":  "hi",
        },
        wait=True,
        timeout=240,
    )
    elapsed = time.time() - t0
    url = result.generate_url() if result else None
    print(f"Time: {elapsed:.1f}s")
    if url:
        print("RESULT: OK")
        print("URL:", url[:80])
    else:
        print("RESULT: None returned (no audio)")
except Exception as e:
    elapsed = time.time() - t0
    print(f"RESULT: ERROR after {elapsed:.1f}s")
    print("Error:", e)
