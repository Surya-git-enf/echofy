# -> gemini_service.py
import json
import os
import re

from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"
# system_instruction ("developer instruction") is only accepted on the v1beta API; the default
# v1 endpoint rejects it with 400 INVALID_ARGUMENT.
API_VERSION = "v1beta"

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

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version=API_VERSION))
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


# ---------------------------------------------------------------------------
# Dialogue writing from a Gnani transcript (the default path).
# Gnani supplies the words and the timing; Gemini only listens for who is speaking and how,
# and writes the dub. See stt_service.py.
# ---------------------------------------------------------------------------

WORDS_PER_SECOND_CEILING = 3.0  # a line that needs more than this many words per second will not fit its slot

DIALOGUE_SYSTEM_INSTRUCTION = (
    "You are the lead dialogue writer and voice director at a film dubbing studio. You adapt "
    "scenes, you do not translate them. You work from a timed transcript and the scene audio, "
    "and you return ONLY valid JSON in the schema you are given: no markdown, no code fences, "
    "no commentary."
)

DIALOGUE_PROMPT_TEMPLATE = """TASK
Write the {target_language} dub of the scene you can hear. A speech-to-text system has already
transcribed it and cut it into timed lines (below). The audio is attached so you can tell who
is speaking and how they say it.

INPUT: TIMED TRANSCRIPT ({line_count} lines, scene length {duration:.1f}s)
Each line has an id, the seconds it occupies, a word ceiling for the dub, and the transcript text.
{lines_block}

WORK IN THIS ORDER
1. Listen to the whole scene first. Decide who the characters are, how they relate, what is at stake
   and what the mood is. Different voices are different characters even if nobody says their name.
   Give each one a stable id (speaker_1, speaker_2, ...). There are at most {max_characters}.
2. For every line, decide which character says it and in which emotion, from the audio.
3. Only then write the {target_language} line.

HOW TO WRITE THE LINES
- Write what a native {target_language} speaker of that character's age, gender and temperament would
  say at that moment. Keep the intent, the attitude, the jokes and the subtext. Do not keep the
  English sentence structure.
- Everyday speech, not textbook speech. Use the fillers, interjections and loanwords people really use
  (phone, boss, sorry, okay, date) and normal code-mixing where native speakers do it. Use the
  language's normal script.
- Give each character their own register: a nervous first-date speaker, a confident flirt and a
  stern elder must not sound alike.
- Fit the slot. Each line has a word ceiling; stay under it, and shorter is fine. A dub that does
  not fit gets sped up and sounds rushed, so cut filler words before you cut meaning.
- Spell out numbers, symbols and abbreviations the way they are spoken, so a speech engine reads them
  correctly.
- Short non-verbal reactions (laugh, gasp, sigh, hmm) stay as brief sounds, with a tag when the
  delivery needs it.
- Emotion tags: the speech engine understands inline tags such as [laughing], [whispers], [sigh],
  [excited], [angry], [crying]. Use one only where the audio really calls for it. Most lines need none.

WHAT YOU MUST NOT DO
- Do not add, merge, split, reorder or drop lines. Return exactly one entry for every input id.
- Do not invent content that is not in the line. Do not explain, apologise or add notes inside a line.
- Do not translate word for word.
- If the transcript text is clearly wrong against the audio (a mishearing, or nonsense), put what
  was really said in "corrected_source". Leave it empty otherwise.

EXAMPLES OF THE STANDARD (these show the approach, not wording to reuse)
  Source: "Wait, you're kidding me."   Speaker: flustered young man.
  Stiff:   Hindi "रुको, आप मुझसे मज़ाक कर रहे हैं।"        Natural: "अरे रुको, मज़ाक कर रहे हो क्या?"
  Stiff:   Telugu "ఆగండి, మీరు నాతో హాస్యం చేస్తున్నారు."   Natural: "ఆగు ఆగు, జోక్ చేస్తున్నావా?"
  The natural version is shorter, uses the casual address a peer would use, and keeps the surprise.

CHARACTER FIELDS
- gender: one of {genders}
- age_group: one of {age_groups}
- archetype (vocal profile): exactly one of {archetypes}; use "default" if nothing stands out
- voice_description: a few words on how the voice sounds
EMOTION per line: exactly one of {emotions}.

OUTPUT: JSON in exactly this shape
{{
  "detected_source_language": "string",
  "scene_summary": "one or two sentences on what happens and the mood",
  "characters": [
    {{"id": "speaker_1", "name_guess": "string or empty", "gender": "male", "age_group": "young",
      "archetype": "default", "voice_description": "string"}}
  ],
  "lines": [
    {{"id": 0, "speaker": "speaker_1", "emotion": "neutral", "corrected_source": "", "text": "the {target_language} dub line"}}
  ]
}}
"""


def format_lines_block(source_lines: list) -> str:
    rows = []
    for line in source_lines:
        seconds = max(0.1, line["end"] - line["start"])
        ceiling = max(2, int(round(seconds * WORDS_PER_SECOND_CEILING)))
        rows.append(f'  id={line["id"]}  {seconds:.1f}s  max {ceiling} words  "{line["text"]}"')
    return "\n".join(rows)


def build_script_from_lines(source_lines: list, data: dict, total_duration: float) -> dict:
    """
    Join Gemini's adapted lines back onto the Gnani lines by id, so timing and source text always
    come from the transcript. Pure function (unit-testable).
    """
    adapted = {}
    for raw in data.get("lines") or []:
        if not isinstance(raw, dict):
            continue
        try:
            adapted[int(raw.get("id"))] = raw
        except (TypeError, ValueError):
            continue

    segments, missing = [], 0
    for src in source_lines:
        raw = adapted.get(src["id"])
        text = str((raw or {}).get("text") or "").strip()
        if not text:
            missing += 1
            continue
        segments.append({
            "start": src["start"],
            "end": src["end"],
            "speaker": raw.get("speaker"),
            "emotion": raw.get("emotion"),
            "original_text": str(raw.get("corrected_source") or "").strip() or src["text"],
            "translated_text": text,
        })

    if source_lines and missing > len(source_lines) / 2:
        raise RuntimeError(f"Gemini returned dialogue for only {len(source_lines) - missing} of {len(source_lines)} lines.")

    return normalise_script({
        "detected_source_language": data.get("detected_source_language"),
        "scene_summary": data.get("scene_summary"),
        "characters": data.get("characters"),
        "segments": segments,
    }, total_duration)


def adapt_dialogue(source_lines: list, audio_path: str, target_language_label: str, total_duration: float = 0.0) -> dict:
    """Write the dub from Gnani's timed transcript, using the audio to decide speakers and emotion."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version=API_VERSION))
    uploaded_file = client.files.upload(file=audio_path)

    prompt = DIALOGUE_PROMPT_TEMPLATE.format(
        target_language=target_language_label,
        duration=total_duration or 0.0,
        line_count=len(source_lines),
        lines_block=format_lines_block(source_lines),
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
            system_instruction=DIALOGUE_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )

    if not response or not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    return build_script_from_lines(source_lines, _extract_json(response.text), total_duration)
