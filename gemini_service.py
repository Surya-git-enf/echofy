# -> gemini_service.py
import json
import os
import re

from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"

ARCHETYPES = ["anime_villain", "monster_deep", "young_boy", "cool_hero", "mature_female", "default"]
EMOTIONS = ["neutral", "excited", "sad", "angry", "calm", "whisper", "serious"]
GENDERS = ["male", "female", "neutral"]
AGE_GROUPS = ["child", "teen", "young", "adult", "elder"]
MAX_CHARACTERS = 8

SYSTEM_INSTRUCTION = (
    "You are a professional film dialogue adapter and voice director — NOT a "
    "literal translator. You are dubbing for movies/anime/shows. You return "
    "ONLY valid JSON matching the schema you are given. No markdown, no code "
    "fences, no explanation, no preamble — JSON only."
)

PROMPT_TEMPLATE = """You are dubbing this scene into {target_language}. The audio is {duration:.1f} seconds long.

STEP 1 — UNDERSTAND THE SCENE BEFORE WRITING ANYTHING.
Listen to the whole clip. Work out who is speaking, how they relate to each other,
the mood, the humour/tension, and what is dramatically happening. Identify every
distinct speaking character (there may be 1 to {max_characters}). Different voices in the
audio are different characters, even if you do not know their names. Keep each
character's id stable for the whole clip.

STEP 2 — WRITE THE DUBBED DIALOGUE LIKE A LOCALISATION TEAM, NOT A TRANSLATOR.
- Write what a real {target_language}-speaking person of THAT character's age, gender and
  personality would naturally say in THAT moment. Match the original's attitude,
  jokes, sarcasm and slang with equivalent {target_language} slang and street speech. Never
  use stiff, textbook, or dictionary phrasing.
- Use the way people really talk in {target_language}: natural sentence order, natural
  fillers and interjections, everyday loanwords (e.g. drink, car, boss, party, phone)
  exactly as native speakers say them, including normal code-mixing where native
  speakers do it. Write in the language's normal script.
- Give each character their own way of speaking (a hot-headed kid, a calm elder and a
  sarcastic friend must not sound alike).
- Spell out numbers, symbols and abbreviations as they are spoken so a TTS engine
  reads them correctly.
- Keep each line the same spoken length as the original phrase (similar syllable
  count, so it fits the same time slot). Shorten rather than ramble.
- Keep non-verbal reactions (laughs, gasps, grunts, battle cries) as short
  phonetic sound effects, combined with a bracket tag where the delivery needs it.

EXPRESSIVE DELIVERY: the TTS engine understands inline tags such as [laughing],
[whispers], [sigh], [excited], [angry], [crying]. Use them only where the source audio
genuinely calls for them; most lines need none.

TIMING RULES:
- Split into natural spoken phrases of roughly 1-8 seconds each.
- start/end are seconds (floats) matching where each phrase occurs in the audio, within 0 to {duration:.1f}.
- Phrases of the same character must not overlap each other.

CHARACTER FIELDS:
- gender: one of {genders}
- age_group: one of {age_groups}
- archetype (vocal profile): exactly one of {archetypes}; use "default" if nothing stands out
- voice_description: a few words on how the voice sounds (e.g. "gruff, slow, low")
EMOTION per line: exactly one of {emotions}.

Return JSON in exactly this shape:
{{
  "detected_source_language": "string",
  "scene_summary": "one or two sentences on what happens and the mood",
  "characters": [
    {{"id": "speaker_1", "name_guess": "string or empty", "gender": "male", "age_group": "adult",
      "archetype": "default", "voice_description": "string"}}
  ],
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker": "speaker_1",
      "emotion": "neutral",
      "original_text": "string",
      "translated_text": "string — natural, localised, in the character's own register"
    }}
  ]
}}
"""


def _extract_json(raw_text: str) -> dict:
    cleaned = re.sub(r"^```(json)?|```$", "", (raw_text or "").strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def _pick(value, allowed, default):
    value = (value or "").strip().lower() if isinstance(value, str) else ""
    return value if value in allowed else default


def _num(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalise_script(data: dict, total_duration: float) -> dict:
    """Clean whatever Gemini returned into a safe shape. Pure function (unit-testable)."""
    if not isinstance(data.get("segments"), list):
        raise RuntimeError("Gemini response did not include a valid 'segments' list.")

    characters = {}
    for raw in data.get("characters") or []:
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("id") or "").strip()
        if not cid or cid in characters:
            continue
        characters[cid] = {
            "id": cid,
            "name_guess": str(raw.get("name_guess") or "").strip(),
            "gender": _pick(raw.get("gender"), GENDERS, "neutral"),
            "age_group": _pick(raw.get("age_group"), AGE_GROUPS, "adult"),
            "archetype": _pick(raw.get("archetype"), ARCHETYPES, "default"),
            "voice_description": str(raw.get("voice_description") or "").strip(),
        }

    segments = []
    for raw in data["segments"]:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("translated_text") or "").strip()
        if not text:
            continue
        start = max(0.0, _num(raw.get("start"), 0.0))
        end = _num(raw.get("end"), start + 1.0)
        if total_duration:
            start = min(start, max(0.0, total_duration - 0.2))
            end = min(end, total_duration)
        if end <= start:
            end = min(start + 1.0, total_duration) if total_duration else start + 1.0
        speaker = str(raw.get("speaker") or "speaker_1").strip() or "speaker_1"
        if speaker not in characters:
            characters[speaker] = {"id": speaker, "name_guess": "", "gender": "neutral", "age_group": "adult",
                                   "archetype": "default", "voice_description": ""}
        segments.append({
            "start": start,
            "end": end,
            "speaker": speaker,
            "character_profile": characters[speaker]["archetype"],
            "emotion": _pick(raw.get("emotion"), EMOTIONS, "neutral"),
            "original_text": str(raw.get("original_text") or "").strip(),
            "translated_text": text,
        })

    segments.sort(key=lambda s: (s["start"], s["end"]))
    return {
        "detected_source_language": data.get("detected_source_language"),
        "scene_summary": str(data.get("scene_summary") or "").strip(),
        "characters": list(characters.values()),
        "segments": segments,
    }


def transcribe_and_translate(audio_path: str, target_language_label: str, total_duration: float = 0.0) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=api_key)
    uploaded_file = client.files.upload(file=audio_path)

    prompt = PROMPT_TEMPLATE.format(
        target_language=target_language_label,
        duration=total_duration or 0.0,
        max_characters=MAX_CHARACTERS,
        genders=", ".join(GENDERS),
        age_groups=", ".join(AGE_GROUPS),
        archetypes=", ".join(ARCHETYPES),
        emotions=", ".join(EMOTIONS),
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt, uploaded_file],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
        ),
    )

    if not response or not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    return normalise_script(_extract_json(response.text), total_duration)
