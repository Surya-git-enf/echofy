# -> tts_service.py
"""
Strict routing: whichever engine is requested is the ONLY engine that runs.
No automatic fallback between engines.

Engines:
  - "gnani"  -> Gnani Vachana API, model timbre-v3.0 (GNANI_API_KEY required). Indian
                languages + English/Hinglish, 13 voices, emotions through inline tags
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


# ---------------- Gnani Vachana (strict — no fallback) ----------------

GNANI_URL = "https://api.vachana.ai/api/v1/tts/inference"
GNANI_MODEL = "timbre-v3.0"  # the only Vachana model with emotion tags and voices that speak every language
GNANI_MAX_RETRIES = 4
GNANI_MIN_SPEED, GNANI_MAX_SPEED = 0.85, 1.15
BRACKET_TAG_PATTERN = re.compile(r"\[([^\]]{1,40})\]")
GNANI_TAG_PATTERN = re.compile(r"<[a-z ]+>")
# The only inline tags timbre-v3.0 understands (docs.gnani.ai, tts-inference). Anything else is dropped.
GNANI_VALID_TAGS = ("coughs", "excited", "exhales", "giggle", "laugh", "pauses", "shouting", "sigh", "slow",
                    "sniffles", "whispers", "yawns", "clears throat")
ANGLE_TAG_PATTERN = re.compile(r"<\s*([A-Za-z][A-Za-z ]{0,20}?)\s*/?>")
LATIN_LETTER = re.compile(r"[A-Za-z]")


def clean_audio_tags(text: str) -> str:
    """Keep valid <tags> (normalised to lower case), drop unknown ones, tidy spaces. Pure function."""
    def fix(match):
        name = re.sub(r"\s+", " ", match.group(1).strip().lower())
        name = {"clear throat": "clears throat", "whisper": "whispers", "cough": "coughs", "yawn": "yawns",
                "exhale": "exhales", "pause": "pauses", "sniffle": "sniffles"}.get(name, name)
        return f"<{name}>" if name in GNANI_VALID_TAGS else ""
    return re.sub(r"\s+", " ", ANGLE_TAG_PATTERN.sub(fix, text)).strip()


def strip_audio_tags(text: str) -> str:
    """Remove every <tag> for engines that would read them aloud."""
    return re.sub(r"\s+", " ", ANGLE_TAG_PATTERN.sub("", text)).strip()

# Words Gemini may put in [brackets] -> the audio tags timbre-v3.0 actually understands.
# Vachana has no "angry" tag; <shouting> is the closest it offers.
GNANI_TAG_WORDS = {
    "laugh": "<laugh>", "laughs": "<laugh>", "laughing": "<laugh>", "laughter": "<laugh>",
    "giggle": "<giggle>", "giggles": "<giggle>", "giggling": "<giggle>",
    "whisper": "<whispers>", "whispers": "<whispers>", "whispering": "<whispers>",
    "excited": "<excited>", "excitedly": "<excited>",
    "shouting": "<shouting>", "shout": "<shouting>", "shouts": "<shouting>", "yelling": "<shouting>",
    "screaming": "<shouting>", "angry": "<shouting>",
    "sigh": "<sigh>", "sighs": "<sigh>", "sighing": "<sigh>", "sad": "<sigh>",
    "crying": "<sniffles>", "sobbing": "<sniffles>", "sniffles": "<sniffles>",
    "cough": "<coughs>", "coughs": "<coughs>", "yawn": "<yawns>", "yawns": "<yawns>",
    "exhale": "<exhales>", "exhales": "<exhales>", "pause": "<pauses>", "pauses": "<pauses>",
    "slow": "<slow>", "slowly": "<slow>", "clears throat": "<clears throat>",
}
# Tag added to the start of a line that has none, based on the line's detected emotion.
GNANI_EMOTION_TAG = {"excited": "<excited>", "angry": "<shouting>", "whisper": "<whispers>", "sad": "<sigh>"}
GNANI_EMOTION_SPEED = {"angry": 1.10, "excited": 1.08, "sad": 0.90, "calm": 0.95, "serious": 0.95, "whisper": 0.95}


def gnani_prepare(text: str, emotion: str = "neutral"):
    """(text with Vachana audio tags, speed). Pure function."""
    def to_tag(match):
        return GNANI_TAG_WORDS.get(match.group(1).strip().lower(), "")

    converted = BRACKET_TAG_PATTERN.sub(to_tag, text)
    converted = clean_audio_tags(converted)
    emotion = (emotion or "neutral").lower()
    lead = GNANI_EMOTION_TAG.get(emotion)
    # Quiet anger stays a spoken line (faster only); anger with "!" gets the shouting tag.
    if emotion == "angry" and "!" not in converted:
        lead = None
    if lead and not GNANI_TAG_PATTERN.search(converted):
        converted = f"{lead} {converted}"
    speed = max(0.85, min(1.15, GNANI_EMOTION_SPEED.get(emotion, 1.0)))
    return converted, speed


def generate_speech_gnani(text: str, language_key: str, out_path: str, emotion: str = "neutral", voice: dict = None,
                          speed_override: float = None):
    api_key = os.getenv("GNANI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GNANI_API_KEY is not set. voice_engine='gnani' was requested but cannot run without this key."
        )
    lang = get_language(language_key)
    if not lang.get("gnani_code"):
        raise RuntimeError(f"Gnani does not support '{lang['label']}'.")
    voice_name = (voice or {}).get("gnani_voice") or "Shubham"

    prepared_text, speed = gnani_prepare(text, emotion)
    if speed_override is not None:  # used to fit a line into its slot; Vachana accepts 0.85 to 1.15
        speed = round(max(GNANI_MIN_SPEED, min(GNANI_MAX_SPEED, speed_override)), 3)
    if not GNANI_TAG_PATTERN.sub("", prepared_text).strip():
        raise RuntimeError("Gnani needs some spoken words in the line, not only audio tags.")

    # A line that mixes scripts (a Telugu sentence with an English name or phrase) is sent with
    # language "auto", which Gnani recommends for mixed content; it routes each part by script.
    language = lang["gnani_code"]
    if language not in ("en-IN", "hi-en") and LATIN_LETTER.search(GNANI_TAG_PATTERN.sub("", prepared_text)):
        language = "auto"

    headers = {"X-API-Key-ID": api_key, "Content-Type": "application/json"}
    payload = {
        "text": prepared_text,
        "model": GNANI_MODEL,
        "voice": voice_name,
        "language": language,
        "speed": speed,
        "audio_config": {"sample_rate": 44100, "num_channels": 1, "container": "mp3", "bitrate": "192k"},
    }

    last_error = None
    for attempt in range(1, GNANI_MAX_RETRIES + 1):
        try:
            resp = requests.post(GNANI_URL, headers=headers, json=payload, timeout=90)
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            time.sleep(2 ** attempt)
            continue

        if resp.status_code in (401, 403):
            raise RuntimeError(f"Gnani rejected the request ({resp.status_code}): check GNANI_API_KEY, account status and credits. {resp.text[:300]}")
        if resp.status_code == 429 or resp.status_code >= 500:
            # Vachana allows one active request at a time; wait and retry.
            last_error = f"status {resp.status_code}: {resp.text[:200]}"
            time.sleep(2 ** attempt)
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"Gnani TTS failed with status {resp.status_code}: {resp.text[:500]}")
        if "json" in resp.headers.get("Content-Type", "").lower() or len(resp.content) < 200:
            last_error = f"unexpected response instead of audio: {resp.text[:200]}"
            time.sleep(2 ** attempt)
            continue

        with open(out_path, "wb") as f:
            f.write(resp.content)
        return

    raise RuntimeError(f"Gnani TTS failed after {GNANI_MAX_RETRIES} attempts: {last_error}")


# ---------------- Fish Audio (strict — no fallback) ----------------

def generate_speech_fish(text: str, language_key: str, out_path: str, character_profile: str = "default", voice: dict = None):
    api_key = os.getenv("FISH_AUDIO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FISH_AUDIO_API_KEY is not set. voice_engine='fish' was requested but "
            "cannot run without this key."
        )

    # Per-character voice from voice_casting wins; otherwise the archetype map
    # (FISH_VOICE_<ARCHETYPE> env vars can fill it in without code changes).
    reference_id = (voice or {}).get("fish_reference_id")
    if not reference_id:
        reference_id = ARCHETYPE_VOICE_MAP.get(character_profile) or os.getenv(f"FISH_VOICE_{character_profile.upper()}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": FISH_MODEL,  # Fish Audio requires the model as a HEADER, not a body field
    }
    payload = {"text": text, "format": "mp3"}
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

def generate_speech_edge(text: str, language_key: str, out_path: str, voice: dict = None):
    import asyncio
    import edge_tts

    lang = get_language(language_key)
    spec = voice or {}
    voice_name = spec.get("edge_voice") or lang.get("edge_voice")
    if not voice_name:
        raise RuntimeError(f"No Edge voice configured for language: {language_key}")

    pitch = f"{int(spec.get('edge_pitch_hz', 0)):+d}Hz"
    rate = f"{int(spec.get('edge_rate_pct', 0)):+d}%"
    clean_text = strip_emotion_tags(text)

    async def _run():
        communicate = edge_tts.Communicate(clean_text, voice_name, rate=rate, pitch=pitch)
        await communicate.save(out_path)

    asyncio.run(_run())


# ---------------- Sarvam AI ----------------

def generate_speech_sarvam(text: str, language_key: str, out_path: str):
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY is not set. voice_engine='sarvam' cannot run without it.")

    lang = get_language(language_key)
    if not lang.get("sarvam_code"):
        raise RuntimeError(f"Sarvam does not support '{lang['label']}'.")
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
    if not lang.get("gtts_code"):
        raise RuntimeError(f"gTTS does not support '{lang['label']}'.")
    clean_text = strip_emotion_tags(text)
    tts = gTTS(text=clean_text, lang=lang["gtts_code"])
    tts.save(out_path)


# ---------------- Dispatcher — strict, no cross-engine fallback ----------------

def generate_speech(text: str, language_key: str, out_path: str, engine: str = "echofy", character_profile: str = "default", emotion: str = "neutral", voice: dict = None, speed: float = None):
    if not text or not text.strip():
        return

    if engine != "gnani":
        text = strip_audio_tags(text)  # <tags> are Gnani-only; other engines would read them aloud
        if not text:
            return
    if engine == "gnani":
        generate_speech_gnani(text, language_key, out_path, emotion=emotion, voice=voice, speed_override=speed)
    elif engine == "fish":
        generate_speech_fish(text, language_key, out_path, character_profile=character_profile, voice=voice)
    elif engine == "echofy":
        generate_speech_echofy(text, language_key, out_path, character_profile=character_profile, emotion=emotion)
    elif engine == "edge":
        generate_speech_edge(text, language_key, out_path, voice=voice)
    elif engine == "sarvam":
        generate_speech_sarvam(text, language_key, out_path)
    elif engine == "gtts":
        generate_speech_gtts(text, language_key, out_path)
    else:
        raise ValueError(f"Unknown voice_engine: {engine}")
