# -> gemini_service.py
import json
import os
import re
import time

from google import genai
from google.genai import types

from tts_service import GNANI_VALID_TAGS, clean_audio_tags

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
# Gnani supplies the words and the timing. Gemini watches the video, listens to the clean voice
# track, decides who speaks and how (face and voice), and writes the dub.
# ---------------------------------------------------------------------------

WORDS_PER_SECOND_CEILING = 3.0  # a line that needs more than this many words per second will not fit its slot
MIN_PART_SECONDS = 0.4
FILE_WAIT_SECONDS = 240

DIALOGUE_SYSTEM_INSTRUCTION = (
    "You are the lead dialogue writer and voice director at a film dubbing studio. You adapt "
    "scenes, you do not translate them. You watch the video, listen to the voices, read the "
    "timed transcript, and return ONLY valid JSON in the schema you are given: no markdown, no "
    "code fences, no commentary."
)

# Shown to the model as the standard to meet. Plain string, not a format template.
WORKED_EXAMPLE = """Scene: Mira (a woman) meets her boyfriend, whom she calls Tiger, at a cafe. He is late. The mood moves from playful
annoyance to a laugh. Names of people stay as they are written. "Tiger" is a pet name for the man, not the animal.

INPUT LINES
  id=0  3.0s  max 9 words   "Tiger, you promised you would not be late today."
  id=1  2.0s  max 6 words   "Sorry. The traffic was terrible."
  id=2  2.0s  max 6 words   "Sorry? You forgot my birthday, didn't you?"
  id=3  1.0s  max 3 words   "What? No!"
  id=4  2.0s  max 6 words   "Okay, I forgot. I'm really sorry."
  id=5  4.0s  max 12 words  "Okay, okay, I'm sorry! It's fine. Come here."   (span 40.0 to 44.0)

CORRECT OUTPUT FOR TELUGU
{
  "detected_source_language": "English",
  "scene_summary": "Mira scolds Tiger for being late, then teases him about her forgotten birthday. He apologises and she laughs it off.",
  "keep_terms": ["Mira", "Tiger"],
  "characters": [
    {"id": "speaker_1", "name_guess": "Mira", "gender": "female", "age_group": "young", "archetype": "default", "voice_description": "bright, teasing, warm"},
    {"id": "speaker_2", "name_guess": "Tiger", "gender": "male", "age_group": "young", "archetype": "default", "voice_description": "easy, a little sheepish"}
  ],
  "lines": [
    {"id": 0, "speaker": "speaker_1", "emotion": "serious", "text": "<sigh> Tiger, ఈ రోజు late చేయనని promise చేశావ్ కదా."},
    {"id": 1, "speaker": "speaker_2", "emotion": "calm", "text": "Sorry, traffic చాలా దారుణంగా ఉంది."},
    {"id": 2, "speaker": "speaker_1", "emotion": "angry", "text": "<slow> Sorry ఆ? నా birthday మర్చిపోయావ్ కదా?"},
    {"id": 3, "speaker": "speaker_2", "emotion": "excited", "text": "What? No!"},
    {"id": 4, "speaker": "speaker_2", "emotion": "sad", "text": "<sigh> Okay, మర్చిపోయా. నిజంగా sorry."},
    {"id": 5, "start": 40.0, "end": 41.8, "speaker": "speaker_2", "emotion": "excited", "text": "<exhales> Okay, okay, sorry!"},
    {"id": 5, "start": 42.0, "end": 44.0, "speaker": "speaker_1", "emotion": "excited", "text": "<laugh> పర్లేదు, ఇలా రా."}
  ]
}

WHY THAT IS RIGHT
- "Mira" and "Tiger" are untouched. Writing the Telugu or Hindi word for a tiger would be wrong.
- "Sorry", "What? No!" and "Okay" stay in English, exactly as an Indian audience says them. The rest of the line is Telugu.
- "late", "promise", "traffic" and "birthday" stay English because that is how people really talk in a mixed sentence.
- Every line has real spoken words. Tags sit directly before the words they colour. No line is only a tag.
- The last source line holds two speakers, so it is split into two parts with start and end inside its span (40.0 to 44.0), in order, not overlapping.
- Grammar follows the speaker and the person addressed. In Hindi, Mira says to Tiger "तुम मेरा birthday भूल गए, है ना?" (a man is addressed), and of herself "मैं माफ़ नहीं करूँगी". Tiger says "मैं माफ़ नहीं करूँगा".
"""

DIALOGUE_PROMPT_TEMPLATE = """TASK
Write the {target_language} dub of this scene. You get the video (with the clean voice track) and a timed
transcript made by a speech-to-text system. Use what you see and hear to decide who speaks and how they feel.
The video is {duration:.1f} seconds long. All times are seconds from the start of the video.

TIMED TRANSCRIPT ({line_count} lines). Each line has an id, its span, the length of that span and a word ceiling.
{lines_block}

WORK IN THIS ORDER
1. Watch and listen to the whole scene first. Work out who the characters are, how they relate, what is at stake and
   what the mood is. Different voices are different characters even if nobody says their name. Give each a stable id
   (speaker_1, speaker_2, ...). At most {max_characters}.
2. Check the transcript against the audio. The speech-to-text can mishear. If a line is wrong, write what was really
   said in "source_text" for that line. Leave it out otherwise.
3. For each line decide the speaker and the emotion from the face, the body and the voice together.
4. Only then write the {target_language} lines.

THE RULES (in order of importance)
1. NAMES NEVER CHANGE. Names, nicknames and pet names stay exactly as written in the source, in Latin script. Do not
   translate them, do not replace them with the dictionary meaning of the word, do not write them in native script.
   "Tiger" used as a name is a person, not an animal. List every such name in "keep_terms".
2. KEEP COMMON ENGLISH PHRASES IN ENGLISH. Short phrases an Indian audience says in English stay in English, in Latin
   script, exactly as spoken: yes, no, yeah, ok, okay, hi, hello, sorry, thanks, please, wow, what, I love you,
   it's okay, and everyday loanwords such as dad, mom, phone, cancer, boss, party. Write the rest of the line in
   {target_language} in its normal script. If the whole line is such a phrase, keep the whole line. (If the target
   language is English, just adapt tone and wording.)
3. TAGS. You may use only these tags, in angle brackets, lower case: {tag_list}. Put a tag directly before the words
   it colours. Use them where the face and voice really show it: <whispers> for a hushed voice, <shouting> for a raised
   one, <sniffles> when crying, <pauses> at a real hesitation, <slow> for tender or halting speech, <sigh>, <giggle>,
   <laugh>, <exhales> and so on. Most lines need one tag or none. Any other tag is ignored.
4. EVERY LINE NEEDS SPOKEN WORDS. A line that is only tags, only a sound or only punctuation is not allowed and is
   thrown away. Attach a reaction to a word ("<sigh> ..."), fold it into the neighbouring line, or use a short word
   such as "Hmm" or "Ha ha".
5. STAY IN THE SPAN. A dub line must fit the span of its source line. Stay under the word ceiling; fewer is fine.
   Cut filler before you cut meaning. A source line may be split into 2 to 4 parts when it contains a change of
   speaker or a long pause. Give each part "start" and "end" inside the source span, in order, not overlapping,
   each at least {min_part:.1f}s. Never move a line outside its span. Do not split unless you must.
6. ONE ENTRY PER ID. Every input id appears at least once. Do not drop, reorder or invent lines.

HOW TO WRITE
- Write what a native {target_language} speaker of that character's age, gender and temperament would say at that
  moment. Keep the intent, attitude, jokes and subtext. Do not copy the English sentence structure.
- Everyday speech, never textbook speech. Use real fillers, interjections and casual address. Grammatical gender
  and politeness follow the speaker and the person addressed.
- Each character has their own register. A nervous speaker, a flirt and a stern elder must not sound alike.
- Spell out numbers, symbols and abbreviations the way they are spoken.

THE STANDARD TO MEET
{worked_example}
CHARACTER FIELDS
- gender: one of {genders}
- age_group: one of {age_groups}
- archetype (vocal profile): exactly one of {archetypes}; use "default" if nothing stands out
- voice_description: a few words on how the voice sounds
EMOTION per line: exactly one of {emotions}.

OUTPUT: JSON in exactly this shape. "start" and "end" are only for split parts. "source_text" only for corrections.
{{
  "detected_source_language": "string",
  "scene_summary": "one or two sentences on what happens and the mood",
  "keep_terms": ["names kept verbatim"],
  "characters": [
    {{"id": "speaker_1", "name_guess": "string or empty", "gender": "male", "age_group": "young",
      "archetype": "default", "voice_description": "string"}}
  ],
  "lines": [
    {{"id": 0, "speaker": "speaker_1", "emotion": "neutral", "text": "the {target_language} dub line"}}
  ]
}}
"""

REPAIR_PROMPT_TEMPLATE = """These {target_language} dub lines lost a name. Names must appear exactly as written in the
source, in Latin script, never translated. Rewrite ONLY the lines below so that each name appears, and change nothing
else: keep the meaning, tone, tags and length. Return ONLY JSON: {{"lines": [{{"id": 0, "text": "..."}}]}}

Names to keep: {names}
{rows}
"""

_WORD = re.compile(r"\w", re.UNICODE)
_ANY_TAG = re.compile(r"<[^>]*>|\[[^\]]*\]")


def has_spoken_words(text: str) -> bool:
    """True if anything is left to say once tags and brackets are removed."""
    return bool(_WORD.search(_ANY_TAG.sub("", text or "")))


def format_lines_block(source_lines: list) -> str:
    rows = []
    for line in source_lines:
        seconds = max(0.1, line["end"] - line["start"])
        ceiling = max(2, int(round(seconds * WORDS_PER_SECOND_CEILING)))
        rows.append(f'  id={line["id"]}  {seconds:.1f}s  max {ceiling} words  '
                    f'(span {line["start"]:.1f} to {line["end"]:.1f})  "{line["text"]}"')
    return "\n".join(rows)


def _group_adapted(data: dict) -> dict:
    grouped = {}
    for raw in data.get("lines") or []:
        if not isinstance(raw, dict):
            continue
        try:
            grouped.setdefault(int(raw.get("id")), []).append(raw)
        except (TypeError, ValueError):
            continue
    return grouped


def _protected_names(data: dict) -> list:
    names = []
    for term in data.get("keep_terms") or []:
        if isinstance(term, str) and 1 < len(term.strip()) <= 30:
            names.append(term.strip())
    for ch in data.get("characters") or []:
        if isinstance(ch, dict) and isinstance(ch.get("name_guess"), str) and len(ch["name_guess"].strip()) > 1:
            names.append(ch["name_guess"].strip())
    seen, out = set(), []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def find_name_violations(source_lines: list, data: dict) -> list:
    """Lines whose source text contains a protected name that the dub line does not. Pure function."""
    names = _protected_names(data)
    grouped = _group_adapted(data)
    bad = []
    for src in source_lines:
        entries = grouped.get(src["id"], [])
        if len(entries) != 1:  # split lines are checked as a whole below
            joined = " ".join(str(e.get("text") or "") for e in entries)
        else:
            joined = str(entries[0].get("text") or "")
        if not entries:
            continue
        missing = [n for n in names
                   if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", src["text"], re.IGNORECASE) and n.lower() not in joined.lower()]
        if missing:
            bad.append({"id": src["id"], "names": missing, "source": src["text"], "current": joined, "single": len(entries) == 1})
    return bad


def _clamp_parts(entries: list, src: dict) -> list:
    """Times for each part of one source line, always inside the source span and in order."""
    span = src["end"] - src["start"]
    n = len(entries)
    if n > 1 and span < n * MIN_PART_SECONDS:  # too short to honour any times: share the span evenly
        entries = [{} for _ in entries]
    out, cursor = [], src["start"]
    for k, e in enumerate(entries):
        s, t = _num(e.get("start"), None), _num(e.get("end"), None)
        if n == 1 and (s is None or t is None):
            s, t = src["start"], src["end"]
        elif s is None or t is None:  # split part with no times: share the span evenly
            s, t = src["start"] + span * k / n, src["start"] + span * (k + 1) / n
        # Leave room for the parts still to come, so parts never overlap and none ends up empty.
        room_end = src["end"] - MIN_PART_SECONDS * (n - k - 1)
        s = max(cursor, min(s, room_end - MIN_PART_SECONDS))
        t = min(room_end, max(t, s + MIN_PART_SECONDS))
        if t <= s:
            t = min(src["end"], s + MIN_PART_SECONDS)
        out.append((round(s, 3), round(t, 3)))
        cursor = t
    return out


def build_script_from_lines(source_lines: list, data: dict, total_duration: float) -> dict:
    """
    Join Gemini's adapted lines back onto the Gnani lines by id. Timing and source text come from the
    transcript; split parts may only move inside their source span. Tags are cleaned to the ones Gnani
    understands, and lines with nothing to say are dropped with a warning. Pure function.
    """
    grouped = _group_adapted(data)
    warnings, segments, missing = [], [], 0

    for src in source_lines:
        entries = grouped.get(src["id"], [])
        kept, times = [], _clamp_parts(entries, src) if entries else []
        for e, (s, t) in zip(entries, times):
            text = clean_audio_tags(str(e.get("text") or ""))
            if not has_spoken_words(text):
                warnings.append(f"line {src['id']}: dropped a part that had no spoken words (tags only or empty)")
                continue
            kept.append({
                "start": s, "end": t,
                "speaker": e.get("speaker"), "emotion": e.get("emotion"),
                "original_text": str(e.get("source_text") or "").strip() or (src["text"] if len(entries) == 1 else ""),
                "translated_text": text,
            })
        if not kept:
            missing += 1
            continue
        segments.extend(kept)

    if source_lines and missing > len(source_lines) / 2:
        raise RuntimeError(f"Gemini returned dialogue for only {len(source_lines) - missing} of {len(source_lines)} lines.")
    if missing:
        warnings.append(f"{missing} of {len(source_lines)} source lines got no dub line")

    script = normalise_script({
        "detected_source_language": data.get("detected_source_language"),
        "scene_summary": data.get("scene_summary"),
        "characters": data.get("characters"),
        "segments": segments,
    }, total_duration)
    script["keep_terms"] = _protected_names(data)
    script["warnings"] = warnings
    return script


def _wait_until_active(client, uploaded):
    """Videos are processed after upload; wait until Gemini can read them."""
    name = getattr(uploaded, "name", None)
    if not isinstance(name, str):
        return uploaded
    waited = 0
    while getattr(getattr(uploaded, "state", None), "name", "") == "PROCESSING":
        if waited >= FILE_WAIT_SECONDS:
            raise RuntimeError("Gemini took too long to process the uploaded video.")
        time.sleep(2)
        waited += 2
        uploaded = client.files.get(name=name)
    if getattr(getattr(uploaded, "state", None), "name", "") == "FAILED":
        raise RuntimeError("Gemini could not process the uploaded video.")
    return uploaded


def _generate(client, model, contents, system_instruction):
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )
    if not response or not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    return _extract_json(response.text)


def _repair_names(client, model, label: str, violations: list, names: list, data: dict):
    """One focused retry for lines that lost a name. Edits data in place."""
    fixable = [v for v in violations if v["single"]]
    if not fixable:
        return
    rows = "\n".join(f'  id={v["id"]}  source: "{v["source"]}"  current dub: "{v["current"]}"  must contain: {", ".join(v["names"])}'
                     for v in fixable)
    prompt = REPAIR_PROMPT_TEMPLATE.format(target_language=label, names=", ".join(names), rows=rows)
    fixed = _generate(client, model, [prompt], DIALOGUE_SYSTEM_INSTRUCTION)
    by_id = {}
    for raw in fixed.get("lines") or []:
        try:
            by_id[int(raw.get("id"))] = str(raw.get("text") or "")
        except (TypeError, ValueError, AttributeError):
            continue
    for entry in data.get("lines") or []:
        try:
            eid = int(entry.get("id"))
        except (TypeError, ValueError, AttributeError):
            continue
        if eid in by_id and by_id[eid].strip() and any(v["id"] == eid for v in fixable):
            entry["text"] = by_id[eid]


def adapt_dialogue(source_lines: list, media_path: str, target_language_label: str, total_duration: float = 0.0) -> dict:
    """
    Write the dub from Gnani's timed transcript. `media_path` is a low-resolution video (preferred, so
    Gemini can read faces and body language) or an audio file. Names are verified afterwards and
    repaired once if the model translated them.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    model = os.getenv("GEMINI_DIALOGUE_MODEL") or MODEL_NAME

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version=API_VERSION))
    uploaded = _wait_until_active(client, client.files.upload(file=media_path))

    prompt = DIALOGUE_PROMPT_TEMPLATE.format(
        target_language=target_language_label,
        duration=total_duration or 0.0,
        line_count=len(source_lines),
        lines_block=format_lines_block(source_lines),
        max_characters=MAX_CHARACTERS,
        tag_list=", ".join(f"<{t}>" for t in GNANI_VALID_TAGS),
        min_part=MIN_PART_SECONDS,
        worked_example=WORKED_EXAMPLE,
        genders=", ".join(GENDERS),
        age_groups=", ".join(AGE_GROUPS),
        archetypes=", ".join(ARCHETYPES),
        emotions=", ".join(EMOTIONS),
    )
    data = _generate(client, model, [prompt, uploaded], DIALOGUE_SYSTEM_INSTRUCTION)

    violations = find_name_violations(source_lines, data)
    if violations:
        _repair_names(client, model, target_language_label, violations, _protected_names(data), data)
        violations = find_name_violations(source_lines, data)

    script = build_script_from_lines(source_lines, data, total_duration)
    for v in violations:
        script["warnings"].append(f"line {v['id']}: name(s) {', '.join(v['names'])} are missing from the dub line")
    return script
