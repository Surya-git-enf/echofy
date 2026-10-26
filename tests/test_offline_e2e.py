"""
Offline end-to-end test. Runs the REAL pipeline (ffmpeg, separation fallback, casting, timing fit,
ducking mix, merge) and the REAL quality gate on test/input/input.mp4, with only the network
services replaced by stand-ins:
  - Gemini returns a fixed 5-character Telugu script
  - TTS is a tone generator whose pitch follows the character's voice
  - Supabase and stemsplit are unavailable, so the FFmpeg background fallback is exercised

Run:  python tests/test_offline_e2e.py        (or: pytest tests)
It proves the plumbing and the gate logic. It cannot prove the real voices or translations sound
good; that needs scripts/run_local_dub.py with real API keys.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# --- stand-ins for packages/services that need network or credentials -------------------------
for name in ("google", "google.genai", "google.genai.types"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["google"].genai = sys.modules["google.genai"]
sys.modules["google.genai"].types = sys.modules["google.genai.types"]
sys.modules["google.genai"].Client = object
fake_supabase = types.ModuleType("supabase_service")
fake_supabase.DUBBING_OUTPUTS_BUCKET = "dubbing_outputs"
fake_supabase.VIDEO_UPLOADS_BUCKET = "video_uploads"
sys.modules["supabase_service"] = fake_supabase
os.environ.pop("STEMSPLIT_API_KEY", None)  # forces the fallback path

import eval_dubbing  # noqa: E402
import gemini_service  # noqa: E402
import pipeline  # noqa: E402
import tts_service  # noqa: E402
import video_service  # noqa: E402
import voice_casting  # noqa: E402

INPUT = os.path.join(ROOT, "test", "input", "input.mp4")
TELUGU = ["ఏంటి ఇది?", "నేను చెప్తున్నా కదా, వినరా!", "అబ్బా, ఇంకెంత సేపు రా బాబు", "సరే సరే, పద వెళ్దాం",
          "ఇక్కడ ఎవరో ఉన్నారు, జాగ్రత్త", "హహ్హా, నేను చూసుకుంటా లే", "ఏమైనా సరే, ఆగను నేను", "చాలు చాలు, అర్థమైంది"]
CHARACTERS = [
    {"id": "speaker_1", "gender": "male", "age_group": "young", "archetype": "cool_hero", "voice_description": "bold"},
    {"id": "speaker_2", "gender": "female", "age_group": "young", "archetype": "default", "voice_description": "bright"},
    {"id": "speaker_3", "gender": "male", "age_group": "elder", "archetype": "default", "voice_description": "gruff"},
    {"id": "speaker_4", "gender": "female", "age_group": "child", "archetype": "default", "voice_description": "squeaky"},
    {"id": "speaker_5", "gender": "male", "age_group": "adult", "archetype": "anime_villain", "voice_description": "deep"},
]


def fake_script(duration, n_speakers=5):
    segments = []
    for i in range(8):
        start = 0.4 + i * 1.15
        segments.append({"start": start, "end": start + 1.0, "speaker": CHARACTERS[i % n_speakers]["id"],
                         "character_profile": "default", "emotion": "neutral",
                         "original_text": f"original line {i}", "translated_text": TELUGU[i]})
    return {"detected_source_language": "English", "scene_summary": "test scene",
            "characters": CHARACTERS[:n_speakers], "segments": segments}


def fake_tts(text, language_key, out_path, engine="echofy", character_profile="default", emotion="neutral", voice=None):
    """Tone whose frequency follows the voice, 0.2s padding each side, length follows the text."""
    freq = 180 + (abs(hash(voice["voice_id"])) % 300)
    length = 0.3 + 0.03 * len(text)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f={freq}:d={length}",
                    "-af", "volume=0.4,adelay=200,apad=pad_dur=0.2", "-c:a", "libmp3lame", out_path], check=True)


def run_case(engine, work, n_speakers=5):
    gemini_service.transcribe_and_translate = lambda path, label, total=0.0: fake_script(total, n_speakers)
    tts_service.generate_speech = fake_tts
    voice_casting.edge_voice_pool = lambda lang: {"male": ["te-IN-MohanNeural"], "female": ["te-IN-ShrutiNeural"]}
    result = pipeline.process_video(INPUT, "telugu", engine, work)
    result["input_path"] = INPUT
    result["expected_speakers"] = n_speakers
    with open(os.path.join(work, "run.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    return result


def test_five_characters_pass_the_gate():
    for engine in ("edge", "gtts"):
        work = tempfile.mkdtemp()
        try:
            result = run_case(engine, work)
            voices = {s["speaker"]: s["voice_id"] for s in result["segments"]}
            assert len(voices) == 5 and len(set(voices.values())) == 5, voices
            assert result["separation_method"].startswith("ffmpeg"), result["separation_method"]
            outcome = eval_dubbing.evaluate_run(work, use_judge=False)
            eval_dubbing.print_result(outcome)
            failed = [c["name"] for c in outcome["checks"] if not c["passed"]]
            # Offline there is no stemsplit, so the fallback runs and the gate must say so, and nothing else.
            assert failed == ["vocals_separated"], (engine, failed)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def test_gate_catches_lost_background():
    work = tempfile.mkdtemp()
    try:
        run_case("gtts", work)
        silent = os.path.join(work, "silent.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "10.1", silent], check=True)
        shutil.move(silent, os.path.join(work, "background_applied.wav"))
        outcome = eval_dubbing.evaluate_run(work, use_judge=False)
        failed = {c["name"] for c in outcome["checks"] if not c["passed"]}
        assert outcome["verdict"] == "FAIL" and "background_present" in failed, failed
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_gate_catches_shared_voice_and_missing_characters():
    work = tempfile.mkdtemp()
    try:
        run_case("gtts", work, n_speakers=2)
        run = json.load(open(os.path.join(work, "run.json"), encoding="utf-8"))
        run["expected_speakers"] = 4  # the scene should have had 4 characters
        json.dump(run, open(os.path.join(work, "run.json"), "w", encoding="utf-8"), ensure_ascii=False)
        outcome = eval_dubbing.evaluate_run(work, use_judge=False)
        failed = {c["name"] for c in outcome["checks"] if not c["passed"]}
        assert "distinct_voice_per_character" in failed, failed
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_language_resolution_and_engine_checks():
    from languages import engine_can_speak, get_language
    assert get_language("es-MX")["label"] == "Spanish"
    assert get_language("Klingon")["label"] == "Klingon"
    assert engine_can_speak("fish", "klingon")[0] and not engine_can_speak("sarvam", "french")[0]


def test_normaliser_cleans_gemini_output():
    raw = {"segments": [{"start": "1", "end": 0.5, "speaker": "A", "translated_text": "hi", "emotion": "??"},
                        {"start": 0, "end": 3, "speaker": "B", "translated_text": "  "}],
           "characters": [{"id": "A", "gender": "Female", "age_group": "elder", "archetype": "nope"}]}
    out = gemini_service.normalise_script(raw, 10.0)
    assert len(out["segments"]) == 1 and out["segments"][0]["end"] > out["segments"][0]["start"]
    assert out["characters"][0]["gender"] == "female" and out["characters"][0]["archetype"] == "default"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nall {len(tests)} offline tests passed")
