"""
Two interchangeable TTS engines:
  - "gtts"   -> free, no API key, good for local testing end-to-end
  - "sarvam" -> Sarvam AI bulbul:v3, better quality for Indian languages,
                requires SARVAM_API_KEY

Both expose the same generate_speech(text, language_key, out_path) signature
so the pipeline doesn't care which one is active.
"""
import base64
import os

import requests
from gtts import gTTS

from languages import get_language

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


def generate_speech_gtts(text: str, language_key: str, out_path: str):
    lang = get_language(language_key)
    tts = gTTS(text=text, lang=lang["gtts_code"])
    tts.save(out_path)  # gTTS writes mp3; ffmpeg handles mp3 fine downstream


def generate_speech_sarvam(text: str, language_key: str, out_path: str):
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "SARVAM_API_KEY is not set. Add it to backend/.env, or choose the "
            "free 'gtts' voice engine instead."
        )
    lang = get_language(language_key)

    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    payload = {
        "inputs": [text],
        "target_language_code": lang["sarvam_code"],
        "model": "bulbul:v3",
        "speaker": "meera",  # default voice; swap for other Sarvam voices as needed
    }
    resp = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    audio_b64 = data["audios"][0]
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(audio_b64))


def generate_speech(text: str, language_key: str, out_path: str, engine: str = "gtts"):
    if not text.strip():
        return  # nothing to synthesize for an empty segment
    if engine == "sarvam":
        generate_speech_sarvam(text, language_key, out_path)
    else:
        generate_speech_gtts(text, language_key, out_path)

