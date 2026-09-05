"""
Strict Fish Audio Dispatcher:
Selects pre-trained model IDs based on the character persona detected by Gemini.
"""
import os
import requests

# Pre-trained community voice models on Fish Audio (S2 Pro architecture)
CHARACTER_VOICE_MODELS = {
    "anime_villain": "802e3bc2b27e49c2995d23ef70e6ac89",  # Intense villain/raspy edge
    "monster_deep": "e1bcbe4e7c1a4e1a8fa003e8c07e0c45",   # Deep resonant creature/boss
    "young_boy": "933563129e564b19a115bedd57b7406a",      # Youthful energetic voice
    "cool_hero": "933563129e564b19a115bedd57b7406a",      # Confident male protagonist
    "mature_female": "d04ad4bcda9e47cc8a0b07ec347e3322",  # Clear female voice
    "default": "933563129e564b19a115bedd57b7406a",
}


def generate_speech(
    text: str,
    target_language: str,
    output_path: str,
    character_profile: str = "default",
    engine: str = "fish"
):
    """Generates audio strictly using the Fish Audio API."""
    api_key = os.getenv("FISH_AUDIO_API_KEY")
    if not api_key:
        raise RuntimeError("FISH_AUDIO_API_KEY is not set in environment variables.")

    ref_id = CHARACTER_VOICE_MODELS.get(character_profile, CHARACTER_VOICE_MODELS["default"])

    url = "https://api.fish.audio/v1/tts"
    payload = {
        "text": text,
        "reference_id": ref_id,
        "format": "mp3",
        "latency": "balanced",
        "prosody": {"speed": 1.05, "volume": 0},
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    
    if response.status_code != 200:
        raise RuntimeError(
            f"Fish Audio API failed with HTTP {response.status_code}: {response.text}"
        )

    if len(response.content) == 0:
        raise RuntimeError("Fish Audio returned an empty audio response.")

    with open(output_path, "wb") as f:
        f.write(response.content)
      
