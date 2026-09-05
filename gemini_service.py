"""
Gemini Dubbing Adapter:
Acts as a film dialogue adapter (not a literal translator).
Detects character profile (age, tone, archetype) and injects natural laughter/pacing.
"""
import json
import os
import re
from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = (
    "You are a top-tier Tollywood / anime dubbing dialogue writer and voice director. "
    "CRITICAL RULES FOR ADAPTATION: "
    "1. NEVER TRANSLATE LITERALLY. Write dialogue the way modern people actually talk. "
    "2. For Telugu dubbing: Use conversational 'Telugish' where natural. Keep common everyday English "
    "   words as-is in Telugu script or phonetic spelling (e.g., use 'drink', 'car', 'building', 'party', "
    "   'police', 'boss' instead of archaic words like 'bhavanam' or 'paaneeyam'). "
    "   Example: 'This is the drink the lord drinks' -> 'Idhi... aa devudu thage special drink!' "
    "3. NEVER use bracket tags like [evil laugh] or [screams]. "
    "   Spell out laughs and emotional noises phonetically: 'Mwahahaha!', 'Hehe... hahahaha!', 'Arey...', 'Orey!'. "
    "4. Analyze the speaker's vocal archetype in the audio and classify them into one of these: "
    "   ['anime_villain', 'young_boy', 'monster_deep', 'cool_hero', 'mature_female', 'default']. "
    "5. Return strictly valid JSON."
)

PROMPT_TEMPLATE = """Analyze this audio. Identify the character persona, transcribe the dialogue, and adapt it into punchy, cinematic {target_language}.

Output Schema:
{{
  "source_language": "string",
  "character_profile": "anime_villain | young_boy | monster_deep | cool_hero | mature_female | default",
  "character_description": "short summary, e.g. 20-year-old arrogant villain with evil laugh",
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker_id": "speaker_1",
      "original_text": "string",
      "translated_text": "Mwahahaha! Prabhuvu thage drink idhe!"
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
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")[span_3](start_span)[span_3](end_span)

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
            
