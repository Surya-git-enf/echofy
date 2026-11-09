
# Echofy

**Dub any video into Indian languages with a different voice for every character, over the original music and effects.**

Echofy takes a video, understands who is speaking and how, rewrites the dialogue the way a native speaker would say it, voices it with **Gnani Vachana**, and mixes it back over the original background soundtrack.

Built by [Suri](https://github.com/Surya-git-enf) as part of the **Great Indian Internship**.

> Live backend: `https://echofy-ty4q.onrender.com` (Render free tier, so the first request after idle can take about a minute to wake up).

---

## Why Gnani is the core

Voice quality decides whether a dub feels like a film or like a screen reader. Echofy's default and recommended engine is **[Gnani](https://www.gnani.ai/) Vachana**, model `timbre-v3.0`, because it is the engine that makes Indian-language dubbing work:

| What Echofy needs | What Gnani Vachana gives it |
|---|---|
| Natural Indian-language speech | Native voices for Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, plus English and Hinglish |
| One distinct voice per character | A catalog of 13 `timbre-v3.0` voices, each of which speaks every supported language, grouped by persona (professional, energetic, conversational, warm, authoritative) |
| Acting, not just reading | Inline emotion tags such as `<excited>`, `<shouting>`, `<whispers>`, `<laugh>`, `<sigh>`, `<sniffles>`, `<pauses>` |
| Speed control to fit lip timing | A per-request `speed` value, which Echofy nudges per emotion (for example faster for anger, slower for sadness) |

How Echofy uses it (`tts_service.py`, `voice_casting.py`):

1. **Gemini labels the scene.** For every line it returns the speaker, gender, age group, archetype and one emotion.
2. **`gnani_prepare()` turns emotions into Vachana tags.** Gemini's bracket words (`[laughing]`, `[whispers]`, `[angry]`...) are mapped to the tags Vachana understands. Vachana has no `<angry>` tag, so `<shouting>` is used, and only when the line has an exclamation mark. Quiet anger stays a spoken line, just faster.
3. **`voice_casting.build_cast()` gives every character a voice.** Persona fit comes first (an elder or villain gets an authoritative or professional voice, a kid or hero gets an energetic one). If a scene has more characters than voices of one gender, voices are reused with a pitch shift so no two characters ever share the same sound.
4. **One request at a time.** Vachana allows a single active request, so the TTS loop is deliberately sequential and retries on `429` and `5xx` with backoff.

Gnani is called through `POST https://api.vachana.ai/api/v1/tts/inference` with the `X-API-Key-ID` header. Set `GNANI_API_KEY` on the server.

Other engines exist for languages Gnani cannot speak (French, Japanese, and so on): `fish`, `edge`, `sarvam`, `gtts`, and a self-hosted `echofy` (IndicF5) option. Routing is strict: whichever engine you request is the only one that runs, with no silent fallback.

---

## How it works

```mermaid
flowchart LR
    A[Upload video] --> B[Validate + extract audio]
    B --> C[Separate vocals / background<br/>stemsplit.io, FFmpeg fallback]
    C --> D[Gemini 2.5 Flash<br/>transcribe, identify characters,<br/>adapt dialogue + emotion]
    D --> E[Voice casting<br/>one voice per character]
    E --> F[Gnani Vachana TTS<br/>line by line, with emotion tags]
    F --> G[Fit each line to its time slot]
    G --> H[Mix over ORIGINAL background<br/>ducking + loudness normalisation]
    H --> I[Merge into video<br/>download via signed URL]
```

Key behaviours:

- **Original music and effects are always kept.** The dubbed dialogue is mixed over the separated background track. There is no vocals-only output path.
- **Adapted, not translated.** The Gemini prompt asks for native slang, natural loanwords and a separate speaking style per character, with line lengths close to the original so they fit the timing.
- **Full-length audio.** The dubbed track is padded to the video length so the video is never cut short.
- **Fail early.** Uploads are validated with FFmpeg before anything is stored, and Supabase transfers are size-verified and retried, which prevents truncated-file bugs.
- **Stable character voices** across the whole clip, up to 8 characters per scene.

---

## Stack

| Layer | Tech |
|---|---|
| API | Python, FastAPI, background tasks |
| Voice (core) | **Gnani Vachana `timbre-v3.0`** |
| Understanding and dialogue | Gemini 2.5 Flash (`google-genai`) |
| Stem separation | stemsplit.io API, FFmpeg center-cancel fallback |
| Audio and video | FFmpeg |
| Storage and jobs | Supabase (Postgres tables plus Storage buckets) |
| Frontend | Next.js 15, React 19, GSAP |
| Hosting | Render (backend) |

---

## Supported languages

Default engine (`gnani`):

`english`, `hinglish`, `hindi`, `telugu`, `tamil`, `kannada`, `malayalam`, `marathi`, `bengali`, `gujarati`, `punjabi`

Any other language name is accepted by the API and written by Gemini, but you must pick an engine that can speak it (`fish`, or `edge` for many languages). `engine_can_speak()` rejects bad pairings immediately with a clear message.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/languages` | Language list for dropdowns |
| `POST` | `/api/dub` | Start a job. `multipart/form-data` with `video` (file), `target_language`, optional `voice_engine` (default `gnani`) |
| `GET` | `/api/dub/{job_id}` | Poll status. Returns `status`, `stage`, `progress`, `from_language`, `error`, `download_ready`, `download_url` |
| `GET` | `/` | Health check |

Limits: `.mp4`, `.mov`, `.mkv`, `.webm`, up to 800 MB. Download links are signed Supabase URLs valid for one hour.

```bash
curl -X POST https://echofy-ty4q.onrender.com/api/dub \
  -F "video=@clip.mp4" \
  -F "target_language=telugu" \
  -F "voice_engine=gnani"
# -> {"job_id": "..."}

curl https://echofy-ty4q.onrender.com/api/dub/<job_id>
```




**Suri** — solo founder and developer of Echofy.
