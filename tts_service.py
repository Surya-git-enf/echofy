# -> tts_service.py
"""
Four interchangeable TTS engines, all exposing the same
generate_speech(text, language_key, out_path, engine) signature:

  - "fish"   -> Fish Audio (best quality, supports emotion tags + cloning,
                paid, requires FISH_AUDIO_API_KEY). Falls back to "edge"
                automatically on any Fish Audio failure so a job never dies
                just because Fish Audio hiccuped or quota ran out.
  - "edge"   -> Microsoft Edge Neural voices (edge-tts). Free, no key.
  - "sarvam" -> Sarvam AI bulbul:v3. Best accent accuracy for Indian
                languages, paid, requires SARVAM_API_KEY.
  - "gtts"   -> Google Translate TTS. Free, no key, most robotic.
"""
import asyncio
import base64
import os
import re

import requests

from languages import get_language

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

EMOTION_TAG_PATTERN = re.compile(r"\[(excited|confident|laugh|sad|angry|calm|whisper|serious)\]\s*", re.IGNORECASE)


def strip_emotion_tags(text: str) -> str:
    """Engines that don't understand [tag] markup should never see it literally spoken."""
    return EMOTION_TAG_PATTERN.sub("", text).strip()


# ---------------- Fish Audio ----------------

def generate_speech_fish(text: str, language_key: str, out_path: str):
    api_key = os.getenv("FISH_AUDIO_API_KEY")
    if not api_key:
        raise RuntimeError("FISH_AUDIO_API_KEY is not set.")

    from fish_audio_sdk import Session, TTSRequest  # imported lazily so the app still runs without this package installed if unused

    lang = get_language(language_key)
    session = Session(api_key)

    request_kwargs = {"text": text}
    if lang.get("fish_voice_id"):
        request_kwargs["reference_id"] = lang["fish_voice_id"]

    request = TTSRequest(**request_kwargs)

    with open(out_path, "wb") as f:
        for chunk in session.tts(request):
            f.write(chunk)


# ---------------- Edge-TTS (free fallback) ----------------

def generate_speech_edge(text: str, language_key: str, out_path: str):
    import edge_tts  # lazy import, same reasoning as above

    lang = get_language(language_key)
    voice = lang.get("edge_voice")
    if not voice:
        raise RuntimeError(f"No Edge voice configured for language: {language_key}")

    clean_text = strip_emotion_tags(text)

    async def _run():
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(out_path)

    asyncio.run(_run())


# ---------------- Sarvam AI ----------------

def generate_speech_sarvam(text: str, language_key: str, out_path: str):
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "SARVAM_API_KEY is not set. Add it to your environment, or choose "
            "a different voice engine."
        )
    lang = get_language(language_key)
    clean_text = strip_emotion_tags(text)

    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    payload = {
        "inputs": [clean_text],
        "target_language_code": lang["sarvam_code"],
        "model": "bulbul:v3",
        "speaker": "meera",
    }
    resp = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    audio_b64 = data["audios"][0]
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(audio_b64))


# ---------------- gTTS (free, most basic) ----------------

def generate_speech_gtts(text: str, language_key: str, out_path: str):
    from gtts import gTTS  # lazy import

    lang = get_language(language_key)
    clean_text = strip_emotion_tags(text)
    tts = gTTS(text=clean_text, lang=lang["gtts_code"])
    tts.save(out_path)


# ---------------- Dispatcher ----------------

def generate_speech(text: str, language_key: str, out_path: str, engine: str = "fish"):
    if not text or not text.strip():
        return  # nothing to synthesize for an empty segment

    if engine == "fish":
        try:
            generate_speech_fish(text, language_key, out_path)
            return
        except Exception as fish_error:  # noqa: BLE001 — deliberate broad catch for automatic fallback
            print(f"[tts_service] Fish Audio failed ({fish_error}); falling back to Edge-TTS.")
            generate_speech_edge(text, language_key, out_path)
            return

    if engine == "edge":
        generate_speech_edge(text, language_key, out_path)
    elif engine == "sarvam":
        generate_speech_sarvam(text, language_key, out_path)
    elif engine == "gtts":
        generate_speech_gtts(text, language_key, out_path)
    else:
        raise ValueError(f"Unknown voice_engine: {engine}")
