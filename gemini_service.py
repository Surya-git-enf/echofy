# -> gemini_service.py
"""
Uses the modern `google-genai` SDK (NOT the deprecated `google-generativeai`
package). This SDK correctly handles Google AI Studio's newer `AQ.` prefixed
keys — the old SDK threw API_KEY_INVALID on those.

Also inserts inline emotional vocal direction tags (e.g. [excited],
[confident], [laugh]) into the translated text, for engines that support
expressive tags (Fish Audio). Engines that don't support tags (gTTS, Sarvam,
Edge) should strip them before synthesis — see tts_service.strip_emotion_tags.
"""
import json
import os
import re

from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = (
    "You are a professional dubbing script generator. You transcribe spoken "
    "audio, translate it, and return ONLY valid JSON matching the schema you "
    "are given. No markdown, no code fences, no explanation, no preamble — "
    "JSON only."
)

PROMPT_TEMPLATE = """Transcribe this audio and translate the dialogue into {target_language}.

Rules:
- Preserve natural sentence/segment breaks matching short spoken phrases (roughly 2-8 seconds each), so timing stays close to the original speech rhythm.
- start/end are in seconds, as floats, matching where each segment occurs in the audio.
- Keep the translated text close in length/duration to the original phrase where possible, so dubbed speech doesn't run drastically longer or shorter than the source.
- If the audio has multiple speakers, label them speaker_1, speaker_2, etc. If unsure, use speaker_1 for everything.
- Insert AT MOST ONE inline emotional direction tag per segment, placed at the start of translated_text, from this exact set: [excited] [confident] [laugh] [sad] [angry] [calm] [whisper] [serious]. Only add a tag when the tone is clearly conveyed in the audio (e.g. genuine laughter, raised excited voice) — most neutral segments should have NO tag at all. Never invent tags outside this list.

Return JSON in exactly this shape:
{{
  "detected_source_language": "string",
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker": "speaker_1",
      "original_text": "string",
      "translated_text": "string (optionally starting with one [tag])"
    }}
  ]
}}
"""


def _extract_json(raw_text: str) -> dict:
    """Gemini usually returns clean JSON, but strip code fences defensively."""
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

    prompt = PROMPT_TEMPLATE.format(target_language=target_language_label)

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

    return data
