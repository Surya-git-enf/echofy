#!/usr/bin/env python3
"""
Run the real dubbing pipeline locally on every video in test/input/ and score the results.

    python scripts/run_local_dub.py                          # all inputs, default languages
    python scripts/run_local_dub.py --languages telugu hindi spanish
    python scripts/run_local_dub.py --inputs test/input/input.mp4 --engine fish

Needs the same environment variables as the server (GEMINI_API_KEY, SUPABASE_*, STEMSPLIT_API_KEY,
and FISH_AUDIO_API_KEY for the fish engine). Stem separation results are cached in .cache/stems so
re-running does not spend stemsplit.io minutes again. Results go to test/outputs/<input>__<language>/.

Optional per-input settings: put <input name>.json next to the video, e.g.
    {"expected_speakers": 4}
and the gate will require at least that many distinct characters with distinct voices.
"""
import argparse
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm")
DEFAULT_LANGUAGES = ["telugu", "hindi"]


def find_inputs(path: str) -> list:
    if os.path.isfile(path):
        return [path]
    return [os.path.join(path, f) for f in sorted(os.listdir(path)) if f.lower().endswith(VIDEO_EXTENSIONS)]


def main():
    parser = argparse.ArgumentParser(description="Run the dubbing pipeline locally and score it")
    parser.add_argument("--inputs", default=os.path.join(ROOT, "test", "input"))
    parser.add_argument("--languages", nargs="+", default=DEFAULT_LANGUAGES)
    parser.add_argument("--engine", default=os.getenv("DUB_ENGINE") or None)
    parser.add_argument("--out", default=os.path.join(ROOT, "test", "outputs"))
    parser.add_argument("--no-eval", action="store_true")
    parser.add_argument("--no-judge", action="store_true")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    engine = args.engine or ("fish" if os.getenv("FISH_AUDIO_API_KEY") else "edge")

    import pipeline
    import eval_dubbing

    stem_cache = os.path.join(ROOT, ".cache", "stems")
    inputs = find_inputs(args.inputs)
    if not inputs:
        print(f"No videos found in {args.inputs}")
        sys.exit(1)

    exit_code = 0
    for video in inputs:
        stem = os.path.splitext(os.path.basename(video))[0]
        meta_path = os.path.splitext(video)[0] + ".json"
        meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
        for language in args.languages:
            run_dir = os.path.join(args.out, f"{stem}__{language}")
            shutil.rmtree(run_dir, ignore_errors=True)
            print(f"\n>>> {os.path.basename(video)} -> {language} (engine={engine})")
            started = time.time()

            def on_progress(stage, progress):
                print(f"    [{progress:3d}%] {stage}")

            try:
                result = pipeline.process_video(video, language, engine, run_dir, on_progress=on_progress, stem_cache_dir=stem_cache)
            except Exception as exc:  # noqa: BLE001
                print(f"    PIPELINE FAILED: {exc}")
                exit_code = 1
                continue

            result["input_path"] = video
            result["expected_speakers"] = int(meta.get("expected_speakers", 1))
            result["elapsed_seconds"] = round(time.time() - started, 1)
            with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            keep = {"output.mp4", "run.json", "dubbed_track.wav", "background_applied.wav", "final_audio.wav"}
            for leftover in os.listdir(run_dir):
                if leftover not in keep:
                    os.remove(os.path.join(run_dir, leftover))

            if not args.no_eval:
                outcome = eval_dubbing.evaluate_run(run_dir, use_judge=not args.no_judge)
                eval_dubbing.print_result(outcome)
                if outcome["verdict"] == "FAIL":
                    exit_code = 1
                elif outcome["verdict"] == "PASS_UNJUDGED" and exit_code == 0:
                    exit_code = 2
    print(f"\nRESULT: {'PASS' if exit_code == 0 else 'PASS_UNJUDGED' if exit_code == 2 else 'FAIL'}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
