# -> voice_casting.py
"""
Gives every character in a scene its own distinct voice.

build_cast() takes the characters Gemini identified (gender, age group,
archetype) and returns one voice spec per speaker id. No two speakers ever
share the same spec, even with 5+ characters and only two voices available
for the language: voices are reused with different pitch/rate offsets
(Edge) or a post-processing pitch shift (all other engines).

Spec keys:
  voice_id          unique label, used by the quality gate to count distinct voices
  edge_voice        Edge neural voice name (engine 'edge')
  edge_pitch_hz     Edge pitch offset in Hz
  edge_rate_pct     Edge speaking-rate offset in percent
  fish_reference_id Fish Audio voice id (engine 'fish'), may be None
  pitch_semitones   post-processing pitch shift applied in video_service
                    (0 when the engine already varies the voice natively)

Fish Audio voices are account-specific. Provide them with:
  FISH_VOICE_POOL='{"male": ["id1", "id2"], "female": ["id3", "id4"]}'
and optionally one voice per archetype, e.g. FISH_VOICE_ANIME_VILLAIN=<id>.
"""
import json
import os

from languages import get_language

AGE_PITCH_HZ = {"child": (40, 6), "teen": (20, 3), "young": (8, 0), "adult": (0, 0), "elder": (-12, -8)}
AGE_SEMITONES = {"child": 4.0, "teen": 2.0, "young": 0.0, "adult": 0.0, "elder": -2.0}
GENDER_SEMITONES = {"male": -2.0, "female": 2.0, "neutral": 0.0}
EDGE_VARIANTS = [(0, 0), (-16, -4), (16, 3), (-28, -7), (28, 6), (-40, -10), (40, 9)]

_edge_voice_cache = None


def _norm_gender(value) -> str:
    value = (value or "").strip().lower()
    if value in ("male", "man", "boy", "m"):
        return "male"
    if value in ("female", "woman", "girl", "f"):
        return "female"
    return "neutral"


def _norm_age(value) -> str:
    value = (value or "").strip().lower()
    return value if value in AGE_PITCH_HZ else "adult"


def _all_edge_voices() -> list:
    global _edge_voice_cache
    if _edge_voice_cache is None:
        try:
            import asyncio
            import edge_tts
            _edge_voice_cache = asyncio.run(edge_tts.list_voices())
        except Exception as exc:  # noqa: BLE001
            print(f"[voice_casting] Could not list Edge voices: {exc}")
            _edge_voice_cache = []
    return _edge_voice_cache


def edge_voice_pool(language_key: str) -> dict:
    """{'male': [...], 'female': [...]} of Edge voice names for the language, exact locale first."""
    lang = get_language(language_key)
    locale = (lang.get("edge_locale") or "").lower()
    pool = {"male": [], "female": []}
    if locale:
        prefix = locale.split("-")[0]
        voices = _all_edge_voices()
        exact = [v for v in voices if v.get("Locale", "").lower() == locale]
        loose = [v for v in voices if v.get("Locale", "").lower().split("-")[0] == prefix and v not in exact]
        for v in sorted(exact, key=lambda x: x["ShortName"]) + sorted(loose, key=lambda x: x["ShortName"]):
            gender = _norm_gender(v.get("Gender"))
            if gender in pool:
                pool[gender].append(v["ShortName"])
    if not pool["male"] and not pool["female"] and lang.get("edge_voice"):
        pool["female"].append(lang["edge_voice"])
    return pool


def fish_voice_pool() -> dict:
    pool = {"male": [], "female": []}
    raw = os.getenv("FISH_VOICE_POOL", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            for gender in pool:
                pool[gender] = [str(v) for v in data.get(gender, []) if v]
        except (ValueError, AttributeError):
            print("[voice_casting] FISH_VOICE_POOL is not valid JSON; ignoring it.")
    return pool


def _fish_archetype_voice(archetype: str):
    return os.getenv(f"FISH_VOICE_{(archetype or 'default').upper()}") or None


def _least_used(candidates: list, usage: dict):
    return min(candidates, key=lambda c: (usage.get(c, 0), candidates.index(c)))


def build_cast(characters: list, engine: str, language_key: str, edge_pool: dict = None, fish_pool: dict = None) -> dict:
    """Return {speaker_id: voice_spec}. Every spec has a unique voice_id."""
    cast = {}
    used_ids = set()
    gender_count = {"male": 0, "female": 0}
    usage = {}

    if engine == "edge":
        pool = edge_pool if edge_pool is not None else edge_voice_pool(language_key)
    elif engine == "fish":
        pool = fish_pool if fish_pool is not None else fish_voice_pool()
    else:
        pool = {"male": [], "female": []}

    for index, character in enumerate(characters):
        speaker = character.get("id") or f"speaker_{index + 1}"
        gender = _norm_gender(character.get("gender"))
        age = _norm_age(character.get("age_group"))
        if gender == "neutral":
            gender_pick = "female" if gender_count["male"] > gender_count["female"] else "male"
        else:
            gender_pick = gender
        gender_count[gender_pick] += 1

        spec = {"speaker": speaker, "gender": gender, "age_group": age,
                "edge_voice": None, "edge_pitch_hz": 0, "edge_rate_pct": 0,
                "fish_reference_id": None, "pitch_semitones": 0.0}

        if engine == "edge":
            candidates = pool.get(gender_pick) or pool.get("female" if gender_pick == "male" else "male") or []
            if not candidates:
                raise RuntimeError(f"No Edge voices available for language '{language_key}'.")
            voice = _least_used(candidates, usage)
            usage[voice] = usage.get(voice, 0) + 1
            base_pitch, base_rate = AGE_PITCH_HZ[age]
            for var_pitch, var_rate in EDGE_VARIANTS:
                pitch, rate = base_pitch + var_pitch, base_rate + var_rate
                voice_id = f"edge:{voice}:{pitch:+d}Hz:{rate:+d}%"
                if voice_id not in used_ids:
                    break
            else:
                pitch, rate = base_pitch + 4 * index, base_rate
                voice_id = f"edge:{voice}:{pitch:+d}Hz:{rate:+d}%:{index}"
            spec.update(edge_voice=voice, edge_pitch_hz=pitch, edge_rate_pct=rate, voice_id=voice_id)

        else:
            ref_id = None
            if engine == "fish":
                ref_id = _fish_archetype_voice(character.get("archetype"))
                candidates = [v for v in (pool.get(gender_pick) or []) if v]
                if not ref_id and candidates:
                    ref_id = _least_used(candidates, usage)
                if ref_id:
                    usage[ref_id] = usage.get(ref_id, 0) + 1
            if ref_id and usage[ref_id] == 1:
                semitones = 0.0  # a real, separately configured voice needs no shift on first use
            else:
                # Shared or default voice: separate characters with a pitch shift.
                base = GENDER_SEMITONES[gender_pick] + AGE_SEMITONES[age]
                nth = (usage[ref_id] - 1) if ref_id else index
                semitones = base + (1.5 * ((nth + 1) // 2)) * (1 if nth % 2 else -1)
                semitones = max(-7.0, min(7.0, semitones))
            voice_id = f"{engine}:{ref_id or 'default'}:{semitones:+.1f}st"
            step = 0
            while voice_id in used_ids:
                step += 1
                semitones += 1.0
                voice_id = f"{engine}:{ref_id or 'default'}:{semitones:+.1f}st"
                if step > 40:
                    break
            spec.update(fish_reference_id=ref_id, pitch_semitones=round(semitones, 2), voice_id=voice_id)

        used_ids.add(spec["voice_id"])
        cast[speaker] = spec

    return cast


def ensure_speaker(cast: dict, speaker: str, engine: str, language_key: str) -> dict:
    """A segment referenced a speaker Gemini did not list as a character: cast them now."""
    if speaker not in cast:
        extra = build_cast(
            [{"id": s, "gender": c["gender"], "age_group": c["age_group"]} for s, c in cast.items()]
            + [{"id": speaker, "gender": "neutral", "age_group": "adult"}],
            engine, language_key,
        )
        cast[speaker] = extra[speaker]
    return cast[speaker]
