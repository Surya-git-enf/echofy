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

REAL_GENERATE_SPEECH = tts_service.generate_speech  # before any test swaps in the fake
REAL_TRANSCRIBE = gemini_service.transcribe_and_translate
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


class FakeResponse:
    def __init__(self, status=200, content=b"", content_type="audio/mpeg", text=""):
        self.status_code, self.content, self.text = status, content, text
        self.headers = {"Content-Type": content_type}


def _tone_mp3(path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=0.7,volume=0.4",
                    "-c:a", "libmp3lame", path], check=True)
    return open(path, "rb").read()


def test_gnani_request_shape_retry_and_errors():
    work = tempfile.mkdtemp()
    try:
        audio = _tone_mp3(os.path.join(work, "t.mp3"))
        calls = []
        replies = [FakeResponse(429, text="busy"), FakeResponse(200, audio)]

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append((url, headers, json))
            return replies.pop(0)

        os.environ["GNANI_API_KEY"] = "test-key"
        tts_service.requests.post, tts_service.time.sleep = fake_post, lambda s: None
        out = os.path.join(work, "out.mp3")
        REAL_GENERATE_SPEECH("[angry] Get out of here!", "telugu", out, engine="gnani", emotion="angry",
                             voice={"gnani_voice": "Harshad"})
        url, headers, payload = calls[-1]
        assert url == "https://api.vachana.ai/api/v1/tts/inference" and len(calls) == 2  # 429 then success
        assert headers["X-API-Key-ID"] == "test-key"
        assert payload["model"] == "timbre-v3.0" and payload["voice"] == "Harshad" and payload["language"] == "te-IN"
        assert payload["text"] == "<shouting> Get out of here!" and payload["speed"] == 1.1
        assert payload["audio_config"]["container"] == "mp3" and os.path.getsize(out) == len(audio)

        tts_service.requests.post = lambda *a, **k: FakeResponse(403, text="no credits")
        try:
            REAL_GENERATE_SPEECH("hello", "telugu", out, engine="gnani", voice={"gnani_voice": "Harshad"})
            raise AssertionError("403 should raise")
        except RuntimeError as exc:
            assert "GNANI_API_KEY" in str(exc)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_gnani_five_characters_through_the_real_engine_code():
    """Real pipeline + real gnani code; only the HTTP call is replaced. Checks what Vachana would receive."""
    work, audio_dir = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        audio = _tone_mp3(os.path.join(audio_dir, "t.mp3"))
        sent = []

        def fake_post(url, headers=None, json=None, timeout=None):
            sent.append(json)
            return FakeResponse(200, audio)

        os.environ["GNANI_API_KEY"] = "test-key"
        tts_service.requests.post = fake_post
        tts_service.generate_speech = REAL_GENERATE_SPEECH
        script = fake_script(10.12)
        script["segments"][1]["emotion"] = "angry"
        script["segments"][3]["emotion"] = "excited"
        gemini_service.transcribe_and_translate = lambda path, label, total=0.0: script
        result = pipeline.process_video(INPUT, "telugu", "gnani", work)

        voices_by_speaker = {}
        for seg, payload in zip(result["segments"], sent):
            voices_by_speaker.setdefault(seg["speaker"], set()).add(payload["voice"])
        assert len(voices_by_speaker) == 5 and all(len(v) == 1 for v in voices_by_speaker.values()), voices_by_speaker
        assert len({next(iter(v)) for v in voices_by_speaker.values()}) == 5  # five different Gnani voices
        assert all(p["language"] == "te-IN" and p["model"] == "timbre-v3.0" for p in sent)
        assert sent[1]["text"].startswith("<shouting>") and sent[3]["text"].startswith("<excited>")
        assert all(os.path.exists(result[k]) for k in ("output_path", "voice_track_path", "background_applied_path"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(audio_dir, ignore_errors=True)


def test_gnani_language_limits():
    from languages import engine_can_speak
    assert engine_can_speak("gnani", "telugu")[0] and engine_can_speak("gnani", "hinglish")[0]
    ok, reason = engine_can_speak("gnani", "french")
    assert not ok and "fish" in reason


def test_gemini_client_uses_v1beta_for_system_instruction():
    """The default v1 API rejects system_instruction with 400 INVALID_ARGUMENT; the client must ask for v1beta."""
    seen = {}

    class FakeFiles:
        def upload(self, file):
            return "uploaded"

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen["config"] = config
            return types.SimpleNamespace(text=json.dumps({"segments": [
                {"start": 0, "end": 1, "speaker": "speaker_1", "translated_text": "hi"}]}))

    class FakeClient:
        def __init__(self, api_key=None, http_options=None):
            seen["http_options"] = http_options
            self.files, self.models = FakeFiles(), FakeModels()

    genai, gtypes = sys.modules["google.genai"], sys.modules["google.genai.types"]
    saved = (genai.Client, getattr(gtypes, "HttpOptions", None), getattr(gtypes, "GenerateContentConfig", None))
    genai.Client = FakeClient
    gtypes.HttpOptions = lambda **kw: kw
    gtypes.GenerateContentConfig = lambda **kw: kw
    os.environ["GEMINI_API_KEY"] = "test-key"
    try:
        out = REAL_TRANSCRIBE("a.wav", "Hindi", 5.0)
    finally:
        genai.Client, gtypes.HttpOptions, gtypes.GenerateContentConfig = saved
    assert seen["http_options"] == {"api_version": "v1beta"}
    assert "system_instruction" in seen["config"]
    assert out["segments"][0]["translated_text"] == "hi"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nall {len(tests)} offline tests passed")
