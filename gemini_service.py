"""
Uses Gemini 2.5 Flash to transcribe the extracted audio and translate it,
segment by segment, into the target language. Forces strict JSON output
compatible with the Echofy pipeline and modern Google GenAI SDK.
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
- start and end are in seconds, as floats, matching where each segment occurs in the audio.
- Keep the translated text close in length/duration to the original phrase where possible.
- If the audio has multiple speakers, label them speaker_1, speaker_2, etc. If unsure, use speaker_1 for everything.

Return JSON in exactly this shape:
{{
  "source_language": "string",
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker_id": "speaker_1",
      "original_text": "string",
      "translated_text": "string"
    }}
  ]
}}
"""


def _extract_json(raw_text: str) -> dict:
    """Strip markdown code blocks defensively if present."""
    cleaned = re.sub(r"^```(json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def transcribe_and_translate(audio_path: str, target_language: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")

    # Initialize client (works natively with your AQ. AI Studio key)
    client = genai.Client(api_key=api_key)

    print(f"[Gemini] Uploading audio: {audio_path}")
    uploaded = client.files.upload(file=audio_path)

    prompt = PROMPT_TEMPLATE.format(target_language=target_language)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[uploaded, prompt],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
            ),
        )

        data = _extract_json(response.text)

        if "segments" not in data or not isinstance(data["segments"], list):
            raise RuntimeError("Gemini response did not include a valid 'segments' list.")

        return data

    finally:
        # Clean up temporary uploaded file from Google servers
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass
            
