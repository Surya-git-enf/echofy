"""
Central place for supported languages.
gtts_code   -> used by the free gTTS engine
sarvam_code -> used by the paid Sarvam bulbul:v3 TTS engine (BCP-47 style)
"""

LANGUAGES = {
    "english":   {"label": "English",   "gtts_code": "en", "sarvam_code": "en-IN"},
    "hindi":     {"label": "Hindi",     "gtts_code": "hi", "sarvam_code": "hi-IN"},
    "telugu":    {"label": "Telugu",    "gtts_code": "te", "sarvam_code": "te-IN"},
    "tamil":     {"label": "Tamil",     "gtts_code": "ta", "sarvam_code": "ta-IN"},
    "kannada":   {"label": "Kannada",   "gtts_code": "kn", "sarvam_code": "kn-IN"},
    "malayalam": {"label": "Malayalam", "gtts_code": "ml", "sarvam_code": "ml-IN"},
    "marathi":   {"label": "Marathi",   "gtts_code": "mr", "sarvam_code": "mr-IN"},
    "bengali":   {"label": "Bengali",   "gtts_code": "bn", "sarvam_code": "bn-IN"},
    "gujarati":  {"label": "Gujarati",  "gtts_code": "gu", "sarvam_code": "gu-IN"},
    "punjabi":   {"label": "Punjabi",   "gtts_code": "pa", "sarvam_code": "pa-IN"},
}


def is_supported(language_key: str) -> bool:
    return language_key.lower() in LANGUAGES


def get_language(language_key: str) -> dict:
    lang = LANGUAGES.get(language_key.lower())
    if not lang:
        raise ValueError(f"Unsupported language: {language_key}")
    return lang


def public_language_list() -> list:
    """Shape returned to the frontend — only what it needs to render a dropdown."""
    return [{"key": key, "label": val["label"]} for key, val in LANGUAGES.items()]

