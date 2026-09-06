# -> tts_service.py
"""
Strict routing: whichever engine is requested is the ONLY engine that runs.
No automatic fallback between engines — if "fish" fails, the job fails with
a descriptive RuntimeError so the real cause shows up in the logs, instead
of silently downgrading to a robotic voice.
"""
import base64
import os
import re

import requests

from languages import get_language

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

EMOTION_TAG_PATTERN = re.compile(r"\[(excited|confident|laugh|sad|angry|calm|whisper|serious)\]\s*", re.IGNORECASE)

# Map each character archetype to a Fish Audio voice model (reference_id).
# These are account-specific — pick/clone voices in your Fish Audio
# playground and paste their reference_id values in here.
ARCHETYPE_VOICE_MAP = {
    "anime_villain":  None,  # e.g. "your-fish-voice-id-for-villain"
    "monster_deep":   None,
    "young_boy":      None,
    "cool_hero":      None,
    "mature_female":  None,
    "default":        None,  # falls back to Fish Audio's default voice if None
}


def strip_emotion_tags(text: str) -> str:
    """For engines that can't understand [tag] markup (edge/sarvam/gtts)."""
    return EMOTION_TAG_PATTERN.sub("", text).strip()


# ---------------- Fish Audio (strict — no fallback) ----------------

def generate_speech_fish(text: str, language_key: str, out_path: str, character_profile: str = "default"):
    api_key = os.getenv("FISH_AUDIO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FISH_AUDIO_API_KEY is not set. voice_engine='fish' was requested but "
            "cannot run without this key — set it in your environment."
        )

    reference_id = ARCHETYPE_VOICE_MAP.get(character_profile, ARCHETYPE_VOICE_MAP["default"])

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "format": "mp3",
    }
    if reference_id:
        payload["reference_id"] = reference_id

    try:
        resp = requests.post(
            "https://api.fish.audio/v1/tts",
            headers=headers,
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Fish Audio request failed (network error): {exc}") from exc

    if resp.status_code == 401:
        raise RuntimeError("Fish Audio rejected the request: invalid FISH_AUDIO_API_KEY.")
    if resp.status_code == 429:
        raise RuntimeError("Fish Audio quota/rate limit exceeded for this API key.")
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Fish Audio TTS failed with status {resp.status_code}: {resp.text[:500]}"
        )

    if not resp.content:
        raise RuntimeError("Fish Audio returned an empty audio response.")

    with open(out_path, "wb") as f:
        f.write(resp.content)


# ---------------- Edge-TTS (only runs if explicitly requested) ----------------

def generate_speech_edge(text: str, language_key: str, out_path: str):
    import asyncio
    import edge_tts

    lang = get_language(language_key)
    voice = lang.get("edge_voice")
    if not voice:
        raise RuntimeError(f"No Edge voice configured for language: {language_key}")

    clean_text = strip_emotion_tags(text)

    async def _run():
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(out_path)

    asyncio.run(_run())


# ---------------- Sarvam AI (only runs if explicitly requested) ----------------

def generate_speech_sarvam(text: str, language_key: str, out_path: str):
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY is not set. voice_engine='sarvam' cannot run without it.")

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


# ---------------- gTTS (only runs if explicitly requested) ----------------

def generate_speech_gtts(text: str, language_key: str, out_path: str):
    from gtts import gTTS

    lang = get_language(language_key)
    clean_text = strip_emotion_tags(text)
    tts = gTTS(text=clean_text, lang=lang["gtts_code"])
    tts.save(out_path)


# ---------------- Dispatcher — strict, no cross-engine fallback ----------------

def generate_speech(text: str, language_key: str, out_path: str, engine: str = "fish", character_profile: str = "default"):
    if not text or not text.strip():
        return

    if engine == "fish":
        generate_speech_fish(text, language_key, out_path, character_profile=character_profile)
    elif engine == "edge":
        generate_speech_edge(text, language_key, out_path)
    elif engine == "sarvam":
        generate_speech_sarvam(text, language_key, out_path)
    elif engine == "gtts":
        generate_speech_gtts(text, language_key, out_path)
    else:
        raise ValueError(f"Unknown voice_engine: {engine}")
      
