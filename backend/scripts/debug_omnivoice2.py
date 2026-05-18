"""
Deep debug: OmniVoice with explicit sandbox provisioning.
Try every possible config to get it working.
"""
import os, json, time
from dotenv import load_dotenv
load_dotenv("../.env")
import videodb
from videodb import SandboxModel
from sandbox_manager import get_sandbox_manager

conn = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
coll = conn.get_collection("c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a")

with open("video_metadata/m-z-019e30d5-934a-7ea3-881a-10e3e5618279.json") as f:
    meta = json.load(f)

ref_audio_id = meta["character_voices"]["shinchan"]["ref_audio_id"]
fresh_url = coll.get_audio(ref_audio_id).generate_url()
print(f"ref_audio_id: {ref_audio_id}")
print(f"URL starts with: {fresh_url[:80]}")
print()

# ── Test 1: OmniVoice with explicit sandbox_id ──────────────────────────────
print("Test 1: Provision sandbox then OmniVoice...")
try:
    manager = get_sandbox_manager()
    import asyncio
    sandbox_id = asyncio.run(manager.get_sandbox_id())
    print(f"  Sandbox ready: {sandbox_id}")

    result = coll.generate_voice(
        text="Hello Mummy!",
        model_name=SandboxModel.OMNIVOICE,
        sandbox_id=sandbox_id,
        config={"ref_audio": fresh_url, "ref_text": "", "language": "hi"},
        wait=True,
        timeout=180,
    )
    url = result.generate_url() if result else None
    print(f"  Result: {'OK -> ' + url[:80] if url else 'None'}")
except Exception as e:
    print(f"  ERROR: {e}")

print()

# ── Test 2: OmniVoice with NO ref_audio (pure TTS) ─────────────────────────
print("Test 2: OmniVoice plain TTS (no ref_audio - sanity check)...")
try:
    manager = get_sandbox_manager()
    sandbox_id = asyncio.run(manager.get_sandbox_id())
    result = coll.generate_voice(
        text="Hello!",
        model_name=SandboxModel.OMNIVOICE,
        sandbox_id=sandbox_id,
        wait=True,
        timeout=180,
    )
    url = result.generate_url() if result else None
    print(f"  Result: {'OK -> ' + url[:80] if url else 'None'}")
except Exception as e:
    print(f"  ERROR: {e}")

print()

# ── Test 3: OmniVoice with ref_audio as audio_id not URL ───────────────────
print("Test 3: OmniVoice with ref_audio = audio asset id (not URL)...")
try:
    manager = get_sandbox_manager()
    sandbox_id = asyncio.run(manager.get_sandbox_id())
    result = coll.generate_voice(
        text="Hello Mummy!",
        model_name=SandboxModel.OMNIVOICE,
        sandbox_id=sandbox_id,
        config={"ref_audio": ref_audio_id, "ref_text": "", "language": "hi"},
        wait=True,
        timeout=180,
    )
    url = result.generate_url() if result else None
    print(f"  Result: {'OK -> ' + url[:80] if url else 'None'}")
except Exception as e:
    print(f"  ERROR: {e}")
