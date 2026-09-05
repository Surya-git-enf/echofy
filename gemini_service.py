"""
Translates and adapts audio transcripts using Gemini 2.5 Flash.
Outputs conversational dubbing dialogue complete with Fish Audio emotion direction tags.
"""
import json
import os
import re
from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = (
    "You are an elite video dubbing script adapter and vocal director. "
    "Your objective is to translate and adapt spoken dialogue so it sounds 100% natural, "
    "colloquial, and emotionally alive when spoken by a voice actor. "
    "Never produce stiff, literal, or academic translations. "
    "You must insert expressive emotion/direction tags at the beginning of phrases "
    "such as [excited], [serious], [laugh], [whispering], [curious], or [casual] "
    "matching the tone of the speaker in that segment. "
    "Output strictly valid JSON with no markdown formatting."
)

PROMPT_TEMPLATE = """Transcribe and adapt this audio into punchy, conversational {target_language}.

Rules:
1. Adapt the phrasing to match conversational idioms in {target_language}.
2. Ensure the duration of translated phrases matches the original segment window (start to end).
3. Prefix translated segments with an appropriate inline direction tag like [excited], [confident], [calm], [curious], [laugh] to capture the speaker's emotional state.
4. Keep timestamps as floats in seconds.

Output must match this exact JSON schema:
{{
  "source_language": "string",
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker_id": "speaker_1",
      "original_text": "string",
      "translated_text": "[excited] Hey, welcome back everyone!"
    }}
  ]
}}
"""


def _extract_json(raw_text: str) -> dict:
    cleaned = re.sub(r"^```(json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def transcribe_and_translate(audio_path: str, target_language: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")

    client = genai.Client(api_key=api_key)
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
            raise RuntimeError("Gemini response did not contain a valid 'segments' list.")

        return data

    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass
            
