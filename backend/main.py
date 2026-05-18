"""
ToonTalk Backend — FastAPI main entry point
"""

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from character_config import (
    CHARACTER_PERSONAS,
    CHARACTER_BUBBLE_STYLES,
    CHARACTER_DETECTION_KEYWORDS,
)
from llm_service import get_llm_service
from videodb_service import VideoDBService
from sandbox_manager import get_sandbox_manager
from voxtral_service import get_voxtral_service
from flux_service import get_flux_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("toontalk")


# ── Settings ──────────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    video_db_api_key: str = ""
    groq_api_key: str = ""

    class Config:
        env_file = "../.env"
        extra = "ignore"


settings = Settings()


# ── Lifespan ──────────────────────────────────────────────────────────────────

async def _warm_sandbox_background():
    """Warm sandbox without blocking server startup."""
    try:
        manager = get_sandbox_manager()
        sandbox_id = await manager.get_sandbox_id()
        logger.info(f"Sandbox pre-warmed: {sandbox_id}")
    except Exception as e:
        logger.warning(f"Sandbox pre-warm failed (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ToonTalk backend starting up...")
    # Fire sandbox warm-up in background — server is available immediately
    asyncio.create_task(_warm_sandbox_background())
    yield
    logger.info("ToonTalk backend shutting down, stopping sandbox...")
    try:
        manager = get_sandbox_manager()
        await manager.stop()
    except Exception:
        pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="ToonTalk API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Voxtral-generated MP3s
_TTS_CACHE = Path(__file__).parent / "tts_cache"
_TTS_CACHE.mkdir(exist_ok=True)
app.mount("/tts-audio", StaticFiles(directory=str(_TTS_CACHE)), name="tts-audio")

# Serve Flux-generated character images
_CHAR_IMG_DIR = Path(__file__).parent / "character_images"
_CHAR_IMG_DIR.mkdir(exist_ok=True)
app.mount("/character-images", StaticFiles(directory=str(_CHAR_IMG_DIR)), name="character-images")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _determine_bubble_position(character_name: str, scene_context: dict) -> str:
    chars = scene_context.get("characters", [])
    for c in chars:
        name = c.get("name", "").lower() if isinstance(c, dict) else str(c).lower()
        if character_name in name:
            pos = c.get("position", "center") if isinstance(c, dict) else "center"
            if "left" in str(pos):
                return "top-left"
            elif "right" in str(pos):
                return "top-right"
    return "top-right"


# ── Request models ────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    video_id: str
    timestamp: float
    question: str
    collection_id: Optional[str] = None


class TTSRequest(BaseModel):
    video_id: str
    character_name: str
    text: str
    collection_id: Optional[str] = None


# ── Video endpoints ───────────────────────────────────────────────────────────

@app.get("/api/videos")
async def list_videos():
    svc = VideoDBService()
    videos = svc.list_videos()
    return {"videos": videos}


@app.get("/api/video/{video_id}")
async def get_video(video_id: str, collection_id: Optional[str] = None):
    svc = VideoDBService()
    meta = svc.get_metadata(video_id)
    if not meta:
        raise HTTPException(404, f"Video {video_id} not found")

    stream_url = await svc.get_stream_url(video_id, collection_id)
    return {**meta, "stream_url": stream_url}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...), title: str = Form(default="")):
    svc = VideoDBService()
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = await svc.upload_video(file_path=tmp_path, title=title or None)
    finally:
        os.unlink(tmp_path)
    return result


@app.post("/api/upload-url")
async def upload_from_url(body: dict):
    url = body.get("url", "")
    if not url:
        raise HTTPException(400, "url required")
    title = body.get("title", "")
    svc = VideoDBService()
    result = await svc.upload_video(url=url, title=title or None)
    return result


_processing_jobs: dict = {}  # job_id → {"status": "running"|"complete"|"error", "message": str, "progress": int}


@app.post("/api/process/{video_id}")
async def process_video(video_id: str, body: dict):
    import uuid
    job_id = f"job-{uuid.uuid4()}"
    collection_id = body.get("collection_id")

    _processing_jobs[job_id] = {"status": "running", "message": "Starting...", "progress": 5, "video_id": video_id}

    async def _run_pipeline():
        svc = VideoDBService()
        llm = get_llm_service()
        try:
            meta = svc.get_metadata(video_id)
            cid  = collection_id or (meta.get("collection_id") if meta else None)
            video_title = meta.get("name", "") if meta else ""

            # Step 0: LLM anime enrichment — detect language from title, then ask
            # the LLM who the characters are with dialogue in the correct language.
            if video_title and not (meta or {}).get("anime_info"):
                _processing_jobs[job_id].update({
                    "message": "🤖 Anime/show identify kar raha hai...", "progress": 8
                })
                # Quick title-based language detection (confirmed by spoken word index later)
                lang_hint = llm.detect_language_from_title(video_title)
                logger.info(f"[process] language hint from title '{video_title}': {lang_hint}")

                anime_info = await llm.infer_anime_characters(
                    video_title, detected_language=lang_hint
                )
                meta = svc.get_metadata(video_id) or {}
                meta["anime_info"] = anime_info
                meta["video_language"] = anime_info.get("detected_language", lang_hint)
                svc._save_metadata(video_id, meta)
                logger.info(
                    f"[process] anime_info saved: {anime_info.get('anime_name')} "
                    f"lang={meta['video_language']} — {len(anime_info.get('characters', []))} chars"
                )
            else:
                anime_info = (meta or {}).get("anime_info", {})

            # Step 1: Scene indexing (VLM)
            _processing_jobs[job_id].update({"message": "🎬 Scene index bana raha hai (VLM)...", "progress": 20})
            if not meta or not meta.get("scene_index_id"):
                await svc.index_scenes(video_id, cid)
                logger.info(f"[process] scene index done for {video_id}")
            else:
                logger.info(f"[process] scene index already exists for {video_id}")

            _processing_jobs[job_id].update({"message": "🗣️ Dialogue index bana raha hai...", "progress": 55})

            # Step 2: Spoken word indexing
            meta = svc.get_metadata(video_id)
            if not meta or not meta.get("spoken_word_indexed"):
                await svc.index_spoken_words(video_id, cid)
                logger.info(f"[process] spoken word index done for {video_id}")
            else:
                logger.info(f"[process] spoken word index already exists for {video_id}")

            # Step 2b: Confirm language from actual transcribed dialogue.
            # The spoken word index now has real text — sample it and check the script.
            # This overrides the title-hint if the two disagree (e.g. title says nothing,
            # but the dialogue is clearly Devanagari Hindi or clearly ASCII English).
            meta = svc.get_metadata(video_id) or {}
            confirmed_lang = await svc.detect_language_from_spoken_index(video_id, cid)
            if confirmed_lang != "unknown":
                prev_lang = meta.get("video_language", "unknown")
                if confirmed_lang != prev_lang:
                    logger.info(
                        f"[process] language updated from spoken index: "
                        f"{prev_lang} → {confirmed_lang}"
                    )
                    # Re-run anime_info with confirmed language if dialogue changed
                    if prev_lang == "unknown" or prev_lang != confirmed_lang:
                        anime_info = await llm.infer_anime_characters(
                            video_title, detected_language=confirmed_lang
                        )
                        meta["anime_info"] = anime_info
                meta["video_language"] = confirmed_lang
                svc._save_metadata(video_id, meta)

            _processing_jobs[job_id].update({"message": "🔍 Characters detect kar raha hai...", "progress": 75})

            # Step 3: Detect which characters ACTUALLY APPEAR in this video via VLM
            await svc.detect_characters_from_scene_index(video_id, cid)
            meta = svc.get_metadata(video_id) or {}
            raw_detected = meta.get("detected_characters_raw", [])   # exact VLM names
            mapped_detected = meta.get("detected_characters", [])    # registry-mapped keys
            logger.info(
                f"[process] VLM confirmed {len(raw_detected)} character(s) in video: {raw_detected}"
            )

            # Step 3b: Map VLM-detected names → anime_info slugs (for unknown chars like Light Yagami)
            anime_chars_map = {c["slug"]: c for c in anime_info.get("characters", []) if c.get("slug")}

            confirmed_in_video: list[str] = []
            for raw_name in raw_detected:
                # Exact slug match
                if raw_name in anime_chars_map:
                    confirmed_in_video.append(raw_name)
                    continue
                # Partial match (e.g. "light" matches "light yagami")
                match = next(
                    (slug for slug in anime_chars_map if raw_name in slug or slug in raw_name),
                    None,
                )
                if match:
                    confirmed_in_video.append(match)
                else:
                    # Unknown character not in anime_info — still detected visually, keep it
                    confirmed_in_video.append(raw_name)

            # Deduplicate, preserve order
            seen = set()
            confirmed_in_video = [x for x in confirmed_in_video if not (x in seen or seen.add(x))]

            # Save final confirmed character list.
            # Use confirmed_in_video as the ONLY source — do NOT union with
            # mapped_detected (registry-mapped keys) because that bleeds
            # Shinchan/Doraemon characters into unrelated videos via loose alias matches.
            meta["detected_characters"] = confirmed_in_video
            svc._save_metadata(video_id, meta)

            logger.info(
                f"[process] {len(confirmed_in_video)} character(s) confirmed in video "
                f"after cross-reference: {confirmed_in_video}"
            )
            _processing_jobs[job_id].update({
                "message": f"🎭 {len(confirmed_in_video)} character(s) mila — awaaz clone shuru...",
                "progress": 78,
            })

            # Step 4: Verify which characters ACTUALLY SPEAK in this clip.
            # Search each character's typical dialogue in the spoken word index.
            # A single-character Death Note clip should return ["light yagami"] only,
            # not the full cast of 5 just because LLM knows the show.
            _processing_jobs[job_id].update({
                "message": "🔊 Kaun kaun bol raha hai check kar raha hai...", "progress": 79,
            })
            if anime_chars_map:
                speaking_chars = await svc.find_speaking_characters(video_id, anime_info, cid)
            else:
                speaking_chars = confirmed_in_video

            if speaking_chars:
                extract_targets = speaking_chars[:3]
                logger.info(f"[process] confirmed speaking characters: {extract_targets}")
            elif confirmed_in_video:
                extract_targets = confirmed_in_video[:3]
                logger.info(f"[process] fallback to VLM-detected: {extract_targets}")
            elif anime_chars_map:
                # Last resort — protagonist from anime_info
                role_order = {"protagonist": 0, "antagonist": 1, "side character": 2}
                sorted_chars = sorted(
                    anime_chars_map.values(),
                    key=lambda c: role_order.get(c.get("role", "side character"), 2)
                )
                extract_targets = [c["slug"] for c in sorted_chars[:1]]
                logger.info(f"[process] last resort — protagonist only: {extract_targets}")
            else:
                extract_targets = mapped_detected[:3]

            # Save confirmed speaking characters to metadata
            meta = svc.get_metadata(video_id) or {}
            meta["detected_characters"] = extract_targets
            svc._save_metadata(video_id, meta)

            if not extract_targets:
                logger.warning("[process] no characters to extract voice for — skipping voice step")
            else:
                logger.info(f"[process] extracting voice for {len(extract_targets)} character(s): {extract_targets}")

            for i, char_slug in enumerate(extract_targets):
                pct = 80 + int(((i + 1) / max(len(extract_targets), 1)) * 18)
                char_display = anime_chars_map.get(char_slug, {}).get("name", char_slug.title())
                _processing_jobs[job_id].update({
                    "message": f"🎤 {char_display} ki awaaz clone kar raha hai ({i+1}/{len(extract_targets)})...",
                    "progress": pct,
                })
                path = await svc.extract_character_ref_audio(
                    video_id, char_slug, cid, anime_info=anime_info
                )
                if path:
                    logger.info(f"[process] ✅ ref audio ready for {char_slug}: {path}")
                else:
                    logger.warning(f"[process] ⚠️ ref audio extraction failed for {char_slug}")

            _processing_jobs[job_id].update({
                "status": "complete",
                "message": f"✅ Ready! {len(extract_targets)} character(s) ki awaaz clone ho gayi!",
                "progress": 100,
            })

        except Exception as e:
            logger.error(f"[process] pipeline failed for {video_id}: {e}", exc_info=True)
            _processing_jobs[job_id].update({"status": "error", "message": f"❌ {e}", "progress": 0})

    asyncio.create_task(_run_pipeline())
    return {"job_id": job_id, "video_id": video_id}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    from fastapi.responses import StreamingResponse
    import json as _json

    async def event_stream():
        import asyncio as _asyncio
        # Poll the job state and stream progress events
        for _ in range(300):  # max 5 min (300 × 1s)
            state = _processing_jobs.get(job_id)
            if not state:
                yield f'data: {_json.dumps({"event": "complete", "message": "Ready", "progress": 100})}\n\n'
                return
            event = "progress"
            if state["status"] == "complete":
                event = "complete"
            elif state["status"] == "error":
                event = "error"
            yield f'data: {_json.dumps({"event": event, "message": state["message"], "progress": state["progress"]})}\n\n'
            if event in ("complete", "error"):
                return
            await _asyncio.sleep(1)
        yield f'data: {_json.dumps({"event": "error", "message": "Timeout", "progress": 0})}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Q&A endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/ask")
async def ask_character(req: AskRequest):
    """
    Text Q&A — returns answer text in ~5s.
    Frontend calls /api/generate-tts separately for audio.
    """
    svc = VideoDBService()
    llm = get_llm_service()

    meta = svc.get_metadata(req.video_id)
    if not meta:
        raise HTTPException(404, f"Video {req.video_id} not found")

    video_language = meta.get("detected_language") or meta.get("video_language", "hindi")
    question_language = get_llm_service().__class__.detect_question_language(req.question)

    # Use only characters detected in THIS video — never bleed Shinchan chars into other videos.
    # Priority: extracted voice refs → registry-mapped keys → raw VLM names (for unknown anime chars)
    available_chars = (
        list(meta.get("character_voices", {}).keys())
        or meta.get("detected_characters", [])
        or meta.get("detected_characters_raw", [])
        or ["generic"]
    )

    logger.info(f"[ask] scene context for {req.video_id}@{req.timestamp}s")
    # Tight ±5s window — gives the exact scene at the paused frame, not a wide window
    scene_context = await svc.get_scene_context(
        req.video_id, req.timestamp, req.collection_id, window_seconds=5.0
    )
    character_name = await llm.detect_character(req.question, scene_context, available_chars)
    logger.info(f"[ask] character={character_name}, fetching dialogue...")

    # 1. Character-specific dialogue near this timestamp (tight ±15s)
    char_dialogue = await svc.get_character_dialogue(
        video_id=req.video_id,
        character_name=character_name,
        query=req.question,
        collection_id=req.collection_id,
        num_results=4,
        timestamp=req.timestamp,
        window_seconds=15.0,
    )

    # 2. ALL nearby speech (any character) — gives scene audio context even when
    #    character-specific search returns nothing (e.g. background noise, crowd)
    nearby_speech = await svc.get_character_dialogue(
        video_id=req.video_id,
        character_name="",           # empty → search question text only, no char prefix
        query=req.question,
        collection_id=req.collection_id,
        num_results=3,
        timestamp=req.timestamp,
        window_seconds=10.0,
    )

    # Deduplicate by text — char_dialogue takes priority
    seen_texts = {d["text"] for d in char_dialogue}
    dialogue_snippets = char_dialogue + [d for d in nearby_speech if d["text"] not in seen_texts]
    logger.info(
        f"[ask] {len(char_dialogue)} char snippets + {len(nearby_speech)} nearby "
        f"= {len(dialogue_snippets)} total for {character_name}"
    )

    answer_text = await llm.generate_character_answer(
        question=req.question,
        character_name=character_name,
        scene_context=scene_context,
        dialogue_snippets=dialogue_snippets,
        timestamp=req.timestamp,
        anime_info=meta.get("anime_info"),
        question_language=question_language,
        video_language=video_language,
    )

    bubble_position = _determine_bubble_position(character_name, scene_context)
    bubble_style = CHARACTER_BUBBLE_STYLES.get(character_name, CHARACTER_BUBBLE_STYLES["generic"])

    return {
        "character": character_name,
        "character_display": CHARACTER_PERSONAS.get(character_name, {}).get("hindi_name", character_name),
        "answer_text": answer_text,
        "bubble_config": {
            "position": bubble_position,
            "style": bubble_style,
            "shape": bubble_style.get("shape", "round"),
        },
        "scene_context": scene_context,
        "timestamp": req.timestamp,
        "video_language": video_language,
        "question_language": question_language,
    }


@app.post("/api/generate-tts")
async def generate_tts(req: TTSRequest):
    """
    Fast TTS via Voxtral Mini TTS (OpenRouter) — near-realtime ~1.5-2.5s.
    Uses character voice reference audio for zero-shot cloning where supported.
    Falls back to Voxtral preset voice if ref_audio passthrough is rejected.
    OmniVoice path kept intact in videodb_service.py — not called here.
    """
    voxtral = get_voxtral_service()
    svc     = VideoDBService()

    # Use video-extracted ref audio if available (exact voice from this episode)
    meta          = svc.get_metadata(req.video_id) or {}
    ref_audio_path = meta.get("character_ref_audio", {}).get(req.character_name)

    audio_url = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: voxtral.synthesize(
            text=req.text,
            character_name=req.character_name,
            ref_audio_path=ref_audio_path,
        ),
    )
    return {"audio_url": audio_url}


@app.post("/api/clone-voice")
async def clone_voice_endpoint(req: TTSRequest):
    """
    Phase 2: OmniVoice true clone — needs warm sandbox, ~25-90s.
    Called in background AFTER ElevenLabs is already playing.
    """
    svc = VideoDBService()
    audio_url = await svc.clone_character_voice(
        text=req.text,
        character_name=req.character_name,
        video_id=req.video_id,
        collection_id=req.collection_id,
    )
    return {"audio_url": audio_url}


@app.post("/api/ask-voice")
async def ask_character_voice(
    video_id: str = Form(...),
    timestamp: float = Form(...),
    audio: UploadFile = File(...),
    collection_id: Optional[str] = Form(None),
):
    """
    Voice input — transcribes child's mic, returns answer text.
    """
    llm = get_llm_service()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        question = await llm.transcribe_audio(tmp_path)
        if not question:
            raise HTTPException(400, "Could not transcribe audio. Please try again.")
        logger.info(f"Transcribed question: {question}")
    finally:
        os.unlink(tmp_path)

    return await ask_character(
        AskRequest(
            video_id=video_id,
            timestamp=timestamp,
            question=question,
            collection_id=collection_id,
        )
    )


# ── Sandbox endpoints ─────────────────────────────────────────────────────────

@app.post("/api/warmup")
async def warmup_sandbox():
    try:
        manager = get_sandbox_manager()
        sandbox_id = await manager.get_sandbox_id()
        return {"status": "ready", "sandbox_id": sandbox_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/sandbox-status")
async def sandbox_status():
    try:
        manager = get_sandbox_manager()
        sid = manager.current_sandbox_id
        if sid:
            return {"ready": True, "sandbox_id": sid, "status": "warm"}
        return {"ready": False, "status": "cold"}
    except Exception:
        return {"ready": False, "status": "unknown"}


@app.post("/api/stop-sandbox")
async def stop_sandbox():
    try:
        manager = get_sandbox_manager()
        await manager.stop()
        return {"status": "stopped"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/characters")
async def list_characters():
    return {"characters": list(CHARACTER_PERSONAS.keys())}


# ── Voxtral usage monitoring ──────────────────────────────────────────────────

@app.get("/api/voxtral-usage")
async def voxtral_usage():
    """Current Voxtral spend: chars, calls, est_cost_usd, cap status."""
    return get_voxtral_service().get_usage()


@app.post("/api/voxtral-usage/reset")
async def voxtral_usage_reset():
    """Zero the spend counter (manual reset after confirming cap)."""
    get_voxtral_service().reset_usage()
    return {"status": "reset", "usage": get_voxtral_service().get_usage()}


# ── Character image endpoint ──────────────────────────────────────────────────

@app.get("/api/character-image/{video_id}/{character_name}")
async def get_character_image(video_id: str, character_name: str):
    """
    Get or generate a character portrait image using Flux.
    Returns {"image_url": "/character-images/...png"} or {"image_url": null}
    """
    svc = VideoDBService()
    meta = svc.get_metadata(video_id) or {}
    anime_info = meta.get("anime_info", {})
    anime_name = anime_info.get("anime_name", "")

    # Check if character exists in anime_info for description
    char_data = next(
        (c for c in anime_info.get("characters", []) if c.get("slug") == character_name),
        {}
    )
    description = char_data.get("personality", "")
    role = char_data.get("role", "")

    collection_id = meta.get("collection_id")
    flux = get_flux_service()

    # Run in executor (blocking call to VideoDB Flux)
    image_url = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: flux.generate_character_image(
            character_name=character_name,
            anime_name=anime_name,
            description=description,
            role=role,
            collection_id=collection_id,
        )
    )

    return {"image_url": image_url}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_excludes=["scripts/*", "scripts/**/*", "*.md", "*.txt"],
        log_level="info",
    )
