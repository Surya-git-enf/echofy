"""
Transcribes and translates audio using Gemini 2.5 Flash via modern google-genai SDK.
"""
import json
import os
import re
from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = (
    "You are an expert film and video dubbing script adapter. "
    "Transcribe spoken dialogue, then adapt it into natural, punchy, spoken conversation "
    "matching the flow of the original timing. Avoid stiff, textbook translations. "
    "At the start of translated_text, include an appropriate vocal direction in brackets "
    "such as [excited], [confident], [calm], [curious], [laugh], or [serious]. "
    "Output must be strictly valid JSON without markdown code blocks."
)

PROMPT_TEMPLATE = """Transcribe and adapt this audio into conversational {target_language}.

Output format:
{{
  "source_language": "string",
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker_id": "speaker_1",
      "original_text": "string",
      "translated_text": "[excited] your natural dialogue here"
    }}
  ]
}}
"""


def _clean_json(text: str) -> dict:
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def transcribe_and_translate(audio_path: str, target_language: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")[span_6](start_span)[span_6](end_span)

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
        data = _clean_json(response.text)
        if "segments" not in data or not isinstance(data["segments"], list):
            raise RuntimeError("Gemini response missing valid segments list.")
        return data
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass
            
