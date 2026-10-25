# -> languages.py
"""
Central language config. Every engine (gtts / sarvam / fish / edge / echofy)
reads its codes from here.

Any language can be requested. A language that is not in the table below
is still accepted: Gemini writes the dialogue in it, and the engine is
checked up front by engine_can_speak() so an unsupported pairing fails
immediately with a clear message instead of deep inside the pipeline.

edge_locale lets tts_service/voice_casting look up every Edge neural voice
for the language at runtime, which is what makes multi-character casting
possible without hard-coding voice names.

fish_voice_id is intentionally None: Fish Audio voice IDs are
account-specific. Configure them with the FISH_VOICE_POOL environment
variable (see voice_casting.py).
"""
import re

# key, label, gtts_code, edge_locale, sarvam_code, edge_voice (last-resort), aliases
_TABLE = [
    ("english",    "English",    "en",    "en-US", "en-IN", "en-IN-NeerjaNeural",   ("en", "eng")),
    ("hindi",      "Hindi",      "hi",    "hi-IN", "hi-IN", "hi-IN-SwaraNeural",    ("hi", "hinglish")),
    ("telugu",     "Telugu",     "te",    "te-IN", "te-IN", "te-IN-ShrutiNeural",   ("te", "tenglish")),
    ("tamil",      "Tamil",      "ta",    "ta-IN", "ta-IN", "ta-IN-PallaviNeural",  ("ta", "tanglish")),
    ("kannada",    "Kannada",    "kn",    "kn-IN", "kn-IN", "kn-IN-SapnaNeural",    ("kn",)),
    ("malayalam",  "Malayalam",  "ml",    "ml-IN", "ml-IN", "ml-IN-SobhanaNeural",  ("ml",)),
    ("marathi",    "Marathi",    "mr",    "mr-IN", "mr-IN", "mr-IN-AarohiNeural",   ("mr",)),
    ("bengali",    "Bengali",    "bn",    "bn-IN", "bn-IN", "bn-IN-TanishaaNeural", ("bn", "bangla")),
    ("gujarati",   "Gujarati",   "gu",    "gu-IN", "gu-IN", "gu-IN-DhwaniNeural",   ("gu",)),
    # Punjabi has no dedicated Edge neural voice as far as we know; the
    # runtime lookup finds one if it exists, otherwise this Hindi voice is used.
    ("punjabi",    "Punjabi",    "pa",    "pa-IN", "pa-IN", "hi-IN-SwaraNeural",    ("pa",)),
    ("urdu",       "Urdu",       "ur",    "ur-IN", None,    None,                   ("ur",)),
    ("spanish",    "Spanish",    "es",    "es-ES", None,    None,                   ("es",)),
    ("french",     "French",     "fr",    "fr-FR", None,    None,                   ("fr",)),
    ("german",     "German",     "de",    "de-DE", None,    None,                   ("de",)),
    ("italian",    "Italian",    "it",    "it-IT", None,    None,                   ("it",)),
    ("portuguese", "Portuguese", "pt",    "pt-BR", None,    None,                   ("pt",)),
    ("russian",    "Russian",    "ru",    "ru-RU", None,    None,                   ("ru",)),
    ("japanese",   "Japanese",   "ja",    "ja-JP", None,    None,                   ("ja",)),
    ("korean",     "Korean",     "ko",    "ko-KR", None,    None,                   ("ko",)),
    ("chinese",    "Chinese",    "zh-CN", "zh-CN", None,    None,                   ("zh", "mandarin")),
    ("arabic",     "Arabic",     "ar",    "ar-SA", None,    None,                   ("ar",)),
    ("turkish",    "Turkish",    "tr",    "tr-TR", None,    None,                   ("tr",)),
    ("indonesian", "Indonesian", "id",    "id-ID", None,    None,                   ("id",)),
    ("vietnamese", "Vietnamese", "vi",    "vi-VN", None,    None,                   ("vi",)),
    ("thai",       "Thai",       "th",    "th-TH", None,    None,                   ("th",)),
    ("dutch",      "Dutch",      "nl",    "nl-NL", None,    None,                   ("nl",)),
    ("polish",     "Polish",     "pl",    "pl-PL", None,    None,                   ("pl",)),
    ("swedish",    "Swedish",    "sv",    "sv-SE", None,    None,                   ("sv",)),
    ("ukrainian",  "Ukrainian",  "uk",    "uk-UA", None,    None,                   ("uk",)),
    ("greek",      "Greek",      "el",    "el-GR", None,    None,                   ("el",)),
    ("hebrew",     "Hebrew",     "iw",    "he-IL", None,    None,                   ("he", "iw")),
    ("persian",    "Persian",    None,    "fa-IR", None,    None,                   ("fa", "farsi")),
    ("swahili",    "Swahili",    "sw",    "sw-KE", None,    None,                   ("sw",)),
    ("filipino",   "Filipino",   "tl",    "fil-PH", None,   None,                   ("fil", "tl", "tagalog")),
    ("nepali",     "Nepali",     "ne",    "ne-NP", None,    None,                   ("ne",)),
    ("sinhala",    "Sinhala",    "si",    "si-LK", None,    None,                   ("si",)),
    ("czech",      "Czech",      "cs",    "cs-CZ", None,    None,                   ("cs",)),
    ("romanian",   "Romanian",   "ro",    "ro-RO", None,    None,                   ("ro",)),
    ("hungarian",  "Hungarian",  "hu",    "hu-HU", None,    None,                   ("hu",)),
    ("malay",      "Malay",      None,    "ms-MY", None,    None,                   ("ms",)),
]

SUPPORTED_LANGUAGES = {}
_ALIASES = {}
for _key, _label, _gtts, _locale, _sarvam, _edge, _aliases in _TABLE:
    SUPPORTED_LANGUAGES[_key] = {
        "label": _label,
        "gtts_code": _gtts,
        "sarvam_code": _sarvam,
        "edge_voice": _edge,
        "edge_locale": _locale,
        "fish_voice_id": None,
    }
    _ALIASES[_key] = _key
    for _alias in _aliases:
        _ALIASES[_alias] = _key

# Backwards-compatible alias — older code/imports may still reference LANGUAGES
LANGUAGES = SUPPORTED_LANGUAGES

_NAME_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z \-]{1,40}")


def _normalise(language_key: str) -> str:
    return re.sub(r"\s+", " ", (language_key or "").strip().lower())


def resolve_language_key(language_key: str) -> str:
    """Canonical key for a name, ISO code or locale ('es', 'es-MX', 'Spanish'); unknown names pass through."""
    norm = _normalise(language_key)
    if norm in _ALIASES:
        return _ALIASES[norm]
    base = re.split(r"[-_]", norm)[0]
    return _ALIASES.get(base, norm)


def is_supported(language_key: str) -> bool:
    """Any plausible language name or code is accepted; engine_can_speak() checks the actual engine."""
    return bool(_NAME_PATTERN.fullmatch((language_key or "").strip()))


def get_language(language_key: str) -> dict:
    if not is_supported(language_key):
        raise ValueError(f"Unsupported language: {language_key}")
    key = resolve_language_key(language_key)
    known = SUPPORTED_LANGUAGES.get(key)
    if known:
        return dict(known, key=key)
    return {
        "key": key,
        "label": key.title(),
        "gtts_code": None,
        "sarvam_code": None,
        "edge_voice": None,
        "edge_locale": None,
        "fish_voice_id": None,
    }


def engine_can_speak(engine: str, language_key: str):
    """(ok, reason). Fish is multilingual, so it is allowed for any language (best effort)."""
    lang = get_language(language_key)
    if engine == "fish":
        return True, ""
    if engine == "edge" and not (lang.get("edge_locale") or lang.get("edge_voice")):
        return False, f"voice_engine='edge' has no known voices for '{lang['label']}'. Use voice_engine='fish'."
    if engine == "gtts" and not lang.get("gtts_code"):
        return False, f"voice_engine='gtts' does not support '{lang['label']}'. Use voice_engine='fish' or 'edge'."
    if engine in ("sarvam", "echofy") and not lang.get("sarvam_code"):
        return False, f"voice_engine='{engine}' only supports Indian languages, not '{lang['label']}'. Use voice_engine='fish' or 'edge'."
    return True, ""


def public_language_list() -> list:
    """Shape returned to the frontend — only what it needs to render a dropdown."""
    return [{"key": key, "label": val["label"]} for key, val in SUPPORTED_LANGUAGES.items()]
