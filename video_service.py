# -> video_service.py
import json
import os
import subprocess
import tempfile
import requests
import time

BATCH_SIZE = 25  # max simultaneous ffmpeg inputs per mix pass — keeps command size/memory sane


class FFmpegError(RuntimeError):
    pass


def _run(cmd: list):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.decode(errors="ignore")[-2000:])
    return result


def validate_video(media_path: str):
    """
    Fast sanity check (ffprobe only, no decoding) run immediately after
    download — fails fast with a clear message if the file is corrupted
    or incomplete (most commonly: the upload got cut off partway through),
    instead of surfacing a confusing raw ffmpeg error deep in the pipeline.
    """
    try:
        get_duration_seconds(media_path)
    except FFmpegError as exc:
        raise FFmpegError(
            "The uploaded video file appears corrupted or incomplete "
            "(this usually means the upload was cut off partway through). "
            f"Try re-uploading the file. Raw ffprobe error: {exc}"
        ) from exc


def get_duration_seconds(media_path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", media_path]
    result = _run(cmd)
    data = json.loads(result.stdout.decode())
    return float(data["format"]["duration"])


def extract_audio(video_path: str, audio_out_path: str):
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        audio_out_path,
    ]
    _run(cmd)


def _mix_batch(segment_batch: list, total_duration_seconds: float, output_path: str, base_track_path: str | None = None):
    """
    Mix one batch of segments (each with its own start-offset delay) into a
    single track. If base_track_path is given, it's mixed in as an
    additional input — this is how batches get combined incrementally
    instead of needing every segment as a simultaneous ffmpeg input at once.
    """
    inputs = []
    filter_parts = []
    input_index = 0

    if base_track_path:
        inputs += ["-i", base_track_path]
        filter_parts.append(f"[{input_index}:a]anull[a{input_index}]")
        input_index += 1

    for seg in segment_batch:
        inputs += ["-i", seg["path"]]
        delay_ms = max(0, int(seg["start"] * 1000))
        filter_parts.append(f"[{input_index}:a]adelay={delay_ms}|{delay_ms}[a{input_index}]")
        input_index += 1

    mix_inputs = "".join(f"[a{i}]" for i in range(input_index))
    filter_complex = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={input_index}:duration=longest:normalize=0[out]"

    cmd = [
        "ffmpeg", "-y", "-hide_banner", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-t", str(total_duration_seconds),
        output_path,
    ]
    _run(cmd)


def build_dubbed_track(segment_files: list, total_duration_seconds: float, output_path: str):
    """
    Scales to any number of segments (needed for long videos — a 20 min
    video can produce hundreds of segments) by mixing in batches of
    BATCH_SIZE, folding each batch's result into a running combined track,
    instead of passing every segment as a simultaneous ffmpeg input at once.
    """
    if not segment_files:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(total_duration_seconds),
            output_path,
        ]
        _run(cmd)
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        running_track = None

        for batch_start in range(0, len(segment_files), BATCH_SIZE):
            batch = segment_files[batch_start:batch_start + BATCH_SIZE]
            batch_output = os.path.join(tmp_dir, f"batch_{batch_start}.wav")

            _mix_batch(batch, total_duration_seconds, batch_output, base_track_path=running_track)
            running_track = batch_output

        # copy the final running track to the requested output path
        _run(["ffmpeg", "-y", "-hide_banner", "-i", running_track, output_path])


def separate_vocals_lalal(audio_path: str, work_dir: str) -> tuple:
    """
    Separate vocals using LALAL.AI's /split/multistem/ endpoint.
    Returns (vocals_path, background_path).

    NOTE: multistem splitting is a paid-tier-only feature on LALAL.AI — a
    free/basic license key will get a 400 "Premium license required" error
    here every time. That's expected unless/until the account is upgraded;
    separate_vocals() below falls back to self-hosted Spleeter in that case.
    """
    license_key = os.getenv("LALAL_API_KEY")
    if not license_key:
        raise RuntimeError("LALAL_API_KEY is not set. Please set it in Render environment variables.")

    auth_headers = {"X-License-Key": license_key}

    filename = os.path.basename(audio_path)
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    upload_response = requests.post(
        "https://www.lalal.ai/api/v1/upload/",
        headers={
            **auth_headers,
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "application/octet-stream",
        },
        data=audio_data,
        timeout=60,
    )
    if not upload_response.ok:
        raise RuntimeError(f"LALAL.AI upload failed ({upload_response.status_code}): {upload_response.text}")
    upload_result = upload_response.json()

    source_id = upload_result.get("id")
    if not source_id:
        raise RuntimeError(f"LALAL.AI upload did not return a source id: {upload_result}")

    split_response = requests.post(
        "https://www.lalal.ai/api/v1/split/multistem/",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={
            "source_id": source_id,
            "presets": {
                "splitter": "auto",
                "dereverb_enabled": False,
                "encoder_format": None,
                "stem_list": ["vocals"],
                "extraction_level": "deep_extraction",
            },
            "idempotency_key": None,
        },
        timeout=30,
    )
    if not split_response.ok:
        raise RuntimeError(f"LALAL.AI split failed ({split_response.status_code}): {split_response.text}")
    split_result = split_response.json()

    task_id = split_result.get("task_id")
    if not task_id:
        raise RuntimeError(f"LALAL.AI split did not return a task id: {split_result}")

    max_attempts = 40
    check_interval = 3

    for attempt in range(max_attempts):
        try:
            check_response = requests.post(
                "https://www.lalal.ai/api/v1/check/",
                headers={**auth_headers, "Content-Type": "application/json"},
                json={"task_ids": [task_id]},
                timeout=10,
            )
            if not check_response.ok:
                raise RuntimeError(f"LALAL.AI check failed ({check_response.status_code}): {check_response.text}")
            check_result = check_response.json()

            task_info = check_result.get("result", {}).get(task_id, {})
            status = task_info.get("status")

            if status == "success":
                tracks = task_info.get("result", {}).get("tracks", [])
                vocals_url = next((t["url"] for t in tracks if t.get("label") == "vocals"), None)
                background_url = next((t["url"] for t in tracks if t.get("label") == "no_multistem"), None)

                if not vocals_url or not background_url:
                    raise RuntimeError(f"LALAL.AI completed but expected tracks are missing: {tracks}")

                vocals_path = os.path.join(work_dir, "vocals_lalal.wav")
                background_path = os.path.join(work_dir, "background_lalal.wav")

                vocals_resp = requests.get(vocals_url, timeout=60)
                vocals_resp.raise_for_status()
                with open(vocals_path, "wb") as f:
                    f.write(vocals_resp.content)

                background_resp = requests.get(background_url, timeout=60)
                background_resp.raise_for_status()
                with open(background_path, "wb") as f:
                    f.write(background_resp.content)

                return vocals_path, background_path

            elif status in ("error", "server_error"):
                raise RuntimeError(f"LALAL.AI processing error: {task_info.get('error')}")

            # still processing - wait and try again
            if attempt < max_attempts - 1:  # Don't sleep on last attempt
                time.sleep(check_interval)

        except requests.exceptions.RequestException as e:
            if attempt == max_attempts - 1:  # Last attempt
                raise RuntimeError(f"LALAL.AI API request failed after {max_attempts} attempts: {str(e)}")
            time.sleep(check_interval)  # Wait before retry

    # If we get here, polling timed out
    raise RuntimeError(f"LALAL.AI processing timed out after {max_attempts * check_interval} seconds")


def separate_vocals_spleeter(audio_path: str, work_dir: str) -> tuple:
    """
    Open-source vocal/background separation using Spleeter (2stems model),
    run locally — no external API, no premium tier required. Used as the
    fallback when LALAL.AI is unavailable or gated behind a paid plan.

    Import is done lazily (inside the function) so the whole app doesn't
    fail to start if Spleeter/TensorFlow aren't installed in an environment
    where preserve_background_music is never used.
    """
    from spleeter.separator import Separator

    separator = Separator("spleeter:2stems")
    separator.separate_to_file(audio_path, work_dir, filename_format="{instrument}.wav")

    # Spleeter names outputs "vocals.wav" and "accompaniment.wav" inside a
    # subfolder named after the input file (minus extension).
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_dir = os.path.join(work_dir, base_name)

    vocals_path = os.path.join(output_dir, "vocals.wav")
    background_path = os.path.join(output_dir, "accompaniment.wav")

    if not os.path.exists(vocals_path) or not os.path.exists(background_path):
        raise RuntimeError(f"Spleeter did not produce expected output files in {output_dir}")

    return vocals_path, background_path


def separate_vocals(audio_path: str, work_dir: str) -> tuple:
    """
    Separate vocals — tries LALAL.AI first (if your account has access to
    it), falls back to self-hosted Spleeter (open-source, no API cost, no
    premium-tier requirement) if LALAL fails for any reason.
    Returns (vocals_path, background_path)
    """
    try:
        return separate_vocals_lalal(audio_path, work_dir)
    except Exception as e:
        print(f"[video_service] LALAL.AI separation failed: {str(e)}. Falling back to Spleeter.")
        return separate_vocals_spleeter(audio_path, work_dir)


def mix_with_background_music(dubbed_track_path: str, background_music_path: str, output_path: str,
                               speech_windows: list = None, duck_db: float = 7):
    """
    True sidechain ducking: the background track is automatically
    attenuated whenever the dubbed dialogue track actually has signal,
    and springs back to full volume the instant dialogue goes silent —
    reacting to the real audio, not a fixed list of start/end windows.

    Also applies a final loudness normalization pass to -14 LUFS (the
    standard streaming/broadcast loudness target) so the mixed result
    has a consistent, professional level.

    `speech_windows` is accepted but no longer used — sidechain
    compression reacts to the real signal, so explicit windows aren't
    needed. Kept as a parameter so existing callers don't need to change.
    """
    threshold = 10 ** (-duck_db / 20)  # convert dB target to a linear threshold

    filter_complex = (
        f"[1:a][0:a]sidechaincompress=threshold={threshold}:ratio=8:attack=5:release=300[ducked_bg];"
        f"[0:a][ducked_bg]amix=inputs=2:duration=longest:normalize=0,"
        f"loudnorm=I=-14:TP=-1.5:LRA=11[out]"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", dubbed_track_path,
        "-i", background_music_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        output_path,
    ]
    _run(cmd)


def merge_audio_into_video(video_path: str, dubbed_audio_path: str, output_path: str):
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", video_path,
        "-i", dubbed_audio_path,
        "-c:v", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    _run(cmd)
