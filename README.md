# 🎬 Echofy

> **AI-powered video dubbing that sounds like a real studio did it.**  
> Original background music preserved · Every character gets their own voice · Any language supported

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Supabase](https://img.shields.io/badge/Supabase-Backend-3ECF8E?logo=supabase&logoColor=white)](https://supabase.com/)
[![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-8E75B2?logo=google-gemini&logoColor=white)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ What Makes Echofy Different

| Feature | Typical Tools | Echofy |
|---------|--------------|--------|
| **Background music** | Stripped or replaced | **Always preserved** — vocals separated, dub layered over original soundtrack |
| **Character voices** | Single voice for all | **Distinct voice per character** — 4-5 speakers, each with unique timbre/pitch |
| **Languages** | Limited dropdown | **Any language** — Gemini writes native dialogue, engine checked at request time |
| **Translation** | Word-for-word | **Localisation** — slang, loanwords, character-specific register |
| **Quality gate** | Manual listening | **Automated scoring** — loudness, timing, background preservation, Gemini judge |

---

## 🏗 Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Frontend   │────▶│   FastAPI    │────▶│  Supabase       │
│  (Next.js)  │     │   Backend    │     │  (Storage + DB) │
└─────────────┘     └──────┬───────┘     └────────┬────────┘
                           │                      │
                    ┌──────▼──────┐      ┌────────▼────────┐
                    │  Pipeline   │      │  Stem Cache     │
                    │  (Dubbing)  │      │  (.cache/stems) │
                    └──────┬──────┘      └─────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌─────────┐ ┌──────────┐ ┌──────────┐
         │ Gemini  │ │   TTS    │ │  FFmpeg  │
         │ 2.5     │ │ (Gnani/  │ │  (Mix &  │
         │ Flash   │ │  Fish/   │ │  Merge)  │
         └─────────┘ │  Edge)   │ └──────────┘
                     └──────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+ (for frontend)
- FFmpeg installed (`apt-get install ffmpeg` / `brew install ffmpeg`)
- API keys (see [Environment Variables](#-environment-variables))

### Backend
```bash
# Clone and enter
git clone <your-repo> && cd echofy

# Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your keys (see below)

# Run API server
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### One-Command Local Dub (for testing)
```bash
# Needs all API keys set in .env
python scripts/run_local_dub.py --languages telugu hindi spanish --engine gnani
```

---

## 🔐 Environment Variables

| Variable | Required For | Description |
|----------|--------------|-------------|
| `GEMINI_API_KEY` | **Always** | Google AI Studio key for transcription & localisation |
| `SUPABASE_URL` | **Always** | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | **Always** | Service role key (bypasses RLS) |
| `STEMSPLIT_API_KEY` | **Always** | stemsplit.io for vocal separation (free tier: 10 min/day) |
| `GNANI_API_KEY` | Engine `gnani` | Gnani Vachana (default engine, Indian languages + English) |
| `FISH_AUDIO_API_KEY` | Engine `fish` | Fish Audio for multilingual TTS |
| `FISH_VOICE_POOL` | Engine `fish` | JSON: `{"male": ["id1"], "female": ["id2"]}` — gives each character a different voice |
| `SARVAM_API_KEY` | Engine `sarvam` | Sarvam AI (Indian languages) |
| `ECHOFY_VOICE_SERVICE_URL` | Engine `echofy` | Self-hosted IndicF5 endpoint |
| `ALLOWED_ORIGINS` | CORS | Comma-separated origins, or `*` |
| `DUB_ENGINE` | Local script | Default engine for `run_local_dub.py` |

> **Note**: Never commit `.env`. Keep secrets in Render/CodeSpace settings.

---

## 🎙 Voice Engines

| Engine | Cost | Languages | Voices | Emotion Tags | Best For |
|--------|------|-----------|--------|--------------|----------|
| **Gnani** (default) | Paid | English, Hinglish, 10 Indian | 13 (timbre-v3.0) | `<excited>`, `<whispers>`, `<laugh>`, `<shouting>`, `<sigh>` | Indian languages, expressive delivery |
| **Fish Audio** | Paid | **Any** (multilingual) | Account-specific (via `FISH_VOICE_POOL`) | `[laughing]`, `[whispers]`, `[angry]`, `[excited]`, `[sad]` | Non-Indian languages, max voice variety |
| **Edge TTS** | Free | 100+ (neural voices) | Runtime lookup per locale | None (pitch/rate only) | Quick tests, no API keys |
| **Sarvam** | Paid | Indian languages | Bulbul v3 | Limited | Indian language alternative |
| **Echofy (self-hosted)** | Free (CPU) | Indic languages | Reference clips per archetype+emotion | Via reference clip | Privacy, offline, IndicF5 |
| **gTTS** | Free | 100+ | One robotic voice | None | Baseline / last resort |

### Gnani Emotion Tags (inline in translated text)
```text
<excited>This is amazing!<excited>
<whispers>Don't tell anyone.<whispers>
<laugh>Hahaha!<laugh>
<shouting>Get back here!<shouting>
<sigh>Fine, I'll do it.<sigh>
```

---

## 📦 API Reference

### `GET /api/languages`
Returns supported languages for the dropdown.
```json
{
  "languages": [
    {"key": "telugu", "label": "Telugu"},
    {"key": "hindi", "label": "Hindi"},
    ...
  ]
}
```

### `POST /api/dub`
Start a dubbing job. Multipart form:
- `video` (file) — `.mp4`, `.mov`, `.mkv`, `.webm` (≤800 MB)
- `target_language` (string) — e.g. `telugu`, `spanish`, `japanese`
- `voice_engine` (string, optional) — `gnani` (default), `fish`, `edge`, `sarvam`, `echofy`, `gtts`
- `preserve_background_music` (bool, ignored) — **Always true**

Response:
```json
{"job_id": "abc123..."}
```

### `GET /api/dub/{job_id}`
Poll for status (every 2s recommended).
```json
{
  "job_id": "abc123...",
  "status": "processing",
  "stage": "Generating dubbed speech",
  "progress": 55,
  "from_language": "english",
  "download_ready": false,
  "download_url": null
}
```
When `status === "completed"`, `download_url` is a signed Supabase URL (1hr expiry).

---

## 🧪 Quality Gate (Automated Scoring)

Every run is scored against `test/reference_profile.json`:

| Metric | Target | What It Checks |
|--------|--------|----------------|
| Integrated loudness | -22 to -14 LUFS | Broadcast-standard level |
| True peak | ≤ -1 dBTP | No clipping |
| Background RMS (gaps) | ≥ -52 dBFS | Music audible in pauses |
| Background swell | ≥ +2 dB | Music rises between dialogue |
| Voice-over-background | 6–26 dB | Dialogue clear over music |
| Duration tolerance | ±0.5s | Output matches input length |
| Segment fit | ≥ 90% | Lines fit their time slots |
| Speedup limit | ≤ 1.36x | No chipmunk effect |
| Script match | ≥ 0.6 | Gemini judge scores dialogue quality |

**Pass**: All gates green + judge score ≥ 7  
**Pass (Unjudged)**: Gates green but judge didn't run (fix and rerun)  
**Fail**: Any gate red or judge < 7

Run the gate locally:
```bash
python scripts/eval_dubbing.py test/outputs/input__telugu
```

---

## 📁 Project Structure

```
echofy/
├── main.py                 # FastAPI app, endpoints
├── pipeline.py             # Core dubbing pipeline (orchestrator)
├── gemini_service.py       # Transcription + localisation (Gemini 2.5 Flash)
├── tts_service.py          # TTS routing (Gnani/Fish/Edge/Sarvam/Echofy/gTTS)
├── video_service.py        # FFmpeg: extract, separate, mix, merge
├── voice_casting.py        # Distinct voice per character
├── languages.py            # Language table + engine compatibility
├── supabase_service.py     # Storage + job persistence
├── requirements.txt        # Python deps
├── scripts/
│   ├── run_local_dub.py    # CLI: run pipeline on test/input/*
│   └── eval_dubbing.py     # Quality gate scorer
├── test/
│   ├── input/              # Source videos (git-ignored outputs go to test/outputs/)
│   ├── examples/           # Reference dub (Dubbed.mp4)
│   └── reference_profile.json
├── frontend/               # Next.js 15 app
│   ├── app/page.tsx        # Main page (Experience component)
│   ├── components/         # UI components (UploadStudio, EqualizerLoader, etc.)
│   └── public/icon.png     # Logo
└── .cache/stems/           # Cached stem separations (saves API minutes)
```

---

## 🛠 Development

### Running Tests
```bash
# Offline plumbing test (no API keys needed)
python tests/test_offline_e2e.py

# Full pipeline test (needs all keys)
python scripts/run_local_dub.py --languages telugu hindi
```

### Adding a Test Clip
Drop `test/input/<name>.mp4` + `<name>.json`:
```json
{"expected_speakers": 4}
```
The gate will require ≥4 distinct character voices.

### Updating the Knowledge Graph
```bash
graphify update .
```

---

## 🚢 Deployment (Render)

1. Push to GitHub
2. Create **Web Service** on Render:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Add all env vars from [Environment Variables](#-environment-variables)
4. Frontend is served automatically from `/` (static mount in `main.py`)

---

## 📝 License

MIT — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- **Gnani Vachana** — expressive Indian-language TTS
- **Fish Audio** — multilingual voice cloning
- **Microsoft Edge TTS** — free neural voices
- **Google Gemini** — dialogue adaptation & judging
- **stemsplit.io** — vocal separation
- **Supabase** — storage & job queue
- **FFmpeg** — the audio/video Swiss Army knife

---

> Built with care by **Suri** · JARVIS on systems duty