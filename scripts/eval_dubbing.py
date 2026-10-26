#!/usr/bin/env python3
"""
Dubbing quality gate.

Scores one dubbing run (a folder written by scripts/run_local_dub.py) against the targets in
test/reference_profile.json and prints PASS / FAIL with the numbers behind every check.

    python scripts/eval_dubbing.py test/outputs/input__telugu
    python scripts/eval_dubbing.py --all test/outputs

Exit code: 0 = PASS, 2 = PASS_UNJUDGED (every measurable check passed but the Gemini dialogue
judge could not run), 1 = FAIL.

What it can and cannot tell you: it measures levels, timing, background presence, voice
casting and script language. It cannot hear the audio, so the dialogue judge (an LLM reading
the original and dubbed lines) stands in for "does it sound natural", and a human listen is
still the final word.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_PATH = os.path.join(ROOT, "test", "reference_profile.json")
SR = 44100

# Unicode ranges of the script each language is normally written in.
SCRIPT_RANGES = {
    "telugu": [(0x0C00, 0x0C7F)], "hindi": [(0x0900, 0x097F)], "marathi": [(0x0900, 0x097F)],
    "nepali": [(0x0900, 0x097F)], "tamil": [(0x0B80, 0x0BFF)], "kannada": [(0x0C80, 0x0CFF)],
    "malayalam": [(0x0D00, 0x0D7F)], "bengali": [(0x0980, 0x09FF)], "gujarati": [(0x0A80, 0x0AFF)],
    "punjabi": [(0x0A00, 0x0A7F)], "urdu": [(0x0600, 0x06FF)], "arabic": [(0x0600, 0x06FF)],
    "persian": [(0x0600, 0x06FF)], "hebrew": [(0x0590, 0x05FF)], "thai": [(0x0E00, 0x0E7F)],
    "sinhala": [(0x0D80, 0x0DFF)], "russian": [(0x0400, 0x04FF)], "ukrainian": [(0x0400, 0x04FF)],
    "greek": [(0x0370, 0x03FF)], "korean": [(0xAC00, 0xD7AF)], "chinese": [(0x4E00, 0x9FFF)],
    "japanese": [(0x3040, 0x30FF), (0x4E00, 0x9FFF)],
}


def load_profile() -> dict:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)["gate"]


def _run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def probe(path: str) -> dict:
    result = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,channels,sample_rate",
                   "-of", "json", path])
    if result.returncode != 0:
        return {}
    return json.loads(result.stdout.decode())


def load_mono(path: str) -> np.ndarray:
    raw = _run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]).stdout
    return np.frombuffer(raw, dtype=np.float32)


def loudness(path: str):
    """(integrated LUFS, true peak dBTP) via ffmpeg ebur128."""
    text = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr.decode(errors="ignore")
    summary = text[text.rfind("Summary:"):] if "Summary:" in text else text
    lufs = re.search(r"\n\s+I:\s+(-?[\d.]+) LUFS", summary)
    peak = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+) dBFS", summary) or re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary)
    return (float(lufs.group(1)) if lufs else None, float(peak.group(1)) if peak else None)


def rms_db(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x.astype(np.float64)))) + 1e-9))


def mask_from_intervals(intervals, length: int) -> np.ndarray:
    mask = np.zeros(length, dtype=bool)
    for start, end in intervals:
        mask[max(0, int(start * SR)):min(length, int(end * SR))] = True
    return mask


def check(name, passed, value, detail=""):
    return {"name": name, "passed": bool(passed), "value": value, "detail": detail}


def script_match_fraction(texts, language_key):
    ranges = SCRIPT_RANGES.get(language_key)
    if not ranges:
        return None
    letters = [c for t in texts for c in t if c.isalpha()]
    if not letters:
        return 0.0
    hits = sum(1 for c in letters if any(lo <= ord(c) <= hi for lo, hi in ranges))
    return hits / len(letters)


def judge_dialogue(run: dict, min_score: float):
    """Ask Gemini to rate the adapted script. Returns (check dict or None, reason)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY is not set"
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None, "google-genai is not installed"

    lines = [
        f"[{s['start']:.1f}-{s['end']:.1f}s] {s['speaker']} ({s.get('emotion', 'neutral')}): "
        f"ORIGINAL: {s.get('original_text', '')} | DUBBED: {s['translated_text']}"
        for s in run["segments"]
    ]
    characters = "; ".join(
        f"{c['id']}={c.get('gender')}/{c.get('age_group')}/{c.get('voice_description', '')}" for c in run["characters"]
    )
    prompt = (
        f"You are a strict dubbing director reviewing a {run['language_label']} dub. Scene: {run.get('scene_summary', '')}\n"
        f"Characters: {characters}\n\nLines:\n" + "\n".join(lines) + "\n\n"
        "Score each from 1 to 10 (10 = indistinguishable from a professional local dub):\n"
        "- naturalness: would a native speaker say exactly this in this moment, with natural flow and no textbook phrasing?\n"
        "- slang_register: does slang, humour and attitude match the original, using real local idiom and normal code-mixing?\n"
        "- character_voice: does each character have a consistent, distinct way of speaking that fits their age and gender?\n"
        "- scene_fit: does the dialogue follow the scene's drama and fit the time slots (no rambling, no missing meaning)?\n"
        'Return JSON only: {"naturalness":n,"slang_register":n,"character_voice":n,"scene_fit":n,"worst_line":"quote the weakest line","fix":"one sentence on how to improve it"}'
    )
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=[prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        scores = json.loads(re.sub(r"^```(json)?|```$", "", response.text.strip(), flags=re.MULTILINE).strip())
        keys = ["naturalness", "slang_register", "character_voice", "scene_fit"]
        values = {k: float(scores[k]) for k in keys}
    except Exception as exc:  # noqa: BLE001
        return None, f"judge call failed: {exc}"
    lowest = min(values.values())
    return check("dialogue_judge", lowest >= min_score, values,
                 f"lowest {lowest:.0f} (need {min_score:.0f}). Worst line: {scores.get('worst_line', '')} | Fix: {scores.get('fix', '')}"), ""


def evaluate_run(run_dir: str, use_judge: bool = True) -> dict:
    gate = load_profile()
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
        run = json.load(f)
    output_path = os.path.join(run_dir, "output.mp4")
    checks = []

    # 1. the file plays and has both streams
    info = probe(output_path) if os.path.exists(output_path) else {}
    stream_types = [s.get("codec_type") for s in info.get("streams", [])]
    plays = "video" in stream_types and "audio" in stream_types
    checks.append(check("output_plays", plays, stream_types, "needs one video and one audio stream"))
    if not plays:
        return finish(run_dir, run, checks, None)

    # 2. duration
    out_duration = float(info["format"]["duration"])
    delta = abs(out_duration - run["total_duration"])
    checks.append(check("duration_matches_input", delta <= gate["duration_tolerance_seconds"], round(out_duration, 2),
                        f"input {run['total_duration']:.2f}s, off by {delta:.2f}s (limit {gate['duration_tolerance_seconds']}s)"))

    # 3. loudness and peak
    lufs, peak = loudness(output_path)
    checks.append(check("loudness", lufs is not None and gate["loudness_lufs_min"] <= lufs <= gate["loudness_lufs_max"], lufs,
                        f"want {gate['loudness_lufs_min']} to {gate['loudness_lufs_max']} LUFS (reference -18.6)"))
    checks.append(check("no_clipping", peak is not None and peak <= gate["true_peak_dbtp_max"], peak,
                        f"true peak must be <= {gate['true_peak_dbtp_max']} dBTP"))

    # placed intervals of each dubbed line
    segments = run["segments"]
    intervals = [(s["start"], s["start"] + s["dubbed_duration"]) for s in segments]
    bg = load_mono(os.path.join(run_dir, "background_applied.wav"))
    voice = load_mono(os.path.join(run_dir, "dubbed_track.wav")) * (10 ** (run.get("voice_gain_db", 0.0) / 20))
    n = min(len(bg), len(voice))
    bg, voice = bg[:n], voice[:n]
    speech = mask_from_intervals(intervals, n)
    gaps = ~speech

    # 4. the original background is really in the mix, and it came from real separation
    checks.append(check("vocals_separated", run["separation_method"] in ("stemsplit", "stemsplit-cache"), run["separation_method"],
                        "anything else means the FFmpeg fallback ran and the original dialogue bleeds under the dub; check STEMSPLIT_API_KEY, Supabase staging and the stemsplit.io response"))
    bg_all = rms_db(bg)
    checks.append(check("background_present", bg_all >= gate["background_min_rms_dbfs"], round(bg_all, 1),
                        f"background level in the mix must be >= {gate['background_min_rms_dbfs']} dBFS (silence = music was lost); stems: {run['separation_method']}"))
    gap_seconds, speech_seconds = gaps.sum() / SR, speech.sum() / SR
    if gap_seconds >= 0.5 and speech_seconds >= 0.5:
        bg_gap, bg_speech = rms_db(bg[gaps]), rms_db(bg[speech])
        checks.append(check("background_audible_in_gaps", bg_gap >= gate["background_gap_min_rms_dbfs"], round(bg_gap, 1),
                            f"background between lines must be >= {gate['background_gap_min_rms_dbfs']} dBFS"))
        checks.append(check("background_ducks_under_speech", bg_gap - bg_speech >= gate["background_swell_min_db"], round(bg_gap - bg_speech, 1),
                            f"music should swell back by >= {gate['background_swell_min_db']} dB in the gaps"))
        balance = rms_db(voice[speech]) - bg_speech
        checks.append(check("voice_over_background", gate["voice_over_background_min_db"] <= balance <= gate["voice_over_background_max_db"],
                            round(balance, 1), f"dialogue should sit {gate['voice_over_background_min_db']} to {gate['voice_over_background_max_db']} dB above the music"))

    # 5. every scripted line was voiced, and roughly as long as the original
    orig_speech = sum(s["end"] - s["start"] for s in segments)
    dub_speech = sum(s["dubbed_duration"] for s in segments)
    ratio = dub_speech / orig_speech if orig_speech else 0
    checks.append(check("speech_coverage", all(s["dubbed_duration"] > 0.05 for s in segments)
                        and gate["dubbed_to_original_speech_ratio_min"] <= ratio <= gate["dubbed_to_original_speech_ratio_max"],
                        round(ratio, 2), f"dubbed speech / original speech must be {gate['dubbed_to_original_speech_ratio_min']} to {gate['dubbed_to_original_speech_ratio_max']}"))

    # 6. timing
    fits = [s["dubbed_duration"] <= s["slot_seconds"] + gate["fit_overflow_seconds"] for s in segments]
    fit_fraction = sum(fits) / len(fits)
    worst_speedup = max(s["speedup"] for s in segments)
    checks.append(check("lines_fit_their_slots", fit_fraction >= gate["fit_fraction_min"] and worst_speedup <= gate["max_speedup"],
                        {"fit_fraction": round(fit_fraction, 2), "max_speedup": round(worst_speedup, 2)},
                        f"need >= {gate['fit_fraction_min']:.0%} of lines inside their slot and speed-up <= {gate['max_speedup']}x. Too-long lines: "
                        + ", ".join(str(s["index"]) for s, ok in zip(segments, fits) if not ok)[:80]))
    overlaps = []
    for speaker in {s["speaker"] for s in segments}:
        own = sorted((s for s in segments if s["speaker"] == speaker), key=lambda s: s["start"])
        for a, b in zip(own, own[1:]):
            overlap = (a["start"] + a["dubbed_duration"]) - b["start"]
            if overlap > gate["same_speaker_overlap_seconds"]:
                overlaps.append((speaker, round(overlap, 2)))
    checks.append(check("no_same_speaker_overlap", not overlaps, overlaps, "a character must never talk over themselves"))

    # 7. casting
    speakers_used = sorted({s["speaker"] for s in segments})
    voices_used = {sp: {s["voice_id"] for s in segments if s["speaker"] == sp} for sp in speakers_used}
    distinct = len({next(iter(v)) for v in voices_used.values()})
    expected = max(run.get("expected_speakers", 1), 1)
    one_voice_each = all(len(v) == 1 for v in voices_used.values())
    checks.append(check("distinct_voice_per_character", one_voice_each and distinct == len(speakers_used) and len(speakers_used) >= expected,
                        {"speakers": len(speakers_used), "distinct_voices": distinct, "expected_speakers": expected},
                        "every character needs one stable voice, different from every other character"))

    # 8. language and translation
    lang_key = run["target_language"].strip().lower()
    texts = [s["translated_text"] for s in segments]
    frac = script_match_fraction(texts, lang_key)
    if frac is not None:
        checks.append(check("script_matches_language", frac >= gate["script_match_min"], round(frac, 2),
                            f">= {gate['script_match_min']:.0%} of letters must be in the {run['language_label']} script"))
    copied = [s["index"] for s in segments if s.get("original_text") and s["original_text"].strip().lower() == s["translated_text"].strip().lower()]
    src_lang = (run.get("detected_source_language") or "").strip().lower()
    if src_lang != run["language_label"].lower():
        checks.append(check("lines_actually_translated", len(copied) <= len(segments) * 0.2, copied, "lines identical to the source text"))

    # 9. dialogue quality (LLM judge)
    judge_note = ""
    if use_judge:
        judged, judge_note = judge_dialogue(run, gate["judge_min_score"])
        if judged:
            checks.append(judged)
    return finish(run_dir, run, checks, judge_note if use_judge else "judge disabled")


def finish(run_dir, run, checks, judge_note):
    failed = [c for c in checks if not c["passed"]]
    judged = any(c["name"] == "dialogue_judge" for c in checks)
    if failed:
        verdict = "FAIL"
    elif judged:
        verdict = "PASS"
    else:
        verdict = "PASS_UNJUDGED"
    result = {"run": os.path.basename(run_dir), "verdict": verdict,
              "score": round(sum(c["passed"] for c in checks) / max(len(checks), 1), 2),
              "checks": checks, "judge_note": judge_note}
    with open(os.path.join(run_dir, "eval.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    return result


def print_result(result: dict):
    print(f"\n=== {result['run']}: {result['verdict']}  (score {result['score']}) ===")
    for c in result["checks"]:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['value']}  - {c['detail']}")
    if result["verdict"] == "PASS_UNJUDGED":
        print(f"  (dialogue judge did not run: {result['judge_note']})")


def main():
    parser = argparse.ArgumentParser(description="Dubbing quality gate")
    parser.add_argument("path", help="a run folder, or with --all a folder of run folders")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--no-judge", action="store_true")
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except ImportError:
        pass
    dirs = ([os.path.join(args.path, d) for d in sorted(os.listdir(args.path))] if args.all else [args.path])
    dirs = [d for d in dirs if os.path.exists(os.path.join(d, "run.json"))]
    if not dirs:
        print("No run folders with run.json found.")
        sys.exit(1)
    results = [evaluate_run(d, use_judge=not args.no_judge) for d in dirs]
    for r in results:
        print_result(r)
    verdicts = {r["verdict"] for r in results}
    code = 1 if "FAIL" in verdicts else (2 if "PASS_UNJUDGED" in verdicts else 0)
    print(f"\nGATE: {'PASS' if code == 0 else 'PASS_UNJUDGED' if code == 2 else 'FAIL'} ({len(results)} run(s))")
    sys.exit(code)


if __name__ == "__main__":
    main()
