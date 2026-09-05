"""
TTS Service supporting Fish Audio with automatic fallback to Microsoft Edge Neural Voices.
"""
import os
import re
import asyncio
import requests
import edge_tts

# Pre-selected expressive community voice reference IDs from Fish Audio
# You can replace these with any voice ID from fish.audio/discovery
FISH_VOICE_IDS = {
    "english": "933563129e564b19a115bedd57b7406a",   # Natural conversational English
    "hindi": "e1bcbe4e7c1a4e1a8fa003e8c07e0c45",     # Clear Hindi
    "telugu": "933563129e564b19a115bedd57b7406a",    # Multilingual S2 model base
    "default": "933563129e564b19a115bedd57b7406a"
}

# Free Microsoft Neural Voice Fallback map
EDGE_VOICE_MAP = {
    "telugu": "te-IN-MohanNeural",        # Natural Telugu male
    "hindi": "hi-IN-MadhurNeural",        # Natural Hindi male
    "tamil": "ta-IN-ValluvarNeural",      # Natural Tamil male
    "kannada": "kn-IN-GaganNeural",       # Natural Kannada male
    "malayalam": "ml-IN-MidhunNeural",    # Natural Malayalam male
    "english": "en-IN-PrabhatNeural",     # Indian-accented English male
    "default": "en-US-AndrewNeural"       # US English male
}


def _strip_emotion_tags(text: str) -> str:
    """Removes [tags] before passing to Edge-TTS since Edge reads them literally."""
    return re.sub(r"\[.*?\]", "", text).strip()


def _generate_fish_audio(text: str, target_language: str, output_path: str, api_key: str) -> bool:
    """Calls Fish Audio REST API directly."""
    url = "https://api.fish.audio/v1/tts"
    
    reference_id = FISH_VOICE_IDS.get(target_language.lower(), FISH_VOICE_IDS["default"])

    payload = {
        "text": text,
        "reference_id": reference_id,
        "format": "mp3",
        "latency": "balanced",
        "prosody": {
            "speed": 1.0,
            "volume": 0
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=25)
        if response.status_code == 200 and len(response.content) > 0:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
        else:
            print(f"[Fish Audio Error] Status {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"[Fish Audio Exception] {str(e)}")
        return False


def _generate_edge_tts(text: str, target_language: str, output_path: str):
    """Fallback generator using Microsoft Edge Neural Voices."""
    clean_text = _strip_emotion_tags(text)
    if not clean_text:
        clean_text = text

    voice = EDGE_VOICE_MAP.get(target_language.lower(), EDGE_VOICE_MAP["default"])

    async def _synthesize():
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(output_path)

    asyncio.run(_synthesize())


def generate_speech(text: str, target_language: str, output_path: str, engine: str = "fish"):
    """
    Main speech generation dispatcher.
    Prioritizes Fish Audio when engine is 'fish' and key is configured.
    Falls back gracefully to Edge-TTS.
    """
    fish_key = os.getenv("FISH_AUDIO_API_KEY")

    if engine.lower() == "fish" and fish_key:
        success = _generate_fish_audio(text, target_language, output_path, fish_key)
        if success:
            return

    # Fallback to Edge-TTS neural engine
    _generate_edge_tts(text, target_language, output_path)
  
