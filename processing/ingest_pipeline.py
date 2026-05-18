"""
ToonTalk Ingest Pipeline
========================
Standalone script to process a cartoon episode end-to-end.

Usage:
    python ingest_pipeline.py --file /path/to/shinchan.mp4
    python ingest_pipeline.py --url https://www.youtube.com/watch?v=...
    python ingest_pipeline.py --video-id vid_xxxx  # re-process existing

This script:
1. Uploads the video to VideoDB
2. Creates a sandbox
3. Runs scene indexing (VLM with Gemma 4 31B)
4. Runs spoken word indexing (transcription)
5. Clones voices for all main characters
6. Saves metadata JSON for the backend to use
7. Stops the sandbox

Run this BEFORE starting the ToonTalk server for best demo performance.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add backend dir to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from videodb import connect, SandboxTier, SandboxModel, IndexType, SearchType, SceneExtractionType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("ingest")

# ─── Scene index prompt ───────────────────────────────────────────────────────

SCENE_PROMPT = """Analyze this cartoon frame and describe:
1. Which characters are VISIBLE (name them — Shinchan, Doraemon, Nobita, etc.)
2. WHERE each character is on screen (left, center, right)
3. What is HAPPENING in this scene
4. The MOOD/EMOTION of each character
5. Any visible dialogue or speech

Respond in this exact JSON format:
{
  "characters": [
    {"name": "name", "position": "left/center/right", "emotion": "emotion", "speaking": true/false}
  ],
  "scene_description": "English description",
  "scene_description_hindi": "Hindi description",
  "action": "what is happening",
  "mood": "overall mood"
}"""


def create_sandbox(conn, tier="medium"):
    """Create and wait for a sandbox."""
    tier_obj = SandboxTier.medium if tier == "medium" else SandboxTier.small
    logger.info(f"Creating sandbox (tier={tier})...")

    sandbox = conn.create_sandbox(
        tier=tier_obj,
        idle_timeout=600,
    )
    logger.info(f"Sandbox created: {sandbox.id} (status: {sandbox.status})")

    sandbox.wait_for_ready(timeout=300, interval=5)
    logger.info(f"✅ Sandbox ready: {sandbox.id}")
    return sandbox


def upload_video(coll, file_path=None, url=None):
    """Upload video to VideoDB."""
    logger.info(f"Uploading video: {file_path or url}")
    if file_path:
        video = coll.upload(file_path=file_path)
    else:
        video = coll.upload(url=url)
    logger.info(f"✅ Video uploaded: {video.id} | {video.name} | {video.length:.0f}s")
    return video


def index_scenes(video, sandbox):
    """Run VLM scene indexing."""
    logger.info("Starting scene indexing (this may take 5-15 minutes)...")
    start = time.time()

    index_id = video.index_scenes(
        extraction_type=SceneExtractionType.time_based,
        extraction_config={
            "time": 10,
            "select_frames": ["first", "middle"],
            "frame_count": 2,
        },
        model_name=SandboxModel.GEMMA_4_31B,
        prompt=SCENE_PROMPT,
        sandbox_id=sandbox.id,
    )

    elapsed = time.time() - start
    logger.info(f"✅ Scene indexing complete: {index_id} ({elapsed:.0f}s)")
    return index_id


def index_spoken_words(video):
    """Run spoken word indexing (transcription)."""
    logger.info("Starting spoken word indexing...")
    start = time.time()

    video.index_spoken_words()

    elapsed = time.time() - start
    logger.info(f"✅ Spoken word indexing complete ({elapsed:.0f}s)")
    return True


def clone_character_voice(video, coll, sandbox, character_name, search_query=None):
    """
    Find character dialogue, extract audio sample, create OmniVoice clone.
    Returns voice data dict or None on failure.
    """
    VOICE_QUERIES = {
        "shinchan": [
            "शिनचान", "shin chan", "shinchan", "mama", "action kamen", "मम्मा", "baa baa",
        ],
        "doraemon": [
            "डोरेमोन", "doraemon", "nobita", "नोबिता", "pocket", "gadget", "takecop",
        ],
        "nobita": [
            "नोबिता", "nobita", "doraemon", "डोरेमोन", "shizuka", "gian", "suneo",
        ],
    }
    
    queries = VOICE_QUERIES.get(character_name, [search_query or f"{character_name} speaking"])
    logger.info(f"Cloning voice for: {character_name} (using {len(queries)} queries)")

    best_shot = None
    for query in queries:
        try:
            # Search for character's dialogue
            results = video.search(
                query,
                index_type=IndexType.spoken_word,
                search_type=SearchType.semantic,
            )
            shots = getattr(results, "shots", []) or []
            if shots:
                logger.info(f"  Found dialogue for query '{query}'")
                best_shot = shots[0]
                break
        except Exception as e:
            logger.debug(f"Query '{query}' failed: {e}")
            continue

    if best_shot is None:
        logger.warning(f"  No dialogue found for {character_name} — skipping voice clone")
        return None

    try:
        # Use best match, extract ~45 second sample
        start_t = max(0, getattr(best_shot, "start", 0))
        end_t = min(video.length, start_t + 45)

        logger.info(f"  Extracting {character_name}'s voice: {start_t:.1f}s – {end_t:.1f}s")

        # Get clip stream URL
        clip_url = video.generate_stream(timeline=[(start_t, end_t)])

        # Upload as reference audio
        ref_audio = coll.upload(url=clip_url, media_type="audio")
        ref_audio_url = ref_audio.generate_url()
        logger.info(f"  Reference audio uploaded: {ref_audio.id}")

        # Test clone with a short phrase
        logger.info(f"  Generating test clone for {character_name}...")
        test_job = coll.generate_voice(
            text="नमस्ते! मैं तैयार हूँ!",
            model_name=SandboxModel.OMNIVOICE,
            sandbox_id=sandbox.id,
            config={
                "ref_audio": ref_audio_url,
                "language": "hi",
            },
        )
        test_audio = test_job.wait(timeout=900, interval=5)

        voice_data = {
            "ref_audio_url": ref_audio_url,
            "ref_audio_id": ref_audio.id,
            "sample_start": start_t,
            "sample_end": end_t,
            "test_audio_id": test_audio.id,
        }
        logger.info(f"  ✅ Voice clone ready for {character_name}")
        return voice_data

    except Exception as e:
        logger.error(f"  ❌ Voice clone failed for {character_name}: {e}")
        return None


def save_metadata(video_id, data, output_dir):
    """Save processing metadata."""
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{video_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Metadata saved: {path}")
    return str(path)


# ─── Characters to process ───────────────────────────────────────────────────

DEFAULT_CHARACTERS = {
    "shinchan": "Shinchan talking",
    "doraemon": "Doraemon speaking",
    "nobita": "Nobita talking",
}


def main():
    parser = argparse.ArgumentParser(description="ToonTalk Ingest Pipeline")
    parser.add_argument("--file", help="Path to video file")
    parser.add_argument("--url", help="URL of video (YouTube, direct link)")
    parser.add_argument("--video-id", help="Existing VideoDB video ID to re-process")
    parser.add_argument("--characters", nargs="+",
                        default=list(DEFAULT_CHARACTERS.keys()),
                        help="Characters to clone voices for")
    parser.add_argument("--sandbox-tier", default="medium", choices=["small", "medium"])
    parser.add_argument("--skip-scene-index", action="store_true")
    parser.add_argument("--skip-spoken-words", action="store_true")
    parser.add_argument("--skip-voice-clone", action="store_true")
    parser.add_argument("--output-dir",
                        default=str(Path(__file__).parent.parent / "backend" / "video_metadata"))
    args = parser.parse_args()

    if not args.file and not args.url and not args.video_id:
        parser.error("Provide --file, --url, or --video-id")

    api_key = os.getenv("VIDEO_DB_API_KEY")
    if not api_key:
        logger.error("VIDEO_DB_API_KEY not set in environment")
        sys.exit(1)

    # Connect
    conn = connect()
    coll = conn.get_collection()
    logger.info(f"Connected to VideoDB. Collection: {coll.id}")

    # Create sandbox
    sandbox = create_sandbox(conn, tier=args.sandbox_tier)

    metadata = {}

    try:
        # Upload or get existing
        if args.video_id:
            video = coll.get_video(args.video_id)
            logger.info(f"Using existing video: {video.id}")
            # Load existing metadata if available
            meta_path = Path(args.output_dir) / f"{video.id}.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    metadata = json.load(f)
        else:
            video = upload_video(coll, file_path=args.file, url=args.url)

        metadata.update({
            "video_id": video.id,
            "name": video.name,
            "duration": video.length,
            "collection_id": coll.id,
            "processing_status": "processing",
        })

        # Scene indexing
        if not args.skip_scene_index:
            index_id = index_scenes(video, sandbox)
            metadata["scene_index_id"] = index_id
        else:
            logger.info("Skipping scene indexing")

        # Spoken word indexing
        if not args.skip_spoken_words:
            index_spoken_words(video)
            metadata["spoken_word_indexed"] = True
        else:
            logger.info("Skipping spoken word indexing")

        # Voice cloning
        if not args.skip_voice_clone:
            character_voices = metadata.get("character_voices", {})
            for char in args.characters:
                search_query = DEFAULT_CHARACTERS.get(char, f"{char} speaking")
                voice_data = clone_character_voice(
                    video, coll, sandbox, char, search_query
                )
                if voice_data:
                    character_voices[char] = voice_data

            metadata["character_voices"] = character_voices
        else:
            logger.info("Skipping voice cloning")

        metadata["processing_status"] = "ready"
        save_metadata(video.id, metadata, args.output_dir)

        logger.info("\n" + "="*60)
        logger.info("✅ ToonTalk Ingest Pipeline Complete!")
        logger.info(f"   Video ID: {video.id}")
        logger.info(f"   Scene Index: {metadata.get('scene_index_id', 'skipped')}")
        logger.info(f"   Spoken Words: {metadata.get('spoken_word_indexed', False)}")
        logger.info(f"   Voice Clones: {list(metadata.get('character_voices', {}).keys())}")
        logger.info(f"   Metadata: {args.output_dir}/{video.id}.json")
        logger.info("="*60)
        logger.info(f"\nAdd this to your .env:\n  DEMO_VIDEO_ID={video.id}")

    finally:
        # Stop sandbox to save credits
        logger.info("Stopping sandbox to conserve credits...")
        try:
            sandbox.stop()
            sandbox.wait_for_stop(timeout=120)
            logger.info("✅ Sandbox stopped")
        except Exception as e:
            logger.warning(f"Could not stop sandbox: {e}")


if __name__ == "__main__":
    main()
