"""Fix the corrupted videodb_service.py by surgically replacing the damaged section."""
content = open('videodb_service.py', encoding='utf-8').read()

# The corruption starts right after the get_character_dialogue try block's results.shots line
# Good code ends just before "return [\n                {\n                    \"text\"        try:"
# We split on the last clean line before corruption

SPLIT_ON = '            results = await asyncio.get_event_loop().run_in_executor(\n                None,\n                lambda: video.search(\n                    f\"{character_name} {query}\",\n                    index_type=IndexType.spoken_word,\n                    search_type=SearchType.semantic,\n                ),\n            )\n'

idx = content.rfind(SPLIT_ON)
print(f"Split point found at byte {idx}")

# Good prefix = everything through the search executor call
prefix = content[:idx + len(SPLIT_ON)]

# Verify the prefix ends correctly
print("Prefix tail:", repr(prefix[-100:]))

# The stream section onwards is clean — find it
STREAM_MARKER = '    # \u2500\u2500\u2500 Stream URL + Frame \u2500'
stream_idx = content.find(STREAM_MARKER)
print(f"Stream section at byte {stream_idx}")

suffix = content[stream_idx:]
print("Suffix head:", repr(suffix[:80]))

# The clean replacement for the damaged middle section
FIXED_MIDDLE = '''            return [
                {
                    "text": getattr(shot, "text", ""),
                    "start": shot.start,
                    "end": shot.end,
                    "score": getattr(shot, "score", 0),
                }
                for shot in results.shots[:num_results]
            ]
        except Exception as e:
            logger.error(f"Dialogue search failed: {e}")
            return []

    # \u2500\u2500\u2500 TTS with Voice Clone \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    async def generate_character_voice(
        self,
        text: str,
        character_name: str,
        video_id: str,
        collection_id: Optional[str] = None,
        language: str = "hi",
    ) -> Optional[str]:
        """
        Generate TTS with the character\'s cloned voice.

        Path A (has ref_audio): OmniVoice zero-shot voice clone.
          \u2192 True cloning: captures pitch, gender, accent from ref audio.
          \u2192 Works for male AND female voices (misae, nene, shizuka etc.)
          \u2192 No pre-warmed sandbox needed \u2014 wait=True handles it internally.
          \u2192 ~20-30s per call.

        Path B (no ref_audio yet): ElevenLabs preset voice.
          \u2192 Instant (~1s) generic fallback until voice is cloned.

        Returns playable URL or None on failure.
        """
        coll = self._coll(collection_id)
        meta = self.get_metadata(video_id)
        voice_data = meta.get("character_voices", {}).get(character_name) if meta else None

        try:
            if voice_data and voice_data.get("ref_audio_url"):
                # \u2500\u2500 Path A: OmniVoice \u2014 TRUE zero-shot voice clone \u2500\u2500
                # Handles any gender. No sandbox pre-warming needed.
                source = voice_data.get("source", "video")
                logger.info(f"[TTS] OmniVoice clone for {character_name} (source={source})")
                audio = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: coll.generate_voice(
                        text=text,
                        model_name=SandboxModel.OMNIVOICE,
                        config={
                            "ref_audio": voice_data["ref_audio_url"],
                            "ref_text":  "",
                            "language":  language,
                        },
                        wait=True,
                        timeout=120,
                    ),
                )
            else:
                # \u2500\u2500 Path B: ElevenLabs preset \u2014 instant fallback, no clone \u2500\u2500
                logger.info(f"[TTS] No clone for {character_name} \u2014 ElevenLabs preset fallback")
                voice_map = {
                    "shinchan": "Charlie",   # energetic kid
                    "doraemon": "George",    # warm, friendly
                    "nobita":   "Harry",     # gentle, slightly whiny
                    "misae":    "Sarah",     # stern mom voice
                    "hiroshi":  "Daniel",    # calm dad voice
                    "gian":     "Arnold",    # loud bully
                    "shizuka":  "Alice",     # sweet girl
                    "nene":     "Alice",     # sweet girl
                }
                voice_name = voice_map.get(character_name, "Default")
                job = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: coll.generate_voice(
                        text=text,
                        model_name="elevenlabs",
                        voice_name=voice_name,
                        config={"language": language},
                    ),
                )
                audio = job if not hasattr(job, "wait") else await asyncio.get_event_loop().run_in_executor(
                    None, lambda: job.wait(timeout=60, interval=2)
                )

            if audio is None:
                logger.warning(f"[TTS] returned None for {character_name}")
                return None

            audio_url = audio.generate_url()
            logger.info(f"[TTS] Ready for {character_name}: {audio_url[:60]}")
            return audio_url

        except Exception as e:
            logger.error(f"[TTS] generation failed for {character_name}: {e}")
            return None

    '''

fixed = prefix + FIXED_MIDDLE + suffix

# Verify it's valid Python before writing
import ast
try:
    ast.parse(fixed)
    print("\nSYNTAX OK — writing fixed file...")
    with open('videodb_service.py', 'w', encoding='utf-8') as f:
        f.write(fixed)
    print("Done! Lines:", fixed.count('\n'))
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    # Show context around error
    lines = fixed.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+3)):
        print(f"{i+1}: {lines[i]}")
