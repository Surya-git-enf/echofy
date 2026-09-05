SUPPORTED_LANGUAGES = {
    "telugu": {"name": "Telugu", "code": "te", "sarvam_code": "te-IN"},
    "hindi": {"name": "Hindi", "code": "hi", "sarvam_code": "hi-IN"},
    "tamil": {"name": "Tamil", "code": "ta", "sarvam_code": "ta-IN"},
    "kannada": {"name": "Kannada", "code": "kn", "sarvam_code": "kn-IN"},
    "malayalam": {"name": "Malayalam", "code": "ml", "sarvam_code": "ml-IN"},
    "marathi": {"name": "Marathi", "code": "mr", "sarvam_code": "mr-IN"},
    "bengali": {"name": "Bengali", "code": "bn", "sarvam_code": "bn-IN"},
    "english": {"name": "English", "code": "en", "sarvam_code": "en-IN"},
    "spanish": {"name": "Spanish", "code": "es", "sarvam_code": "es-ES"},
    "french": {"name": "French", "code": "fr", "sarvam_code": "fr-FR"},
}

def is_supported(lang_code: str) -> bool:
    return (lang_code or "").lower().strip() in SUPPORTED_LANGUAGES

def public_language_list():
    return SUPPORTED_LANGUAGES
    
