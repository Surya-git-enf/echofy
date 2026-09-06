# -> gemini_service.py
import json
import os
import re

from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"

ARCHETYPES = ["anime_villain", "monster_deep", "young_boy", "cool_hero", "mature_female", "default"]

SYSTEM_INSTRUCTION = (
    "You are a professional film dialogue adapter and voice director — NOT a "
    "literal translator. You are dubbing for movies/anime. You return ONLY "
    "valid JSON matching the schema you are given. No markdown, no code "
    "fences, no explanation, no preamble — JSON only."
)

PROMPT_TEMPLATE = """Transcribe this audio and adapt the dialogue into {target_language} the way a
professional dubbing director would — natural, colloquial, punchy. This is NOT a
literal/dictionary translation.

Rules:
- Preserve natural sentence/segment breaks matching short spoken phrases (roughly 2-8 seconds each).
- start/end are in seconds, as floats, matching where each segment occurs in the audio.
- Keep translated_text close in spoken length to the original phrase so dubbed timing stays natural.
- If multiple speakers, label them speaker_1, speaker_2, etc.

- COLLOQUIAL LOANWORDS: Do not translate everyday words into archaic/formal language.
  Preserve natural English loanwords as commonly spoken (e.g. drink, car, building,
  bike, police, boss, party). Example: "This is a drink which the lord drinks" should
  become something like "Prabhuvu thage drink idhe!" — NOT a stiff formal translation
  like "Idhi prabhuvu paaneeyam".

- PHONETIC LAUGHTER & ACTING CADENCE: Never insert bracketed meta-tags like [evil laugh]
  or [laughing]. Instead spell vocal actions out phonetically with punctuation so a TTS
  model actually pronounces them naturally. Example: "Mwahahaha! Hehehe... You really
  thought you had a chance?!"

- CHARACTER ARCHETYPE: For each segment, classify the speaker's vocal profile by
  listening to tone, pitch, and delivery in the audio. Choose exactly one value from
  this list: {archetypes}. Use "default" if nothing distinctive stands out.

Return JSON in exactly this shape:
{{
  "detected_source_language": "string",
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker": "speaker_1",
      "character_profile": "one of: {archetypes}",
      "original_text": "string",
      "translated_text": "string — natural, colloquial, phonetically-spelled acting cues, no bracket tags"
    }}
  ]
}}
"""


def _extract_json(raw_text: str) -> dict:
    cleaned = re.sub(r"^```(json)?|```$", "", (raw_text or "").strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def transcribe_and_translate(audio_path: str, target_language_label: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to your environment before running a dubbing job."
        )

    client = genai.Client(api_key=api_key)
    uploaded_file = client.files.upload(file=audio_path)

    prompt = PROMPT_TEMPLATE.format(
        target_language=target_language_label,
        archetypes=", ".join(ARCHETYPES),
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
        raise RuntimeError("Gemini returned an empty response for transcription/translation.")

    data = _extract_json(response.text)

    if "segments" not in data or not isinstance(data["segments"], list):
        raise RuntimeError("Gemini response did not include a valid 'segments' list.")

    # normalize any unexpected archetype value down to "default" rather than
    # letting a bad value silently break voice selection downstream
    for seg in data["segments"]:
        if seg.get("character_profile") not in ARCHETYPES:
            seg["character_profile"] = "default"

    return data
    
