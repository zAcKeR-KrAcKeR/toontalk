# ToonTalk 🎬 — Cartoon Characters Se Baat Karo!

World's #1 First Talk2Video with Voice Cloning Auto Character Generation !

> **Interactive AI Cartoon Companion for Kids** — powered by VideoDB

ToonTalk lets children *talk to* their favourite cartoon characters. Upload any anime or cartoon episode — the system automatically figures out who's in it, clones their voice directly from the video, and when a kid asks a question the character answers back **in their own cloned voice** with a **full anime-style banner** sliding up over the paused video.

Works for **any cartoon in any language Multilingual** — Hindi dubs, English originals, whatever you upload.

---

## 🏆 VideoDB Primitives Used

| Feature | API |
|---|---|
| Video ingestion | `coll.upload()` / URL ingest |
| Scene understanding | `video.index_scenes(model_name="pro")` — VLM describes every scene |
| Dialogue transcription | `video.index_spoken_words()` — full semantic search index |
| Scene + dialogue search | `video.search(SearchType.semantic)` |
| LLM (character routing + answer) | `coll.generate_text(prompt, model_name="pro")` |
| Voice cloning | `coll.generate_voice()` with `OmniVoice` + `ref_audio` |
| Character art generation | `coll.generate_image(prompt, aspect_ratio="3:4")` — **FLUX** |

---

## ✨ How It Works — Full Pipeline

### Stage 1: Upload

```
User uploads cartoon episode (MP4 file or YouTube URL)
         ↓
VideoDB stores video → returns video_id + stream_url
         ↓
Local metadata file created for this video
```

### Stage 2: Processing (runs once per video, ~5-10 minutes)

```
Video title sent to LLM (VideoDB generate_text)
         ↓
LLM returns full cast: names, personalities, typical dialogue,
language (Hindi dub vs English original)
         ↓
video.index_scenes(model_name="pro")
→ VLM describes every scene: who's visible, emotions, action
         ↓
video.index_spoken_words()
→ Full dialogue indexed for semantic search
         ↓
Language confirmed: sample 10 dialogue lines,
count Devanagari vs ASCII → hindi / english
         ↓
Speaker verification: each character's typical dialogue
searched in spoken word index with score threshold 0.45
→ Only confirmed speakers kept (prevents character bleed-in)
         ↓
Voice extraction: 10-15s clean audio clip per confirmed character
→ ffmpeg extracts + normalises → saved as ref audio
         ↓
Video is READY
```

### Stage 3: Kid Asks a Question

```
Kid watches video normally
         ↓
Presses "Character se Puchho" → video PAUSES
         ↓
Types or speaks their question (Hindi or English)
         ↓
Backend pipeline (~3-5 seconds):

  1. Detect question language
     → Devanagari script? → Hindi
     → Hinglish keywords (yaar, kya, toh, hai...)? → Hindi
     → Otherwise → English

  2. Scene context at pause point (±5 seconds)
     → VLM scene description: what's visible, who's there, emotions

  3. Which character?
     → Keyword match first ("yagami", "shinchan", "doraemon"...)
     → LLM fallback if ambiguous

  4. Dialogue context (±15 seconds)
     → Semantic search: what was actually being said near pause

  5. Language-adaptive answer generation:
     → Hindi video + Hindi question  → Hinglish text (Latin script)
     → Hindi video + English question → English text
     → English video                 → English text
     → Always first-person, scene-aware, under 25 words

  6. Answer text appears on screen instantly (~3-5s)
         ↓
  7. Background TTS (~2 seconds):
     → Voxtral Mini TTS (Mistral) + extracted ref audio
     → Zero-shot voice cloning: answer spoken in character's own voice
     → Audio plays through anime banner
         ↓
  8. Character portrait:
     → VideoDB Flux generates anime portrait from character description
     → White background removed via canvas processing
     → Character "floats" over the banner
     → Cached — instant on future questions
```

### Stage 4: The Banner

```
Anime-style banner slides up from bottom of video:
  ★ CHARACTER NAME KA JAWAB!        ← top strip with name stamp
  ─────────────────────────────────  ← torn paper divider
  "Answer text types out..."         ← dialogue with typewriter effect
  ▶ REPLAY    ●●●  〰〰〰〰〰〰     ← replay + waveform while playing

  Character portrait floats right    ← Flux-generated, white bg removed
  Lightning bolts, particles, aura   ← animated effects
         ↓
Kid taps "Phir Suno" to replay audio
Kid taps "Aur Puchho" for another question
Kid taps "Video Continue Karo" to resume
```

---

## 🧠 What Makes It Smart

### Automatic Cast Detection
No manual tagging needed. The LLM reads the video title → returns full cast with personalities and typical dialogue. *"Death Note"* → Light Yagami, L, Misa Amane. *"Shinchan Hindi"* → Shinchan, Misae, Hiroshi, Kazama...

### No Character Bleed-In
Every character goes through speaker verification before being included. Semantic search on their actual dialogue lines with a score threshold — if Doraemon's lines don't appear in a Death Note video, he's not added.

### Voice Cloned From the Video Itself
The system doesn't use generic TTS voices. It finds a clean 10-15 second clip of the character actually speaking in this specific episode and uses that as the reference for zero-shot voice cloning. The answer sounds like the character from *this* video.

### Language-Aware Everywhere
- Detects video language from actual spoken dialogue (not just title)
- Detects question language from script + keywords
- Adapts response text format accordingly
- Audio always matches the video's language

### Scene-Grounded Answers
The LLM sees exactly what was happening at the paused frame — who's visible, what emotion, what action, what was being said. Answers are specific to the moment, not generic character trivia.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- [VideoDB API Key](https://console.videodb.io) — Medium sandbox tier recommended
- [Groq API Key](https://console.groq.com) — free tier, for voice transcription (Whisper)
- [Mistral API Key](https://console.mistral.ai) — for Voxtral TTS voice cloning

### 1. Setup

```bash
git clone https://github.com/your-username/toontalk.git
cd toontalk

# Copy and fill in your API keys
cp .env.example .env
```

`.env` keys needed:
```
VIDEO_DB_API_KEY=...     # Required — powers everything
GROQ_API_KEY=...         # Required — voice question transcription
MISTRAL_API_KEY=...      # Required — cloned voice TTS
```

### 2. Backend

```bash
cd backend

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# → http://localhost:8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### 4. Upload & Process a Video

1. Open `http://localhost:5173`
2. Click **Upload Video** — paste a YouTube URL or upload an MP4
3. Enter the video title (include the show name, e.g. *"Shinchan Hindi Episode"*)
4. Click **Process** — watch the progress bar (~5-10 min first time)
5. Once ready → click the video → pause → ask anything!

---

## 📁 Project Structure

```
toontalk/
├── backend/
│   ├── main.py                  # FastAPI — all API routes
│   ├── videodb_service.py       # All VideoDB SDK operations
│   ├── llm_service.py           # LLM calls + language detection + Whisper
│   ├── character_config.py      # Character personas + answer prompt
│   ├── voxtral_service.py       # Mistral TTS + spend tracking ($1 cap)
│   ├── flux_service.py          # VideoDB Flux character image generation
│   ├── sandbox_manager.py       # VideoDB sandbox lifecycle (singleton)
│   ├── video_metadata/          # Per-video JSON (characters, voices, indexes)
│   ├── ref_audio/               # Extracted character voice clips
│   ├── tts_cache/               # Generated TTS audio files
│   └── character_images/        # Flux-generated character portraits (cached)
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main app — upload, library, player screens
│   │   ├── components/
│   │   │   ├── VideoPlayer.jsx  # Video player + Q&A panel
│   │   │   ├── CharacterPopup.jsx  # Anime banner overlay with all effects
│   │   │   └── MicButton.jsx    # Voice recorder with waveform
│   │   └── services/api.js      # All backend API calls
│   └── public/characters/       # Static character images (Shinchan, Misae, Hiroshi)
└── .env
```

---

## 🌐 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/upload` | POST | Upload video file |
| `/api/upload-url` | POST | Upload from URL / YouTube |
| `/api/process/{id}` | POST | Start AI processing pipeline |
| `/api/status/{job_id}` | GET SSE | Real-time progress stream |
| `/api/videos` | GET | List all processed videos |
| `/api/video/{id}` | GET | Video metadata + stream URL |
| `/api/ask` | POST | Text question → character answer |
| `/api/ask-voice` | POST | Voice question → character answer |
| `/api/generate-tts` | POST | Generate cloned voice audio |
| `/api/character-image/{vid}/{char}` | GET | Get/generate character portrait |
| `/api/voxtral-usage` | GET | TTS spend tracker |
| `/api/sandbox-status` | GET | VideoDB sandbox status |

---

## 💡 Supported Shows (Auto-detected)

Any show the LLM knows about works automatically — no manual setup. Tested with:

- **Shinchan** (Hindi dub) — full family cast
- **Doraemon** (Hindi dub)
- **Death Note** (English)
- **Naruto** (Hindi or English)
- **Dragon Ball Z**
- **Any cartoon** — generic character fallback if show is unknown

---

## 💰 API Cost Estimate

| Task | Approx Cost |
|---|---|
| Process one episode (scene + spoken word index) | ~$0.50-2.00 VideoDB credits |
| Voice extraction per character | negligible |
| Answer text (LLM) per question | ~$0.001 |
| TTS per answer (~120 chars) | ~$0.002 Mistral |
| Flux character portrait (generated once, cached) | ~$0.01 VideoDB credits |
| **1000 questions on a processed video** | **~$2.00 total** |

---

## 📝 One-Line Pitch

> *"Pause any cartoon, ask the character anything in Hindi or English — they answer back in their own voice, aware of exactly what was happening in the scene."*

---

## 📜 License

MIT — Built for the VideoDB Hackathon 2026
