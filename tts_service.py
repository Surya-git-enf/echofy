"""
Echofy TTS Service:
Supports Fish Audio (zero-shot cloning & public voices with inline emotions)
and falls back cleanly to Microsoft Edge Neural Voices (edge-tts) or gTTS.
"""
import os
import re
import asyncio
import requests
import edge_tts
from gtts import gTTS
from languages import SUPPORTED_LANGUAGES

# Public voice reference IDs on Fish Audio (changeable to any model on fish.audio/discovery)
FISH_VOICE_IDS = {
    "english": "933563129e564b19a115bedd57b7406a",
    "hindi": "e1bcbe4e7c1a4e1a8fa003e8c07e0c45",
    "telugu": "933563129e564b19a115bedd57b7406a",
    "default": "933563129e564b19a115bedd57b7406a",
}

# High-quality Microsoft Edge Neural Voices (no API key needed)
EDGE_VOICES = {
    "telugu": "te-IN-MohanNeural",
    "hindi": "hi-IN-MadhurNeural",
    "tamil": "ta-IN-ValluvarNeural",
    "kannada": "kn-IN-GaganNeural",
    "malayalam": "ml-IN-MidhunNeural",
    "marathi": "mr-IN-AarohiNeural",
    "bengali": "bn-IN-BashkarNeural",
    "english": "en-IN-PrabhatNeural",
    "spanish": "es-ES-AlvaroNeural",
    "french": "fr-FR-HenriNeural",
    "default": "en-US-AndrewNeural",
}


def _strip_emotion_tags(text: str) -> str:
    """Removes [tags] so edge-tts does not read emotion direction aloud."""
    cleaned = re.sub(r"\[.*?\]", "", text).strip()
    return cleaned if cleaned else text


def _generate_fish_audio(text: str, target_language: str, output_path: str, api_key: str) -> bool:
    """Invokes Fish Audio v1 TTS with balanced latency and emotion tag parsing."""
    url = "https://api.fish.audio/v1/tts"
    ref_id = FISH_VOICE_IDS.get(target_language.lower(), FISH_VOICE_IDS["default"])

    payload = {
        "text": text,
        "reference_id": ref_id,
        "format": "mp3",
        "latency": "balanced",
        "prosody": {"speed": 1.0, "volume": 0},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": "s2.1-pro",
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=25)
        if res.status_code == 200 and len(res.content) > 0:
            with open(output_path, "wb") as f:
                f.write(res.content)
            return True
        print(f"[Fish Audio Error] HTTP {res.status_code}: {res.text}")
        return False
    except Exception as e:
        print(f"[Fish Audio Exception] {e}")
        return False


def _generate_edge_tts(text: str, target_language: str, output_path: str) -> bool:
    """Free, human-sounding Microsoft Edge neural voice generation."""
    clean_text = _strip_emotion_tags(text)
    voice = EDGE_VOICES.get(target_language.lower(), EDGE_VOICES["default"])

    async def _run():
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(output_path)

    try:
        asyncio.run(_run())
        return True
    except Exception as e:
        print(f"[Edge TTS Error] {e}")
        return False


def _generate_gtts(text: str, target_language: str, output_path: str):
    clean_text = _strip_emotion_tags(text)
    lang_info = SUPPORTED_LANGUAGES.get(target_language.lower(), {"code": "en"})[span_3](start_span)[span_3](end_span)
    tts = gTTS(text=clean_text, lang=lang_info["code"], slow=False)[span_4](start_span)[span_4](end_span)
    tts.save(output_path)[span_5](start_span)[span_5](end_span)


def generate_speech(text: str, target_language: str, output_path: str, engine: str = "fish"):
    """
    Speech generation routing:
    1. engine='fish': attempts Fish Audio, falls back to Edge-TTS, then gTTS.
    2. engine='edge': calls Edge-TTS directly.
    3. engine='gtts': calls gTTS directly.
    """
    selected_engine = (engine or "fish").lower().strip()
    fish_api_key = os.getenv("FISH_AUDIO_API_KEY")

    if selected_engine == "fish" and fish_api_key:
        if _generate_fish_audio(text, target_language, output_path, fish_api_key):
            return

    if selected_engine in ("fish", "edge"):
        if _generate_edge_tts(text, target_language, output_path):
            return

    # Final fallback
    _generate_gtts(text, target_language, output_path)
    
