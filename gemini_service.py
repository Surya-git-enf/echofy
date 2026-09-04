"""
Uses Gemini 2.5 Flash to transcribe the extracted audio and translate it,
segment by segment, into the target language. Forces strict JSON output
so the rest of the pipeline never has to guess-parse free text.
"""
import json
import os
import re

import google.generativeai as genai

MODEL_NAME = "gemini-3.6-flash"

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

Return JSON in exactly this shape:
{{
  "detected_source_language": "string",
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker": "speaker_1",
      "original_text": "string",
      "translated_text": "string"
    }}
  ]
}}
"""


def _extract_json(raw_text: str) -> dict:
    """Gemini usually returns clean JSON, but strip code fences defensively."""
    cleaned = re.sub(r"^```(json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def transcribe_and_translate(audio_path: str, target_language_label: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to backend/.env before running a dubbing job."
        )
    genai.configure(api_key=api_key)

    uploaded = genai.upload_file(audio_path)

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config={"response_mime_type": "application/json"},
    )

    prompt = PROMPT_TEMPLATE.format(target_language=target_language_label)
    response = model.generate_content([uploaded, prompt])

    data = _extract_json(response.text)

    if "segments" not in data or not isinstance(data["segments"], list):
        raise RuntimeError("Gemini response did not include a valid 'segments' list.")

    return data

