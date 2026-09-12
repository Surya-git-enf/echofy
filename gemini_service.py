# -> gemini_service.py
import json
import os
import re

from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"

ARCHETYPES = ["anime_villain", "monster_deep", "young_boy", "cool_hero", "mature_female", "default"]
EMOTIONS = ["neutral", "excited", "sad", "angry", "calm", "whisper", "serious"]

SYSTEM_INSTRUCTION = (
    "You are a professional film dialogue adapter and voice director — NOT a "
    "literal translator. You are dubbing for movies/anime, writing scripts for "
    "Fish Audio's S2.1 Pro TTS model, which understands BOTH inline bracket "
    "tags (e.g. [laugh], [whispers sweetly], [sigh]) AND phonetically spelled "
    "sound effects. You return ONLY valid JSON matching the schema you are "
    "given. No markdown, no code fences, no explanation, no preamble — JSON only."
)

PROMPT_TEMPLATE = """Transcribe this audio and adapt the dialogue into {target_language} the way a
professional dubbing director would — natural, colloquial, punchy. This is NOT a
literal/dictionary translation.

CRITICAL — SCENE-LEVEL UNDERSTANDING, NOT LINE-BY-LINE SUBSTITUTION:
Before writing any single segment, listen to and understand the WHOLE scene — the
relationship between speakers, the mood, what's actually happening dramatically.
Then write each line to fit that scene naturally, the way a native speaker would
actually talk in that moment — NOT a word-for-word swap of the original sentence
structure. A literal swap like turning "not interesting anymore" into a stiff
phrase such as "inka interesting gaa emundhada" (a rigid, textbook-style rendering)
is exactly what to avoid. Instead, write what a real person would naturally say in
that emotional beat, even if the sentence structure looks nothing like the original.

Rules:
- Preserve natural sentence/segment breaks matching short spoken phrases (roughly 2-8 seconds each).
- start/end are in seconds, as floats, matching where each segment occurs in the audio.
- Keep translated_text close in spoken length to the original phrase so dubbed timing stays natural.
- If multiple speakers, label them speaker_1, speaker_2, etc.

- COLLOQUIAL LOANWORDS: Do not translate everyday words into archaic/formal language.
  Preserve natural English loanwords as commonly spoken (e.g. drink, car, building,
  bike, police, boss, party). Example: "This is a drink which the lord drinks" should
  become something like "Prabhuvu thage drink idhe!" — NOT a stiff formal translation.

- EXPRESSIVE DELIVERY (bracket tags + phonetic sound effects, combined): the TTS model
  understands inline bracket tags like [laughing], [whispers], [sigh], [excited],
  [angry], [crying] placed at the point in the sentence where that delivery happens.
  It ALSO renders phonetically-spelled sound effects naturally. Use BOTH together
  for maximum effect — the tag sets the delivery style, the phonetic spelling gives
  it the actual sound. Only add these where the source audio genuinely calls for it;
  most neutral dialogue should have neither.
  Example: "[laughing] Mwahahaha! Hehehe... You really thought you had a chance?!"
  Example: "[whispers] I'll find you... no matter where you hide."

- CHARACTER ARCHETYPE (who is speaking): classify the speaker's general vocal profile —
  exactly one value from: {archetypes}. Use "default" if nothing distinctive stands out.
  This should stay CONSISTENT for the same speaker across segments.

- EMOTION (how this specific line is delivered right now, for engines that pick
  reference clips by emotion rather than reading tags): exactly one value from:
  {emotions}.

Return JSON in exactly this shape:
{{
  "detected_source_language": "string",
  "segments": [
    {{
      "start": 0.0,
      "end": 3.2,
      "speaker": "speaker_1",
      "character_profile": "one of: {archetypes}",
      "emotion": "one of: {emotions}",
      "original_text": "string",
      "translated_text": "string — natural, scene-appropriate, colloquial, may include [bracket tags] combined with phonetically-spelled sound effects where the moment calls for it"
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
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=api_key)
    uploaded_file = client.files.upload(file=audio_path)

    prompt = PROMPT_TEMPLATE.format(
        target_language=target_language_label,
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

    data = _extract_json(response.text)

    if "segments" not in data or not isinstance(data["segments"], list):
        raise RuntimeError("Gemini response did not include a valid 'segments' list.")

    for seg in data["segments"]:
        if seg.get("character_profile") not in ARCHETYPES:
            seg["character_profile"] = "default"
        if seg.get("emotion") not in EMOTIONS:
            seg["emotion"] = "neutral"

    return data
    
