# -> tts_service.py
"""
Strict routing: whichever engine is requested is the ONLY engine that runs.
No automatic fallback between engines.

Engines:
  - "fish"   -> Fish Audio hosted API (paid, FISH_AUDIO_API_KEY required)
  - "echofy" -> your own self-hosted IndicF5 service (free, CPU-runnable,
                ECHOFY_VOICE_SERVICE_URL required — see echofy-voice/)
  - "edge"   -> Microsoft Edge Neural voices (free, no key)
  - "sarvam" -> Sarvam AI bulbul:v3 (paid, SARVAM_API_KEY required)
  - "gtts"   -> Google Translate TTS (free, most robotic)
"""
import base64
import os
import re
import time

import requests

from languages import get_language

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
FISH_MODEL = "s2.1-pro-free"  # Fish Audio's free-tier flagship model — same quality as paid
FISH_MAX_RETRIES = 4

EMOTION_TAG_PATTERN = re.compile(r"\[(excited|confident|laugh|sad|angry|calm|whisper|serious)\]\s*", re.IGNORECASE)

# Fish Audio archetype -> reference_id (account-specific, fill in your own)
ARCHETYPE_VOICE_MAP = {
    "anime_villain":  None,
    "monster_deep":   None,
    "young_boy":      None,
    "cool_hero":      None,
    "mature_female":  None,
    "default":        None,
}

# Echofy self-hosted reference clips. IndicF5 has no [tag]-based emotion
# control like Fish Audio — emotion is inherited from how the REFERENCE
# CLIP was spoken. So instead of one clip per archetype, record one clip
# per (archetype, emotion) pair you care about, named:
#   voices/<archetype>_<emotion>.wav + voices/<archetype>_<emotion>.txt
# Lookup falls back in this order if an exact pair isn't recorded yet:
#   1) <archetype>_<emotion>
#   2) <archetype>_neutral
#   3) default_neutral   <- record this one at minimum, it's the ultimate fallback
VOICES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")


def _resolve_echofy_voice_key(character_profile: str, emotion: str) -> str:
    candidates = [
        f"{character_profile}_{emotion}",
        f"{character_profile}_neutral",
        "default_neutral",
    ]
    for key in candidates:
        wav_path = os.path.join(VOICES_DIR, f"{key}.wav")
        txt_path = os.path.join(VOICES_DIR, f"{key}.txt")
        if os.path.exists(wav_path) and os.path.exists(txt_path):
            return key
    raise RuntimeError(
        f"No reference voice found for archetype='{character_profile}' emotion='{emotion}', "
        f"and no 'default_neutral' fallback exists either. Add voices/default_neutral.wav + .txt at minimum."
    )


def strip_emotion_tags(text: str) -> str:
    return EMOTION_TAG_PATTERN.sub("", text).strip()


# ---------------- Fish Audio (strict — no fallback) ----------------

def generate_speech_fish(text: str, language_key: str, out_path: str, character_profile: str = "default"):
    api_key = os.getenv("FISH_AUDIO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FISH_AUDIO_API_KEY is not set. voice_engine='fish' was requested but "
            "cannot run without this key."
        )

    reference_id = ARCHETYPE_VOICE_MAP.get(character_profile, ARCHETYPE_VOICE_MAP["default"])

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"text": text, "format": "mp3", "model": FISH_MODEL}
    if reference_id:
        payload["reference_id"] = reference_id

    last_error = None
    for attempt in range(1, FISH_MAX_RETRIES + 1):
        try:
            resp = requests.post("https://api.fish.audio/v1/tts", headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            time.sleep(2 ** attempt)  # 2s, 4s, 8s, 16s
            continue

        if resp.status_code == 401:
            raise RuntimeError("Fish Audio rejected the request: invalid FISH_AUDIO_API_KEY.")

        if resp.status_code == 429:
            # Free-tier "fair use" throttling — a long video means hundreds of
            # sequential calls, so back off and retry rather than failing the job.
            last_error = "rate limited (429) under fair-use policy"
            time.sleep(2 ** attempt)
            continue

        if resp.status_code >= 400:
            raise RuntimeError(f"Fish Audio TTS failed with status {resp.status_code}: {resp.text[:500]}")

        if not resp.content:
            last_error = "empty audio response"
            time.sleep(2 ** attempt)
            continue

        with open(out_path, "wb") as f:
            f.write(resp.content)
        return

    raise RuntimeError(f"Fish Audio TTS failed after {FISH_MAX_RETRIES} attempts: {last_error}")


# ---------------- Echofy self-hosted (strict — no fallback) ----------------

def generate_speech_echofy(text: str, language_key: str, out_path: str, character_profile: str = "default", emotion: str = "neutral"):
    service_url = os.getenv("ECHOFY_VOICE_SERVICE_URL")
    if not service_url:
        raise RuntimeError(
            "ECHOFY_VOICE_SERVICE_URL is not set. voice_engine='echofy' was requested "
            "but no self-hosted voice service URL is configured."
        )

    voice_key = _resolve_echofy_voice_key(character_profile, emotion)
    ref_audio_path = os.path.join(VOICES_DIR, f"{voice_key}.wav")
    ref_text_path = os.path.join(VOICES_DIR, f"{voice_key}.txt")

    with open(ref_audio_path, "rb") as f:
        ref_audio_b64 = base64.b64encode(f.read()).decode("utf-8")
    with open(ref_text_path, "r", encoding="utf-8") as f:
        ref_text = f.read().strip()

    payload = {"text": text, "ref_audio_base64": ref_audio_b64, "ref_text": ref_text}

    try:
        resp = requests.post(f"{service_url.rstrip('/')}/v1/tts", json=payload, timeout=180)
    except requests.RequestException as exc:
        raise RuntimeError(f"Echofy voice service request failed (network error): {exc}") from exc

    if resp.status_code >= 400:
        raise RuntimeError(f"Echofy voice service failed with status {resp.status_code}: {resp.text[:500]}")
    if not resp.content:
        raise RuntimeError("Echofy voice service returned empty audio.")

    with open(out_path, "wb") as f:
        f.write(resp.content)


# ---------------- Edge-TTS ----------------

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


# ---------------- Sarvam AI ----------------

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


# ---------------- gTTS ----------------

def generate_speech_gtts(text: str, language_key: str, out_path: str):
    from gtts import gTTS

    lang = get_language(language_key)
    clean_text = strip_emotion_tags(text)
    tts = gTTS(text=clean_text, lang=lang["gtts_code"])
    tts.save(out_path)


# ---------------- Dispatcher — strict, no cross-engine fallback ----------------

def generate_speech(text: str, language_key: str, out_path: str, engine: str = "echofy", character_profile: str = "default", emotion: str = "neutral"):
    if not text or not text.strip():
        return

    if engine == "fish":
        generate_speech_fish(text, language_key, out_path, character_profile=character_profile)
    elif engine == "echofy":
        generate_speech_echofy(text, language_key, out_path, character_profile=character_profile, emotion=emotion)
    elif engine == "edge":
        generate_speech_edge(text, language_key, out_path)
    elif engine == "sarvam":
        generate_speech_sarvam(text, language_key, out_path)
    elif engine == "gtts":
        generate_speech_gtts(text, language_key, out_path)
    else:
        raise ValueError(f"Unknown voice_engine: {engine}")
        
