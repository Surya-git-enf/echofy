# -> video_service.py
import json
import os
import subprocess
import tempfile
import requests
import base64
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
    Separate vocals using LALAL.AI API with proper asynchronous polling
    Returns (vocals_path, background_path)
    """
    api_key = os.getenv("LALAL_API_KEY")
    if not api_key:
        raise RuntimeError("LALAL_API_KEY is not set. Please set it in Render environment variables.")

    # Step 1: Upload file and get task ID
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    upload_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/octet-stream"
    }

    upload_files = {
        "file": ("audio.wav", audio_data, "audio/wav")
    }

    # Upload file
    upload_response = requests.post(
        "https://www.lalal.ai/api/v1/upload",
        headers=upload_headers,
        files=upload_files,
        timeout=30
    )
    upload_response.raise_for_status()
    upload_result = upload_response.json()

    if not upload_result.get("success"):
        raise RuntimeError(f"LALAL.AI upload failed: {upload_result.get('error')}")

    task_id = upload_result.get("result", {}).get("id")
    if not task_id:
        raise RuntimeError("LALAL.AI did not return task ID after upload")

    # Step 2: Poll for completion (max 2 minutes, check every 3 seconds)
    max_attempts = 40  # 40 * 3s = 120 seconds
    check_interval = 3  # seconds

    for attempt in range(max_attempts):
        try:
            # Check task status
            status_headers = {
                "Authorization": f"Bearer {api_key}"
            }

            status_params = {
                "id": task_id
            }

            status_response = requests.get(
                "https://www.lalal.ai/api/v1/check",
                headers=status_headers,
                params=status_params,
                timeout=10
            )
            status_response.raise_for_status()
            status_result = status_response.json()

            if not status_result.get("success"):
                raise RuntimeError(f"LALAL.AI status check failed: {status_result.get('error')}")

            task_result = status_result.get("result", {})
            task_status = task_result.get("state")

            # Check if completed
            if task_status == "completed":
                # Get download URLs
                result_files = task_result.get("result_files", {})
                vocals_url = result_files.get("vocal")
                background_url = result_files.get("accompaniment")

                if not vocals_url or not background_url:
                    raise RuntimeError("LALAL.AI did not return expected file URLs after completion")

                # Download separated files
                vocals_path = os.path.join(work_dir, "vocals_lalal.wav")
                background_path = os.path.join(work_dir, "background_lalal.wav")

                # Download vocals
                vocals_response = requests.get(vocals_url, timeout=30)
                vocals_response.raise_for_status()
                with open(vocals_path, "wb") as f:
                    f.write(vocals_response.content)

                # Download accompaniment (background)
                background_response = requests.get(background_url, timeout=30)
                background_response.raise_for_status()
                with open(background_path, "wb") as f:
                    f.write(background_response.content)

                return vocals_path, background_path

            elif task_status == "error":
                raise RuntimeError(f"LALAL.AI processing error: {task_result.get('error', 'Unknown error')}")

            # Still processing - wait and try again
            if attempt < max_attempts - 1:  # Don't sleep on last attempt
                time.sleep(check_interval)

        except requests.exceptions.RequestException as e:
            if attempt == max_attempts - 1:  # Last attempt
                raise RuntimeError(f"LALAL.AI API request failed after {max_attempts} attempts: {str(e)}")
            time.sleep(check_interval)  # Wait before retry

    # If we get here, polling timed out
    raise RuntimeError(f"LALAL.AI processing timed out after {max_attempts * check_interval} seconds")


def separate_vocals(audio_path: str, work_dir: str) -> tuple:
    """
    Separate vocals - tries LALAL.AI first for quality, falls back to FFmpeg
    Returns (vocals_path, background_path)
    """
    # Try LALAL.AI first for high-quality separation
    try:
        return separate_vocals_lalal(audio_path, work_dir)
    except Exception as e:
        # Log the error but fall back to FFmpeg
        print(f"[video_service] LALAL.AI separation failed: {str(e)}. Falling back to FFmpeg.")

        # FALLBACK: Original FFmpeg phase cancellation
        background_path = os.path.join(work_dir, "background_music.wav")
        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            "-i", audio_path,
            "-af", "pan=stereo|c0=0.5*c0+-0.5*c1|c1=-0.5*c0+0.5*c1",
            background_path,
        ]
        _run(cmd)
        return None, background_path


def mix_with_background_music(dubbed_track_path: str, background_music_path: str, output_path: str,
                               speech_windows: list, duck_volume: float = 0.3):
    """
    Exact volume automation, not approximate sidechain compression: since
    we already know precisely when the dubbed voice speaks (each TTS
    segment's start/end), the background track is set to `duck_volume`
    during those exact windows and left at its original (100%) level
    everywhere else — a real two-level switch, not a compressor's
    proportional response to signal level.

    speech_windows: list of (start_seconds, end_seconds) tuples.
    """
    if speech_windows:
        # One `volume` stage per window; each is only active (enable=...)
        # during its own [start, end] range — outside that range every
        # stage passes audio through unchanged, so untouched regions stay
        # at the background track's original 100% level.
        stages = [
            f"volume={duck_volume}:enable='between(t,{start},{end})'"
            for start, end in speech_windows
        ]
        bg_filter = ",".join(stages)
    else:
        bg_filter = "anull"  # no speech at all — leave background untouched

    filter_complex = f"[1:a]{bg_filter}[ducked_music];[0:a][ducked_music]amix=inputs=2:duration=longest:normalize=0[out]"

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