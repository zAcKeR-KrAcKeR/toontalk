"""
ToonTalk LLM Service
====================
- LLM (character routing + answer generation): VideoDB native generate_text API
  → coll.generate_text(prompt, model_name="pro") — uses VIDEO_DB_API_KEY
  → No OpenAI/Groq key needed for LLM; works directly through the VideoDB SDK.

- Transcription (kid's voice → text): Groq Whisper API (free tier)
  → 7,200 sec/day limit = ~720-1440 questions/day.
  → Uses GROQ_API_KEY.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class LLMService:
    """
    Uses VideoDB's native generate_text API for all LLM calls.
    VIDEO_DB_API_KEY covers everything — no OpenAI/Groq key for LLM.
    """

    def __init__(self):
        self._groq_client = None

    # ── VideoDB native text generation ────────────────────────────────────────

    def _get_coll(self, collection_id: Optional[str] = None):
        """Get a VideoDB collection via the sandbox manager's connection."""
        from sandbox_manager import get_sandbox_manager
        conn = get_sandbox_manager().get_connection()
        if collection_id:
            return conn.get_collection(collection_id)
        return conn.get_collection()

    def _call_llm(
        self,
        prompt: str,
        model_name: str = "pro",
        collection_id: Optional[str] = None,
    ) -> str:
        """
        Call VideoDB's native generate_text API.
        model_name: "basic" (fast), "pro" (balanced), "ultra" (best quality)
        Returns the generated text string.
        """
        coll = self._get_coll(collection_id)
        try:
            result = coll.generate_text(
                prompt=prompt,
                model_name=model_name,
                response_type="text",
            )
            if isinstance(result, dict):
                result = (
                    result.get("output")
                    or result.get("text")
                    or result.get("response")
                    or result.get("result")
                    or str(result)
                )
            logger.debug(f"LLM ({model_name}): {str(result)[:120]}")
            return (result or "").strip()
        except Exception as e:
            logger.error(f"LLM call failed ({type(e).__name__}): {e}")
            raise

    # ── Anime title enrichment ────────────────────────────────────────────────

    @staticmethod
    def detect_question_language(question: str) -> str:
        """Returns 'hi' for Hindi/Hinglish, 'en' for English."""
        if any('ऀ' <= ch <= 'ॿ' for ch in question):
            return "hi"
        hinglish = {"kya", "kab", "kaise", "kyun", "kaun", "kahan", "woh", "yeh", "tum",
                    "aap", "hum", "main", "mujhe", "tumhe", "usse", "hai", "hain", "tha",
                    "thi", "kar", "karo", "aur", "lekin", "toh", "bhi", "nahi", "haan",
                    "yaar", "bhai", "raha", "rahi", "gaya", "gayi", "accha", "theek",
                    "bahut", "kuch", "sab", "phir", "pehle", "baad"}
        words = set(question.lower().split())
        if len(words & hinglish) >= 2:
            return "hi"
        return "en"

    @staticmethod
    def detect_language_from_title(title: str) -> str:
        """
        Quick heuristic: look for explicit language hints in the title.
        Returns "hindi" or "english". Falls back to "unknown" when ambiguous
        (the spoken word index will confirm later).
        """
        t = title.lower()
        hindi_hints = ["hindi", "हिंदी", "hindi dub", "hindi dubbed", "hindi version",
                       "हिंदी डब", "star vijay", "cartoon network india", "pogo"]
        english_hints = ["english", "english dub", "eng dub", "english sub",
                         "english version", "original", "japanese", "eng"]
        if any(h in t for h in hindi_hints):
            return "hindi"
        if any(h in t for h in english_hints):
            return "english"
        # Presence of Devanagari script → Hindi
        if any("ऀ" <= ch <= "ॿ" for ch in title):
            return "hindi"
        return "unknown"

    async def infer_anime_characters(
        self,
        title: str,
        detected_language: str = "unknown",
        collection_id: Optional[str] = None,
    ) -> dict:
        """
        Given a video title and detected language, ask the LLM who the characters
        are, their personalities, and typical dialogue in the VIDEO'S ACTUAL LANGUAGE.

        detected_language: "hindi" | "english" | "unknown"
          - hindi   → typical_dialogue in Hindi/Hinglish (Hindi dub lines)
          - english → typical_dialogue in English (original/English dub lines)
          - unknown → LLM infers from title; dialogue provided in both

        Returns:
        {
          "anime_name": "Death Note",
          "detected_language": "english",
          "characters": [
            {
              "name": "Light Yagami",
              "slug": "light yagami",
              "role": "protagonist",
              "gender": "male",
              "personality": "calculating genius who believes he is justice itself",
              "typical_dialogue": ["I am justice", "This is my perfect victory", "All according to plan"],
              "voice_type": "calm confident dramatic male"
            }
          ]
        }
        """
        import asyncio
        import json as _json

        # Build language instruction for the LLM
        if detected_language == "hindi":
            lang_instruction = (
                "The video is the HINDI DUB. Provide character names as used in Hindi dub "
                "and typical_dialogue in Hindi/Hinglish exactly as spoken in the Hindi dubbed version."
            )
        elif detected_language == "english":
            lang_instruction = (
                "The video is in ENGLISH (original or English dub). Provide character names in English "
                "and typical_dialogue as spoken in the English version."
            )
        else:
            lang_instruction = (
                "Language is unclear from the title. Detect it from the show/title context. "
                "If the show originally aired in Hindi (Indian cartoon) use Hindi dialogue. "
                "If it's a Japanese anime or western show, detect whether this seems to be "
                "a Hindi dub or English version from the title and provide dialogue accordingly. "
                "Add a 'detected_language' field: 'hindi' or 'english'."
            )

        prompt = f"""You are an anime/cartoon expert. Based on this video title, identify the show and its characters.

Video title: "{title}"
Language context: {lang_instruction}

Instructions:
1. Identify the anime/cartoon show from the title
2. List ALL speaking characters (main + important side characters, max 5)
3. For each character, provide typical dialogue in the CORRECT LANGUAGE for this video
4. If you don't recognize the show, use character names in the title as hints

Respond ONLY in this exact JSON format (no extra text, no markdown fences):
{{
  "anime_name": "<show name>",
  "detected_language": "<hindi|english>",
  "characters": [
    {{
      "name": "<character name>",
      "slug": "<lowercase with spaces, e.g. light yagami>",
      "role": "<protagonist|antagonist|side character>",
      "gender": "<male|female>",
      "personality": "<1 sentence personality>",
      "typical_dialogue": ["<phrase 1 in correct language>", "<phrase 2>", "<phrase 3>", "<phrase 4>"],
      "voice_type": "<e.g. calm confident dramatic male>"
    }}
  ]
}}"""

        try:
            raw = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._call_llm(prompt, model_name="pro", collection_id=collection_id),
            )
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()

            result = _json.loads(clean)

            # Normalise: if language was unknown, use what LLM detected
            if detected_language == "unknown":
                detected_language = result.get("detected_language", "english")
            result["detected_language"] = detected_language

            chars = result.get("characters", [])
            logger.info(
                f"[anime-infer] '{title}' → {result.get('anime_name')} "
                f"lang={detected_language} "
                f"chars={[c.get('name') for c in chars]}"
            )
            return result
        except Exception as e:
            logger.warning(f"[anime-infer] failed for '{title}': {e}")
            return {"anime_name": title, "detected_language": detected_language, "characters": []}

    # ── Character Detection ───────────────────────────────────────────────────

    async def detect_character(
        self,
        question: str,
        scene_context: dict,
        available_characters: list[str],
        collection_id: Optional[str] = None,
    ) -> str:
        """
        Determine which cartoon character the child is asking about.
        Returns character name in lowercase (e.g. 'shinchan', 'doraemon').
        Fast keyword path first; LLM fallback if ambiguous.
        """
        import asyncio
        from character_config import CHARACTER_DETECTION_KEYWORDS

        question_lower = question.lower()

        # Fast path: keyword match — no LLM needed
        for char_name, keywords in CHARACTER_DETECTION_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in question_lower:
                    logger.info(f"Character detected by keyword: {char_name}")
                    return char_name

        # LLM fallback for ambiguous questions
        raw_chars = scene_context.get("characters", [])
        visible = [
            c.get("name", "") if isinstance(c, dict) else str(c)
            for c in raw_chars
        ]
        visible_str = ", ".join(v for v in visible if v) or (
            ", ".join(available_characters) or "unknown"
        )
        scene_desc = scene_context.get("scene_description", "a cartoon scene")

        prompt = (
            f"Task: Detect which cartoon character a child is asking about.\n\n"
            f"Child's question: \"{question}\"\n"
            f"Scene: {scene_desc}\n"
            f"Characters visible in scene: {visible_str}\n"
            f"Available characters: {', '.join(available_characters)}\n\n"
            f"Reply with ONLY one character name in lowercase from the available list "
            f"(e.g. shinchan / doraemon / nobita). If unclear, pick the most prominent "
            f"character shown in the scene. No explanation, just the name."
        )

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._call_llm(prompt, model_name="basic", collection_id=collection_id),
            )
            result = result.lower().strip().split()[0].strip("'\".,'!?")

            # Snap to closest valid character
            if result not in available_characters:
                matched = next(
                    (c for c in available_characters if result in c or c in result), None
                )
                result = matched or (available_characters[0] if available_characters else "generic")

            logger.info(f"Character detected by LLM: {result}")
            return result or "generic"
        except Exception as e:
            logger.warning(f"Character detection LLM failed: {e}, defaulting to first available")
            return available_characters[0] if available_characters else "generic"

    # ── Answer Generation ─────────────────────────────────────────────────────

    async def generate_character_answer(
        self,
        question: str,
        character_name: str,
        scene_context: dict,
        dialogue_snippets: list = None,
        language: str = "hi",
        collection_id: Optional[str] = None,
        timestamp: Optional[float] = None,
        anime_info: Optional[dict] = None,
        question_language: str = "hi",
        video_language: str = "hindi",
    ) -> str:
        """
        Generate an in-character Hindi answer grounded in the actual episode context.
        Uses:
         - VLM scene description (what is visually happening)
         - Spoken word semantic search results (what was actually said nearby)
        """
        import asyncio
        from character_config import CHARACTER_PERSONAS, ANSWER_GENERATION_PROMPT, get_dynamic_persona

        persona = CHARACTER_PERSONAS.get(character_name) or get_dynamic_persona(character_name, anime_info, video_language)

        # Defensive: scene_context must be a dict
        if not isinstance(scene_context, dict):
            scene_context = {"scene_description": str(scene_context), "characters": []}

        # Format timestamp as MM:SS
        ts_str = ""
        if timestamp is not None:
            m, s = divmod(int(timestamp), 60)
            ts_str = f"{m}:{s:02d}"

        # Format scene context
        scene_desc = (
            scene_context.get("scene_description_hindi")
            or scene_context.get("scene_description", "episode mein kuch ho raha hai")
        )
        chars_visible = scene_context.get("characters", [])
        char_info = (
            ", ".join(
                f"{c['name']} ({c.get('emotion', 'neutral')})" if isinstance(c, dict) else str(c)
                for c in chars_visible
            ) or "unknown characters"
        )
        action = scene_context.get("action", "")

        ts_prefix = f"[Video paused at {ts_str}] " if ts_str else ""
        scene_full = f"{ts_prefix}VISUAL SCENE: {scene_desc} | Characters visible: {char_info}"
        if action:
            scene_full += f" | Action: {action}"

        # Format actual spoken dialogue from the video (±5-15s from pause point)
        dialogue_context = ""
        if dialogue_snippets:
            lines = [s.get("text", "").strip() for s in dialogue_snippets if s.get("text", "").strip()]
            if lines:
                dialogue_context = "\n\nWHAT WAS BEING SAID in this scene (actual dialogue from the video):\n" + "\n".join(
                    f'- "{line}"' for line in lines[:5]
                )
                logger.info(f"Dialogue context for {character_name}: {lines[:2]}")

        # Build language instruction based on video + question language
        if video_language == "hindi":
            if question_language == "hi":
                language_instruction = (
                    "CRITICAL — OUTPUT LANGUAGE: Write in HINGLISH only. "
                    "That means Hindi words but spelled in English script (Latin letters). "
                    "NO Devanagari script at all. "
                    "Example good: 'Yaar, main toh bilkul nahi samjha! Scene mein kuch ajeeb ho raha hai!' "
                    "Example bad: 'मैं नहीं समझा' (Devanagari — FORBIDDEN)"
                )
            else:
                language_instruction = (
                    "CRITICAL — OUTPUT LANGUAGE: Write in English only. "
                    "The child asked in English so answer in English. "
                    "Keep your character personality but use English words. "
                    "Example: 'Hey, I was just watching TV when this happened! So confusing!'"
                )
        else:
            language_instruction = (
                "CRITICAL — OUTPUT LANGUAGE: Write in English only. "
                "This is an English cartoon — answer in natural English. "
                "Keep your character personality."
            )

        answer_prompt_body = ANSWER_GENERATION_PROMPT.format(
            character_name=persona["hindi_name"],
            character_persona=persona["description"],
            scene_context=scene_full + dialogue_context,
            question=question,
            language_instruction=language_instruction,
        )

        # Combine system persona + answer prompt into a single prompt for generate_text
        full_prompt = (
            f"{persona['system_prompt']}\n\n"
            f"---\n\n"
            f"{answer_prompt_body}"
        )

        try:
            answer = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._call_llm(
                    prompt=full_prompt,
                    model_name="pro",
                    collection_id=collection_id,
                ),
            )
            logger.info(f"Answer for {character_name}: {answer}")
            return answer or persona.get("greeting", "Namaste!")
        except Exception as e:
            logger.error(f"Answer generation failed for {character_name}: {e}")
            return persona.get("greeting", "Namaste!")

    # ── Whisper Transcription via Groq ────────────────────────────────────────

    async def transcribe_audio(self, audio_path: str) -> str:
        """
        Transcribe child's voice recording using Groq's Whisper API.

        Groq free tier: 7,200 sec audio/day (~1440 questions at 5s each).
        Model: whisper-large-v3-turbo (fastest, best for Hindi/mixed language)
        """
        import asyncio

        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("GROQ_API_KEY not set. Get a free key at console.groq.com")

        if self._groq_client is None:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=groq_key)
            except ImportError:
                raise ImportError("Run: pip install groq")

        def _transcribe():
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            for model in ["whisper-large-v3-turbo", "whisper-large-v3"]:
                try:
                    response = self._groq_client.audio.transcriptions.create(
                        model=model,
                        file=("audio.webm", audio_bytes, "audio/webm"),
                        language="hi",
                        prompt=(
                            "यह एक बच्चे का सवाल है cartoon character के बारे में। "
                            "Hindi aur English dono ho sakti hai."
                        ),
                        response_format="text",
                    )
                    return response.strip() if isinstance(response, str) else response.text.strip()
                except Exception as e:
                    if "rate" in str(e).lower():
                        logger.warning(f"Groq rate limit on {model}: {e}")
                        raise
                    logger.warning(f"Groq {model} failed: {e}, trying next...")

            return ""

        try:
            text = await asyncio.get_event_loop().run_in_executor(None, _transcribe)
            logger.info(f"Transcribed ({len(text)} chars): {text}")
            return text
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ""


# ── Global singleton ──────────────────────────────────────────────────────────

_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
