"""
Debug OmniVoice failure - inspect raw API response.
"""
import os, json, requests
from dotenv import load_dotenv
load_dotenv("../.env")
import videodb
from videodb import SandboxModel

conn = videodb.connect(api_key=os.getenv("VIDEO_DB_API_KEY"))
coll = conn.get_collection("c-f7389e1f-4945-4b75-bea4-f29eeb2fd79a")

with open("video_metadata/m-z-019e30d5-934a-7ea3-881a-10e3e5618279.json") as f:
    meta = json.load(f)

voice_data = meta["character_voices"]["shinchan"]
ref_audio_id = voice_data["ref_audio_id"]

print(f"ref_audio_id: {ref_audio_id}")

# Get fresh URL
audio_obj = coll.get_audio(ref_audio_id)
fresh_url = audio_obj.generate_url()
print(f"Fresh URL (first 120 chars): {fresh_url[:120]}")
print(f"Audio object id: {audio_obj.id}, name: {getattr(audio_obj, 'name', 'N/A')}")

# Try with NO sandbox_id first (let VideoDB auto-assign)
print("\nTest 1: OmniVoice, no sandbox_id, wait=False (get raw job)...")
try:
    job = coll.generate_voice(
        text="Hello",
        model_name=SandboxModel.OMNIVOICE,
        config={"ref_audio": fresh_url, "ref_text": "", "language": "hi"},
        wait=False,
    )
    print(f"  Job type: {type(job).__name__}")
    print(f"  Job attrs: {dir(job)}")
    if hasattr(job, 'id'):
        print(f"  Job id: {job.id}")
    if hasattr(job, 'status'):
        print(f"  Status: {job.status}")
except Exception as e:
    print(f"  ERROR: {e}")

# Try with elevenlabs just to confirm that still works
print("\nTest 2: ElevenLabs preset (sanity check)...")
try:
    job2 = coll.generate_voice(text="Hello", model_name="elevenlabs", voice_name="Charlie")
    audio2 = job2 if not hasattr(job2, 'wait') else job2.wait(30)
    print(f"  ElevenLabs OK: {type(audio2).__name__}")
except Exception as e:
    print(f"  ElevenLabs ERROR: {e}")

# Try ElevenLabs WITH ref_audio (the approach we tested earlier that returned a different URL)
print("\nTest 3: ElevenLabs + ref_audio...")
try:
    job3 = coll.generate_voice(
        text="Mummy mujhe chocolate chahiye!",
        model_name="elevenlabs",
        config={"ref_audio": fresh_url, "language": "hi"},
    )
    audio3 = job3 if not hasattr(job3, 'wait') else job3.wait(60)
    url3 = audio3.generate_url() if audio3 else None
    print(f"  ElevenLabs+ref_audio OK: {url3[:80] if url3 else 'FAILED'}")
except Exception as e:
    print(f"  ERROR: {e}")
