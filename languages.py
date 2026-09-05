# -> languages.py
"""
Central language config. Every engine (gtts / sarvam / fish / edge) reads
its own code from here so adding a language means editing one dict, not
four files.

fish_voice_id is intentionally left as None for most languages — Fish
Audio voice IDs are account-specific (picked from your own Fish Audio
playground / cloned voices), there's no universal default to ship here.
Fill in your own reference_id per language once you've picked voices.
"""

SUPPORTED_LANGUAGES = {
    "english":   {"label": "English",   "gtts_code": "en", "sarvam_code": "en-IN",
                  "edge_voice": "en-IN-NeerjaNeural",  "fish_voice_id": None},
    "hindi":     {"label": "Hindi",     "gtts_code": "hi", "sarvam_code": "hi-IN",
                  "edge_voice": "hi-IN-SwaraNeural",   "fish_voice_id": None},
    "telugu":    {"label": "Telugu",    "gtts_code": "te", "sarvam_code": "te-IN",
                  "edge_voice": "te-IN-ShrutiNeural",  "fish_voice_id": None},
    "tamil":     {"label": "Tamil",     "gtts_code": "ta", "sarvam_code": "ta-IN",
                  "edge_voice": "ta-IN-PallaviNeural", "fish_voice_id": None},
    "kannada":   {"label": "Kannada",   "gtts_code": "kn", "sarvam_code": "kn-IN",
                  "edge_voice": "kn-IN-SapnaNeural",   "fish_voice_id": None},
    "malayalam": {"label": "Malayalam", "gtts_code": "ml", "sarvam_code": "ml-IN",
                  "edge_voice": "ml-IN-SobhanaNeural", "fish_voice_id": None},
    "marathi":   {"label": "Marathi",   "gtts_code": "mr", "sarvam_code": "mr-IN",
                  "edge_voice": "mr-IN-AarohiNeural",  "fish_voice_id": None},
    "bengali":   {"label": "Bengali",   "gtts_code": "bn", "sarvam_code": "bn-IN",
                  "edge_voice": "bn-IN-TanishaaNeural","fish_voice_id": None},
    "gujarati":  {"label": "Gujarati",  "gtts_code": "gu", "sarvam_code": "gu-IN",
                  "edge_voice": "gu-IN-DhwaniNeural",  "fish_voice_id": None},
    "punjabi":   {"label": "Punjabi",   "gtts_code": "pa", "sarvam_code": "pa-IN",
                  "edge_voice": "hi-IN-SwaraNeural",   "fish_voice_id": None},
    # Punjabi has no dedicated Edge neural voice as of writing — falls back to
    # Hindi's voice if you select engine=edge with Punjabi. Verify current
    # availability with `edge-tts --list-voices` and update if one exists.
}

# Backwards-compatible alias — older code/imports may still reference LANGUAGES
LANGUAGES = SUPPORTED_LANGUAGES


def is_supported(language_key: str) -> bool:
    return (language_key or "").lower() in SUPPORTED_LANGUAGES


def get_language(language_key: str) -> dict:
    lang = SUPPORTED_LANGUAGES.get((language_key or "").lower())
    if not lang:
        raise ValueError(f"Unsupported language: {language_key}")
    return lang


def public_language_list() -> list:
    """Shape returned to the frontend — only what it needs to render a dropdown."""
    return [{"key": key, "label": val["label"]} for key, val in SUPPORTED_LANGUAGES.items()]
