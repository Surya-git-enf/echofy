<div align="center">

# Echofy

### Dub any video into Indian languages. Keep the music. Give every character their own voice.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Gnani Vachana](https://img.shields.io/badge/TTS-Gnani%20Vachana%20timbre--v3.0-007BA7)](https://docs.gnani.ai)
[![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-8E75B2?logo=google-gemini&logoColor=white)](https://ai.google.dev/)
[![Supabase](https://img.shields.io/badge/Supabase-Storage%20%2B%20Jobs-3ECF8E?logo=supabase&logoColor=white)](https://supabase.com/)

[How Echofy uses Gnani](#how-echofy-uses-gnani) ·
[Pipeline](#how-a-dub-is-made) ·
[Quick start](#quick-start) ·
[API](#api) ·
[Frontend](#frontend) ·
[Quality gate](#quality-gate)

</div>

---

## What it does

You upload a video. Echofy hands back the same video, dubbed the way a real studio would do it:

- **New voices in the target language.** Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, English and Hinglish with the default engine.
- **The original music and effects stay.** Vocals are separated out, the dubbed dialogue goes on top, and the background ducks under every line and swells back in the gaps.
- **Every character sounds like a different person.** Up to eight speakers per scene, each with a stable voice for the whole video.
- **Dialogue is adapted, not translated word for word.** Native slang, everyday loanwords, and each character's own way of speaking.

Backend: FastAPI on Render with Supabase for storage and job state. Frontend: Next.js with a scroll-scrubbed hero, a one-time scratch card that grants 100 credits, and a single-page upload flow.

---

## How Echofy uses Gnani

[Gnani Vachana](https://docs.gnani.ai) is Echofy's **default voice engine**. Every dubbed line in a normal job is spoken by Vachana's `timbre-v3.0` model. Everything below is what the code in [`tts_service.py`](tts_service.py), [`voice_casting.py`](voice_casting.py) and [`languages.py`](languages.py) actually does.

### The request

```text
POST https://api.vachana.ai/api/v1/tts/inference
X-API-Key-ID: <GNANI_API_KEY>
```

```json
{
  "text": "<excited> ఇది అద్భుతం!",
  "model": "timbre-v3.0",
  "voice": "Shubham",
  "language": "te-IN",
  "speed": 1.08,
  "audio_config": { "sample_rate": 44100, "num_channels": 1, "container": "mp3", "bitrate": "192k" }
}
```

One request per dialogue line. Vachana allows one active request at a time, so the TTS loop in [`pipeline.py`](pipeline.py) is deliberately sequential and is never parallelised.

### Languages

Echofy checks the pairing **before** a job starts ([`engine_can_speak()`](languages.py)), so an unsupported language fails in the first second with a clear message, not three minutes into the pipeline.

| Echofy key | Vachana code | | Echofy key | Vachana code |
|---|---|---|---|---|
| `english` | `en-IN` | | `kannada` | `kn-IN` |
| `hinglish` | `hi-en` | | `malayalam` | `ml-IN` |
| `hindi` | `hi-IN` | | `marathi` | `mr-IN` |
| `telugu` | `te-IN` | | `bengali` | `bn-IN` |
| `tamil` | `ta-IN` | | `gujarati` | `gu-IN` |
| | | | `punjabi` | `pa-IN` |

Any other language (French, Japanese, …) is rejected for `gnani` with a hint to use `fish` or `edge`. All 13 `timbre-v3.0` voices speak every language above.

### One stable voice per character

[`voice_casting.build_cast()`](voice_casting.py) receives the characters Gemini found in the scene (gender, age group, archetype) and assigns each a Vachana voice from the `timbre-v3.0` catalog.

| | Professional | Energetic | Conversational | Warm | Authoritative |
|---|---|---|---|---|---|
| **Male** | Avinash, Harshad, Prakash | Shubham | Devansh | Yashraj | |
| **Female** | | Lakshmi, Vasudha | | Chetana, Kalpana, Shivani, Tarika | Riyaa |

- **Persona fit first.** Elders, villains and deep monsters get authoritative and professional voices first. Young heroes, boys and anyone under "adult" get energetic and conversational ones first. Everyone else starts with conversational and warm.
- **Least-used voice wins.** Each new character takes the best-fitting voice that has been used the fewest times, so a five-character scene uses five different Vachana voices.
- **More characters than voices.** If a scene has more speakers of one gender than there are voices, a voice is reused and the character is separated with a post-processing pitch shift (steps of 2.5 semitones, capped at ±7). Every character still gets a unique `voice_id`.
- **Stable for the whole video.** The cast is built once per job, so a character never changes voice halfway through.

### Emotion through Vachana's inline audio tags

Gemini labels every line with an emotion and may add bracket cues such as `[laughing]`. [`gnani_prepare()`](tts_service.py) turns those into the tags `timbre-v3.0` understands and picks a speaking speed.

| Gemini emotion | Tag added to the start of the line | Speed |
|---|---|---|
| `excited` | `<excited>` | 1.08 |
| `angry` | `<shouting>` (only if the line contains `!`; quiet anger stays a plain, faster line) | 1.10 |
| `whisper` | `<whispers>` | 0.95 |
| `sad` | `<sigh>` | 0.90 |
| `calm`, `serious` | none | 0.95 |
| `neutral` | none | 1.00 |

Bracket cues inside the dialogue are converted one by one: `[laughing]` → `<laugh>`, `[crying]` → `<sniffles>`, `[yelling]` → `<shouting>`, `[sighs]` → `<sigh>`, `[pause]` → `<pauses>`, and more. Unknown cues are dropped. A line that already carries a tag does not get a second one. Speed is clamped to 0.85–1.15.

Vachana has no `<angry>` tag. `<shouting>` is the closest it offers, and the code says so.

### Failure handling

| Situation | What Echofy does |
|---|---|
| `GNANI_API_KEY` missing | The API rejects the job at request time (HTTP 400) before any compute is spent |
| 401 / 403 | Fails immediately with the Gnani response and "check key, account status and credits" |
| 429, 5xx, network error, or a JSON/short body instead of audio | Retries up to 4 times with 2, 4, 8, 16 second backoff |
| Line with only tags and no words | Fails that line with a clear message instead of sending it |
| Other 4xx | Fails with Gnani's error text |

There is **no automatic fallback to another engine**. If you ask for `gnani`, you get Gnani or a clear error, never a silent switch to a different voice.

### What happens to the audio after Vachana

The returned 44.1 kHz mp3 is trimmed of leading and trailing silence, sped up (never beyond 1.36×) only if it is longer than its time slot, converted to 44.1 kHz stereo, levelled to −19 LUFS, mixed over the original background with sidechain ducking, and loudness-normalised. See [video_service.py](video_service.py).

### Gnani speech-to-text

Transcription uses Gnani **`prisma-v3.0`** through `POST https://api.vachana.ai/stt/v3` ([`stt_service.py`](stt_service.py)). The synchronous endpoint accepts at most 30 seconds of audio and returns text only, with no timestamps and no speaker labels, so Echofy works around that:

1. ffmpeg silence detection finds the spoken stretches of the separated vocals. Stretches over 12 seconds are split again at their pauses with looser settings, and nothing is sent that is longer than 25 seconds.
2. Each stretch goes to Gnani as a 16 kHz mono WAV, one request at a time. The stretch's own start and end become the line's timing. Stretches Gnani hears no speech in are dropped.
3. Language is `en-IN,hi-IN,te-IN,ta-IN` by default (prisma-v3.0 takes up to four codes). Set `GNANI_STT_LANGUAGE` to override, for example `te-IN`.

Gemini 2.5 Flash then receives the timed lines plus the audio. It decides who is speaking and in which emotion, and writes the adapted dialogue. It returns exactly one line per source id, and timing and source text are always taken from Gnani's transcript, never from Gemini. Set `TRANSCRIBE_ENGINE=gemini` to let Gemini transcribe by itself instead.

### Tested

[`tests/test_offline_e2e.py`](tests/test_offline_e2e.py) runs the real Gnani code path with only the HTTP call replaced. It asserts the endpoint and payload shape, the 429-then-success retry, the missing-key error, that a five-character scene reaches Vachana with five different voices, and that unsupported languages are refused. It cannot judge how the voices sound; a human listen is still the final check.

---

## How a dub is made

```mermaid
flowchart LR
    A[Upload video] --> B[Extract audio]
    B --> C[Separate vocals<br/>from music]
    C --> S[Gnani STT prisma-v3.0<br/>timed transcript]
    S --> D[Gemini 2.5 Flash<br/>speakers, emotion<br/>+ adapted dialogue]
    D --> E[Cast one voice<br/>per character]
    E --> F[Gnani Vachana<br/>speak each line]
    F --> G[Trim, fit to time slot,<br/>level to -19 LUFS]
    G --> H[Mix over original<br/>background, ducked]
    H --> I[Merge into video]
    I --> J[Signed download URL]
```

| Progress | Stage |
|---|---|
| 1–5 % | Starting, downloading the upload from Supabase |
| 12 % | Extracting audio |
| 22 % | Separating vocals from music (stemsplit.io, cached by audio hash; FFmpeg fallback if the API fails) |
| 30 % | Transcribing with Gnani speech-to-text |
| 38 % | Writing the dub (Gemini) |
| 45–70 % | Generating dubbed speech, one Vachana request per line |
| 75 % | Building the dubbed dialogue track |
| 82 % | Remixing with the original background (sidechain ducking) |
| 88 % | Merging with the video |
| 95–100 % | Uploading the result, job marked `completed` |

**Rules the pipeline never breaks**

- The original background music and effects are always kept. `preserve_background_music` is accepted for old clients and ignored.
- Every character gets one stable, distinct voice.
- The dubbed track covers the full video length, so the video is never cut short.
- Dialogue is localised, not literal.

---

## Quick start

### Prerequisites

Python 3.11+, Node.js 20+, FFmpeg on your `PATH`, and the keys listed under [Environment variables](#environment-variables).

### Backend

```bash
git clone https://github.com/Surya-git-enf/echofy && cd echofy

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then fill in your keys
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local  # NEXT_PUBLIC_API_URL points at your backend
npm run dev                 # http://localhost:3000
```

### Dub a clip from the command line

```bash
python scripts/run_local_dub.py --languages telugu hindi --engine gnani
```

Results go to `test/outputs/<input>__<language>/` and are scored by the quality gate.

---

## Environment variables

| Variable | Needed for | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | always | Dialogue adaptation, speakers, emotions, quality judge |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | always | Storage and job state |
| `STEMSPLIT_API_KEY` | always | Vocal separation (without it the FFmpeg fallback background is used) |
| `GNANI_API_KEY` | always (speech-to-text) and engine `gnani` (default, TTS) | Gnani Vachana STT and TTS |
| `GNANI_STT_LANGUAGE` | optional | Source language codes for STT, default `en-IN,hi-IN,te-IN,ta-IN` |
| `TRANSCRIBE_ENGINE` | optional | `gnani` (default) or `gemini` to let Gemini transcribe |
| `FISH_AUDIO_API_KEY`, `FISH_VOICE_POOL` | engine `fish` | Any-language TTS; the pool is JSON `{"male": ["id"], "female": ["id"]}` |
| `SARVAM_API_KEY` | engine `sarvam` | Sarvam TTS |
| `ECHOFY_VOICE_SERVICE_URL` | engine `echofy` | Self-hosted IndicF5 service |
| `ALLOWED_ORIGINS` | optional | CORS origins, comma-separated, or `*` |
| `DUB_ENGINE`, `STEM_CACHE_DIR` | optional | Defaults for the local script |

Never commit `.env`. Keep secrets in Render and Codespaces settings.

---

## API

### `POST /api/dub`

Multipart form.

| Field | Notes |
|---|---|
| `video` | `.mp4`, `.mov`, `.mkv` or `.webm`, up to 800 MB |
| `target_language` | e.g. `telugu`, `hindi`, `hinglish` |
| `voice_engine` | `gnani` (default), `fish`, `edge`, `sarvam`, `echofy`, `gtts` |

Returns `{"job_id": "…"}`. Unsupported engine and language pairs and missing server keys return HTTP 400 with the reason.

### `GET /api/dub/{job_id}`

```json
{
  "job_id": "65cf237a-…",
  "status": "processing",
  "stage": "Generating dubbed speech",
  "progress": 55,
  "from_language": "english",
  "error": null,
  "download_ready": false,
  "download_url": null
}
```

`status` is `processing`, `completed` or `failed`. When completed, `download_url` is a signed Supabase URL.

### `GET /api/languages`

The supported language list.

---

## Voice engines

| Engine | Cost | Languages | Notes |
|---|---|---|---|
| **`gnani`** (default) | Paid | English, Hinglish and 10 Indian languages | 13 voices, inline emotion tags |
| `fish` | Paid | Any | Voices come from your account (`FISH_VOICE_POOL`) |
| `edge` | Free | Many | Voices looked up per locale, pitch and rate vary per character |
| `sarvam` | Paid | Indian languages | Single speaker voice |
| `echofy` | Self-hosted | Indic | IndicF5 with reference clips per archetype and emotion |
| `gtts` | Free | Many | One robotic voice, baseline only |

Engines never fall back to each other.

---

## Frontend

A single Next.js page in [`frontend/`](frontend), built around one idea: the page is the product demo.

- **Hero.** A scroll-scrubbed sequence of 300 frames drawn on a canvas, as on Apple's product pages. On portrait phones the whole frame is shown with a tagline above it.
- **Scratch card.** At the end of the hero a glitter card appears once. Scratch it and 100 credits are added. The flag is kept in the browser, so it never reappears.
- **Upload.** Drop an MP4, pick a language from chips written in their own scripts (हिन्दी, తెలుగు, தமிழ்…), press **let's dub it**. Cost is 2 credits per started minute.
- **Loading.** Equaliser bars with the Echofy echo curves in the middle, and rotating status lines while the backend job runs.
- **Result.** The dubbed video appears under the card with a download button.
- **Studio and showcase.** Three 3D cards (voice styles, dub moods, language vibes) and a draggable 3D spiral of vertical sample dubs that play on hover.

Stack: Next.js 15, React 19, TypeScript, GSAP ScrollTrigger. Deploy the `frontend` folder to Vercel (Root Directory `frontend`) with `NEXT_PUBLIC_API_URL` set to your backend.

> Credits are stored in the browser for now, so clearing site data resets them. Move the balance to the server before charging for it.

---

## Quality gate

Every local run is scored against [`test/reference_profile.json`](test/reference_profile.json) by [`scripts/eval_dubbing.py`](scripts/eval_dubbing.py).

| Check | Limit |
|---|---|
| Duration vs source | within 0.5 s |
| Integrated loudness | −22 to −14 LUFS |
| True peak | at most −1 dBTP |
| Background audible in gaps, and swelling back | gap level ≥ −52 dBFS, swell ≥ 2 dB |
| Dialogue over background | 6 to 26 dB |
| Dubbed vs original speech length | ratio 0.5 to 1.7 |
| Lines fitting their time slot | ≥ 90 % |
| Speed-up applied to any line | at most 1.36× |
| Same-speaker overlap | at most 0.3 s |
| Distinct voices | at least the expected number of characters |
| Dialogue quality | judged by Gemini |

Exit codes: `0` pass, `2` pass but the Gemini judge did not run (does not count as done), `1` fail. The gate measures levels, timing, voices and script; it cannot hear. A human listen is still needed.

```bash
python tests/test_offline_e2e.py                      # plumbing and gate logic, no keys needed
python scripts/run_local_dub.py --languages telugu hindi
python scripts/eval_dubbing.py test/outputs/<input>__<language>
```

---

## Project layout

```text
echofy/
├── main.py              FastAPI app and endpoints
├── pipeline.py          Orchestrates one dubbing job
├── stt_service.py       Gnani speech-to-text: speech chunks, requests, timed lines
├── gemini_service.py    Dialogue writing, speakers, emotions (Gemini 2.5 Flash, v1beta API)
├── tts_service.py       TTS engines; Gnani Vachana lives here
├── voice_casting.py     One distinct voice per character
├── languages.py         Language table and engine/language checks
├── video_service.py     FFmpeg: extract, separate, fit, duck, mix, merge
├── supabase_service.py  Storage and job rows
├── scripts/             run_local_dub.py, eval_dubbing.py
├── tests/               Offline end-to-end tests
├── test/                Inputs, reference profile, outputs (git-ignored)
└── frontend/            Next.js app
```

---

## Deployment

**Backend (Render).** Build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`, then add the environment variables above. The free tier sleeps when idle, so the first request after a pause can take 30 to 60 seconds.

**Frontend (Vercel).** Root Directory `frontend`, environment variable `NEXT_PUBLIC_API_URL`.

---

## Known limits

- Uploads are capped at 800 MB. Slow connections can truncate large uploads, so compress first.
- Credits are client-side (see above).
- Gnani's synchronous STT has no speaker labels or timestamps, so speaker identity comes from Gemini listening to the audio. Its batch API can separate two speakers, which is not used.
- A stretch of speech with no pause longer than 25 seconds is cut at an arbitrary point before transcription.
- Gnani voices cover English, Hinglish and 10 Indian languages. Other languages need the `fish` or `edge` engine.
- Automated checks do not replace listening to the result.

---

## Built with

[Gnani Vachana](https://docs.gnani.ai) for voices, [Google Gemini](https://ai.google.dev/) for dialogue, [stemsplit.io](https://stemsplit.io) for vocal separation, [Supabase](https://supabase.com/) for storage, [FFmpeg](https://ffmpeg.org/) for the mix, [Fish Audio](https://fish.audio), [Edge TTS](https://github.com/rany2/edge-tts) and [Sarvam](https://www.sarvam.ai/) as alternative engines.

<div align="center">

Built by **Suri** for the Great Indian Internship with Gnani.

</div>
