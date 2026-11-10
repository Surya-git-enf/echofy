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
import re
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
import stt_service  # noqa: E402
import tts_service  # noqa: E402
import video_service  # noqa: E402
import voice_casting  # noqa: E402

REAL_GENERATE_SPEECH = tts_service.generate_speech  # before any test swaps in the fake
REAL_TRANSCRIBE = gemini_service.transcribe_and_translate
REAL_TRANSCRIBE_AUDIO = stt_service.transcribe_audio
REAL_ADAPT = gemini_service.adapt_dialogue
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
    os.environ["TRANSCRIBE_ENGINE"] = "gemini"
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
        REAL_GENERATE_SPEECH("[angry] ఇక్కడ నుంచి వెళ్ళు!", "telugu", out, engine="gnani", emotion="angry",
                             voice={"gnani_voice": "Harshad"})
        url, headers, payload = calls[-1]
        assert url == "https://api.vachana.ai/api/v1/tts/inference" and len(calls) == 2  # 429 then success
        assert headers["X-API-Key-ID"] == "test-key"
        assert payload["model"] == "timbre-v3.0" and payload["voice"] == "Harshad" and payload["language"] == "te-IN"
        assert payload["text"] == "<shouting> ఇక్కడ నుంచి వెళ్ళు!" and payload["speed"] == 1.1
        assert payload["audio_config"]["container"] == "mp3" and os.path.getsize(out) == len(audio)

        # a Telugu line that holds English words (names, "dad", "cancer") is sent with language "auto"
        replies.append(FakeResponse(200, audio))
        REAL_GENERATE_SPEECH("<exhales> నీ dad కి <pauses> నిజంగానే cancer ఉందా?", "telugu", out, engine="gnani",
                             voice={"gnani_voice": "Harshad"})
        assert calls[-1][2]["language"] == "auto" and calls[-1][2]["text"].startswith("<exhales> నీ dad")

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
        os.environ["TRANSCRIBE_ENGINE"] = "gemini"
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


# ---------------------------------------------------------------------------------------------
# Gnani speech-to-text and the Gemini dialogue writer
# ---------------------------------------------------------------------------------------------
def _gated_audio(path, bursts, total):
    """A 300 Hz tone that is audible only inside the given (start, end) bursts."""
    gate = "+".join(f"between(t,{a},{b})" for a, b in bursts)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f=300:d={total}",
                    "-af", f"volume='if({gate},0.5,0)':eval=frame", "-ar", "16000", "-ac", "1", path], check=True)
    return path


class FakeSTTResponse:
    def __init__(self, status=200, transcript="", text=""):
        self.status_code, self._transcript, self.text = status, transcript, text

    def json(self):
        return {"success": True, "transcript": self._transcript, "model": "prisma-v3.0"}


def test_stt_finds_spoken_stretches_and_splits_long_ones():
    work = tempfile.mkdtemp()
    try:
        # two short lines, then 14 s of speech with a clear pause at 12 s that must be used to split it
        bursts = [(0.5, 2.5), (3.5, 5.0), (6.0, 12.0), (12.5, 20.0)]
        audio = _gated_audio(os.path.join(work, "a.wav"), bursts, 22)
        found = stt_service.find_speech_intervals(audio, 22.0)
        assert len(found) == 4, found
        for (a, b), (ea, eb) in zip(found, bursts):
            assert abs(a - ea) < 0.2 and abs(b - eb) < 0.2, (found, bursts)
        # unbroken speech longer than the API limit is hard-split under the 25 s cap
        long_audio = _gated_audio(os.path.join(work, "b.wav"), [(0.5, 39.5)], 40)
        pieces = stt_service.find_speech_intervals(long_audio, 40.0)
        assert len(pieces) == 2 and all(b - a <= stt_service.MAX_CHUNK_SECONDS for a, b in pieces), pieces
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_stt_request_shape_lines_and_timing():
    work = tempfile.mkdtemp()
    try:
        audio = _gated_audio(os.path.join(work, "a.wav"), [(0.5, 2.0), (3.0, 4.5), (5.5, 7.0)], 8)
        sent, answers = [], iter(["hello there", "", "see you later"])  # the middle stretch is music, not speech

        def fake_post(url, headers=None, data=None, files=None, timeout=None):
            sent.append({"url": url, "headers": headers, "data": data, "file": files["audio_file"].read(64)})
            return FakeSTTResponse(200, next(answers))

        os.environ["GNANI_API_KEY"] = "test-key"
        os.environ.pop("GNANI_STT_LANGUAGE", None)
        stt_service.requests.post = fake_post
        stt_service.transcribe_audio = REAL_TRANSCRIBE_AUDIO
        lines = stt_service.transcribe_audio(audio, 8.0, work)

        assert [l["text"] for l in lines] == ["hello there", "see you later"]
        assert [l["id"] for l in lines] == [0, 1]  # ids are re-numbered after silent chunks are dropped
        assert abs(lines[0]["start"] - 0.5) < 0.2 and abs(lines[1]["end"] - 7.0) < 0.2
        assert all(r["url"] == "https://api.vachana.ai/stt/v3" for r in sent)
        assert all(r["headers"] == {"X-API-Key-ID": "test-key"} for r in sent)
        assert all(r["data"] == {"language_code": "en-IN,hi-IN,te-IN,ta-IN", "model": "prisma-v3.0"} for r in sent)
        assert all(r["file"][:4] == b"RIFF" for r in sent)  # a WAV was uploaded
        os.environ["GNANI_STT_LANGUAGE"] = "te-IN"
        sent.clear(); answers = iter(["a", "b", "c"])
        stt_service.transcribe_audio(audio, 8.0, work)
        assert sent[0]["data"]["language_code"] == "te-IN"
    finally:
        os.environ.pop("GNANI_STT_LANGUAGE", None)
        shutil.rmtree(work, ignore_errors=True)


def test_stt_retries_and_errors():
    work = tempfile.mkdtemp()
    try:
        wav = _gated_audio(os.path.join(work, "a.wav"), [(0.2, 1.5)], 2)
        stt_service.time.sleep = lambda s: None
        os.environ["GNANI_API_KEY"] = "test-key"
        replies = iter([FakeSTTResponse(500, text="boom"), FakeSTTResponse(429, text="slow down"), FakeSTTResponse(200, "ok")])
        stt_service.requests.post = lambda *a, **k: next(replies)
        assert stt_service.transcribe_chunk(wav, "en-IN") == "ok"

        stt_service.requests.post = lambda *a, **k: FakeSTTResponse(401, text="bad key")
        try:
            stt_service.transcribe_chunk(wav, "en-IN")
            raise AssertionError("401 should raise")
        except RuntimeError as exc:
            assert "GNANI_API_KEY" in str(exc)

        stt_service.requests.post = lambda *a, **k: FakeSTTResponse(400, text="UNSUPPORTED_LANGUAGE")
        try:
            stt_service.transcribe_chunk(wav, "xx-XX")
            raise AssertionError("400 should raise without retrying")
        except RuntimeError as exc:
            assert "400" in str(exc)

        os.environ.pop("GNANI_API_KEY")
        try:
            stt_service.transcribe_chunk(wav, "en-IN")
            raise AssertionError("missing key should raise")
        except RuntimeError as exc:
            assert "GNANI_API_KEY is not set" in str(exc)
    finally:
        shutil.rmtree(work, ignore_errors=True)


SOURCE_LINES = [
    {"id": 0, "start": 0.5, "end": 2.0, "text": "Hi, is this seat taken?"},
    {"id": 1, "start": 2.4, "end": 4.0, "text": "No, please, sit."},
    {"id": 2, "start": 4.5, "end": 6.0, "text": "Thanks. I'm Maya."},
]


def test_dialogue_is_joined_to_the_transcript_by_id():
    data = {"detected_source_language": "English", "scene_summary": "meeting",
            "characters": [{"id": "speaker_1", "gender": "female"}, {"id": "speaker_2", "gender": "male"}],
            "lines": [  # out of order, one corrected, one with an unknown speaker id
                {"id": 2, "speaker": "speaker_1", "emotion": "calm", "text": "థ్యాంక్స్, నేను మాయ"},
                {"id": 0, "speaker": "speaker_1", "emotion": "excited", "source_text": "Hi, is this seat free?", "text": "హాయ్, ఈ సీట్ ఖాళీయేనా?"},
                {"id": 1, "speaker": "speaker_9", "emotion": "bogus", "text": "లేదు లేదు, కూర్చో"},
            ]}
    script = gemini_service.build_script_from_lines(SOURCE_LINES, data, 7.0)
    segs = script["segments"]
    assert [s["start"] for s in segs] == [0.5, 2.4, 4.5]  # timing is Gnani's, never Gemini's
    assert segs[0]["original_text"] == "Hi, is this seat free?" and segs[1]["original_text"] == "No, please, sit."
    assert segs[1]["emotion"] == "neutral" and {c["id"] for c in script["characters"]} >= {"speaker_1", "speaker_2", "speaker_9"}

    half = {"lines": [{"id": 0, "speaker": "speaker_1", "text": "ఒకటి"}]}
    try:
        gemini_service.build_script_from_lines(SOURCE_LINES, half, 7.0)
        raise AssertionError("too many missing lines should raise")
    except RuntimeError as exc:
        assert "1 of 3" in str(exc)


def test_adapt_dialogue_sends_the_transcript_and_audio_to_gemini():
    seen = {}

    class FakeFiles:
        def upload(self, file):
            seen["audio"] = file
            return "uploaded"

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen["contents"], seen["config"] = contents, config
            return types.SimpleNamespace(text=json.dumps({"lines": [
                {"id": i, "speaker": "speaker_1", "emotion": "neutral", "text": f"line {i}"} for i in range(3)]}))

    class FakeClient:
        def __init__(self, api_key=None, http_options=None):
            self.files, self.models = FakeFiles(), FakeModels()

    genai, gtypes = sys.modules["google.genai"], sys.modules["google.genai.types"]
    saved = (genai.Client, getattr(gtypes, "HttpOptions", None), getattr(gtypes, "GenerateContentConfig", None))
    genai.Client = FakeClient
    gtypes.HttpOptions = lambda **kw: kw
    gtypes.GenerateContentConfig = lambda **kw: kw
    os.environ["GEMINI_API_KEY"] = "test-key"
    try:
        out = REAL_ADAPT(SOURCE_LINES, "a.wav", "Telugu", 7.0)
    finally:
        genai.Client, gtypes.HttpOptions, gtypes.GenerateContentConfig = saved
    prompt = seen["contents"][0]
    assert 'id=0  1.5s  max 4 words  (span 0.5 to 2.0)  "Hi, is this seat taken?"' in prompt
    assert "Telugu" in prompt and not re.search(r"\{[a-z_]+\}", prompt)  # no unfilled template fields
    assert "NAMES NEVER CHANGE" in prompt and "<whispers>" in prompt and "<angry>" not in prompt
    assert "timbre-v3.0" in prompt and "in the middle of a sentence" in prompt
    assert seen["contents"][1] == "uploaded" and seen["audio"] == "a.wav"
    assert seen["config"]["system_instruction"] == gemini_service.DIALOGUE_SYSTEM_INSTRUCTION
    assert [s["translated_text"] for s in out["segments"]] == ["line 0", "line 1", "line 2"]


def test_pipeline_uses_gnani_transcription_by_default():
    work = tempfile.mkdtemp()
    try:
        os.environ.pop("TRANSCRIBE_ENGINE", None)
        lines = [{"id": i, "start": 0.4 + i * 1.15, "end": 1.4 + i * 1.15, "text": f"source {i}"} for i in range(8)]
        calls = {}

        def fake_stt(path, total, work_dir, **kw):
            calls["stt"] = total
            return lines

        def fake_adapt(source_lines, path, label, total):
            calls["adapt"] = (len(source_lines), label)
            return gemini_service.build_script_from_lines(source_lines, {
                "characters": CHARACTERS,
                "lines": [{"id": l["id"], "speaker": CHARACTERS[l["id"] % 5]["id"], "emotion": "neutral", "text": TELUGU[l["id"]]}
                          for l in source_lines]}, total)

        stt_service.transcribe_audio = fake_stt
        gemini_service.adapt_dialogue = fake_adapt
        gemini_service.transcribe_and_translate = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Gemini must not transcribe"))
        tts_service.generate_speech = fake_tts
        voice_casting.edge_voice_pool = lambda lang: {"male": ["te-IN-MohanNeural"], "female": ["te-IN-ShrutiNeural"]}
        result = pipeline.process_video(INPUT, "telugu", "edge", work)
        assert calls["adapt"] == (8, "Telugu") and calls["stt"] > 0
        assert [round(s["start"], 2) for s in result["segments"]] == [round(l["start"], 2) for l in lines]
        assert len({s["speaker"] for s in result["segments"]}) == 5

        # a video with no recognised speech stops with a clear message instead of dubbing silence
        stt_service.transcribe_audio = lambda *a, **k: []
        try:
            pipeline.process_video(INPUT, "telugu", "edge", tempfile.mkdtemp())
            raise AssertionError("no speech should raise")
        except RuntimeError as exc:
            assert "no spoken dialogue" in str(exc)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------------------------
# Names, tags, split parts, repair and the video upload wait
# ---------------------------------------------------------------------------------------------
def _fake_gemini(replies, upload_result="uploaded"):
    """Install a fake Gemini client that answers with the given JSON replies in order. Returns (calls, restore)."""
    calls, answers = [], iter(replies)

    class FakeFiles:
        def upload(self, file):
            return upload_result

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append(contents)
            return types.SimpleNamespace(text=json.dumps(next(answers)))

    class FakeClient:
        def __init__(self, api_key=None, http_options=None):
            self.files, self.models = FakeFiles(), FakeModels()

    genai, gtypes = sys.modules["google.genai"], sys.modules["google.genai.types"]
    saved = (genai.Client, getattr(gtypes, "HttpOptions", None), getattr(gtypes, "GenerateContentConfig", None))
    genai.Client, gtypes.HttpOptions, gtypes.GenerateContentConfig = FakeClient, (lambda **kw: kw), (lambda **kw: kw)
    os.environ["GEMINI_API_KEY"] = "test-key"

    def restore():
        genai.Client, gtypes.HttpOptions, gtypes.GenerateContentConfig = saved
    return calls, restore


NAME_LINES = [
    {"id": 0, "start": 1.0, "end": 3.0, "text": "Tiger, you promised."},
    {"id": 1, "start": 4.0, "end": 5.5, "text": "Sorry, the traffic was terrible."},
]
CHAR = [{"id": "speaker_1", "name_guess": "Mira", "gender": "female"}, {"id": "speaker_2", "name_guess": "Tiger", "gender": "male"}]


def test_a_translated_name_is_repaired_once():
    first = {"keep_terms": ["Tiger"], "characters": CHAR, "lines": [
        {"id": 0, "speaker": "speaker_1", "emotion": "serious", "text": "బెబ్బులి, నువ్వు మాటిచ్చావ్ కదా."},  # the name became a word
        {"id": 1, "speaker": "speaker_2", "emotion": "calm", "text": "Sorry, traffic దారుణంగా ఉంది."}]}
    repaired = {"lines": [{"id": 0, "text": "Tiger, నువ్వు మాటిచ్చావ్ కదా."}]}
    calls, restore = _fake_gemini([first, repaired])
    try:
        script = REAL_ADAPT(NAME_LINES, "v.mp4", "Telugu", 6.0)
    finally:
        restore()
    assert len(calls) == 2 and "must contain: Tiger" in calls[1][0]
    assert script["segments"][0]["translated_text"].startswith("Tiger,") and script["warnings"] == []
    assert script["keep_terms"] == ["Tiger", "Mira"]

    stubborn = {"lines": [{"id": 0, "text": "బెబ్బులి, మాటిచ్చావ్ కదా."}]}
    calls, restore = _fake_gemini([first, stubborn])
    try:
        script = REAL_ADAPT(NAME_LINES, "v.mp4", "Telugu", 6.0)
    finally:
        restore()
    assert any("Tiger" in w and "missing" in w for w in script["warnings"])  # reported, never hidden


def test_tags_are_limited_and_tag_only_parts_are_dropped():
    assert tts_service.clean_audio_tags("<Whispers> hi <angry> there <clear throat> x") == "<whispers> hi there <clears throat> x"
    assert tts_service.strip_audio_tags("<sigh> hello <pauses> world") == "hello world"
    assert gemini_service.has_spoken_words("<sigh> Hmm") and not gemini_service.has_spoken_words("<sigh> <pauses> ...")
    data = {"characters": CHAR, "lines": [
        {"id": 0, "speaker": "speaker_1", "text": "<sigh>"},                       # tag only
        {"id": 1, "speaker": "speaker_2", "text": "<angry> Sorry, <pauses> okay."}]}  # <angry> is not a Gnani tag
    script = gemini_service.build_script_from_lines(NAME_LINES, data, 6.0)
    assert [s["translated_text"] for s in script["segments"]] == ["Sorry, <pauses> okay."]
    assert any("no spoken words" in w for w in script["warnings"])


def test_split_parts_stay_inside_their_source_span():
    src = {"id": 5, "start": 40.0, "end": 44.0, "text": "Okay, okay, sorry! It's fine. Come here."}
    parts = [{"start": 42.0, "end": 47.0}, {"start": 38.0, "end": 41.0}]  # out of order, outside the span
    times = gemini_service._clamp_parts(parts, src)
    assert all(40.0 <= a < b <= 44.0 for a, b in times), times
    assert times[0][1] <= times[1][0] + 1e-9  # in order, not overlapping
    assert gemini_service._clamp_parts([{}], src) == [(40.0, 44.0)]  # no times: the whole span
    data = {"characters": CHAR, "lines": [
        {"id": 5, "speaker": "speaker_2", "start": 40.0, "end": 41.8, "text": "Okay, okay, sorry!"},
        {"id": 5, "speaker": "speaker_1", "start": 42.0, "end": 44.0, "text": "<laugh> పర్లేదు, ఇలా రా."}]}
    script = gemini_service.build_script_from_lines([src], data, 50.0)
    assert [(s["start"], s["speaker"]) for s in script["segments"]] == [(40.0, "speaker_2"), (42.0, "speaker_1")]


def test_video_upload_is_awaited_until_active():
    states = iter(["PROCESSING", "PROCESSING", "ACTIVE"])

    def file(state):
        return types.SimpleNamespace(name="files/abc", state=types.SimpleNamespace(name=state))

    class Client:
        class files:
            @staticmethod
            def get(name):
                return file(next(states))

    gemini_service.time.sleep = lambda s: None
    assert gemini_service._wait_until_active(Client, file("PROCESSING")).state.name == "ACTIVE"
    try:
        gemini_service._wait_until_active(Client, file("FAILED"))
        raise AssertionError("a failed upload should raise")
    except RuntimeError as exc:
        assert "could not process" in str(exc)


def test_gemini_gets_a_video_and_long_gnani_lines_are_re_recorded_faster():
    work, audio_dir = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        long_mp3 = os.path.join(audio_dir, "long.mp3")  # 2.2 s of speech for a line whose slot is 1.5 s
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=2.2,volume=0.4",
                        "-c:a", "libmp3lame", long_mp3], check=True)
        audio = open(long_mp3, "rb").read()
        sent, seen = [], {}
        os.environ["GNANI_API_KEY"] = "test-key"
        os.environ.pop("TRANSCRIBE_ENGINE", None)
        tts_service.requests.post = lambda url, headers=None, json=None, timeout=None: (sent.append(json), FakeResponse(200, audio))[1]
        tts_service.generate_speech = REAL_GENERATE_SPEECH
        lines = [{"id": i, "start": 0.4 + i * 2.0, "end": 1.4 + i * 2.0, "text": f"source {i}"} for i in range(3)]
        stt_service.transcribe_audio = lambda *a, **k: lines

        def fake_adapt(source_lines, media, label, total):
            seen["media"] = media
            return gemini_service.build_script_from_lines(source_lines, {"characters": CHARACTERS, "lines": [
                {"id": l["id"], "speaker": CHARACTERS[l["id"]]["id"], "emotion": "neutral", "text": TELUGU[l["id"]]}
                for l in source_lines]}, total)

        gemini_service.adapt_dialogue = fake_adapt
        result = pipeline.process_video(INPUT, "telugu", "gnani", work)

        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,height", "-of", "csv=p=0", seen["media"]],
                               capture_output=True, text=True).stdout
        assert "video" in probe and "audio" in probe and "360" in probe, probe  # a 360p video with the voice track
        assert len(sent) == 6  # every line was recorded twice, once at normal speed and once faster
        assert [p["speed"] for p in sent[0::2]] == [1.0, 1.0, 1.0] and [p["speed"] for p in sent[1::2]] == [1.15, 1.15, 1.15]
        assert all(s["tts_speed"] == 1.15 and s["speedup"] <= video_service.MAX_SPEEDUP + 1e-6 for s in result["segments"])

        os.environ["GEMINI_VISION"] = "0"  # audio-only switch
        pipeline.process_video(INPUT, "telugu", "gnani", tempfile.mkdtemp())
        assert seen["media"].endswith("transcribe_input.wav")
    finally:
        os.environ.pop("GEMINI_VISION", None)
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(audio_dir, ignore_errors=True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nall {len(tests)} offline tests passed")
