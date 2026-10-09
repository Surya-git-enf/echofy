# -> video_service.py
import json
import os
import subprocess
import tempfile
import requests
import time
import uuid
import supabase_service

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


def separate_vocals_stemsplit(audio_path: str, work_dir: str) -> tuple:
    """
    Separate vocals using stemsplit.io's REST API. Returns (vocals_path, background_path).

    Replaces LALAL.AI (its multistem splitting is gated behind a paid plan
    our key doesn't have) and Spleeter (incompatible with Python 3.14 — no
    TensorFlow build exists for it, so it can never actually install here).

    stemsplit.io takes a URL to fetch the audio from rather than a direct
    upload, so we briefly upload the extracted audio to Supabase and hand
    it a signed URL.
    """
    api_key = os.getenv("STEMSPLIT_API_KEY")
    if not api_key:
        raise RuntimeError("STEMSPLIT_API_KEY is not set. Please set it in Render environment variables.")

    auth_headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Briefly stage the audio in Supabase so stemsplit.io has a URL to fetch.
    temp_path = f"temp/{uuid.uuid4().hex}.wav"
    supabase_service.upload_file(
        supabase_service.DUBBING_OUTPUTS_BUCKET, temp_path, audio_path, "audio/wav"
    )
    source_url = supabase_service.create_signed_url(
        supabase_service.DUBBING_OUTPUTS_BUCKET, temp_path, expires_in_seconds=3600
    )
    if not source_url:
        raise RuntimeError("Could not create a signed URL for the staged audio file.")

    create_response = requests.post(
        "https://stemsplit.io/api/v1/jobs",
        headers=auth_headers,
        json={
            "sourceUrl": source_url,
            "outputType": "BOTH",
            "quality": "BALANCED",
            "outputFormat": "WAV",
        },
        timeout=30,
    )
    if not create_response.ok:
        raise RuntimeError(f"stemsplit.io job creation failed ({create_response.status_code}): {create_response.text}")
    job = create_response.json()

    job_id = job.get("id")
    if not job_id:
        raise RuntimeError(f"stemsplit.io did not return a job id: {job}")

    max_attempts = 40
    check_interval = 3

    for attempt in range(max_attempts):
        status_response = requests.get(
            f"https://stemsplit.io/api/v1/jobs/{job_id}",
            headers=auth_headers,
            timeout=15,
        )
        if not status_response.ok:
            raise RuntimeError(f"stemsplit.io status check failed ({status_response.status_code}): {status_response.text}")
        status_data = status_response.json()
        status = status_data.get("status")

        if status == "COMPLETED":
            outputs = status_data.get("outputs", {})
            vocals_url = outputs.get("vocals", {}).get("url")
            background_url = outputs.get("instrumental", {}).get("url")

            if not vocals_url or not background_url:
                raise RuntimeError(f"stemsplit.io completed but outputs are missing: {outputs}")

            vocals_path = os.path.join(work_dir, "vocals_stemsplit.wav")
            background_path = os.path.join(work_dir, "background_stemsplit.wav")

            vocals_resp = requests.get(vocals_url, timeout=60)
            vocals_resp.raise_for_status()
            with open(vocals_path, "wb") as f:
                f.write(vocals_resp.content)

            background_resp = requests.get(background_url, timeout=60)
            background_resp.raise_for_status()
            with open(background_path, "wb") as f:
                f.write(background_resp.content)

            return vocals_path, background_path

        elif status == "FAILED":
            raise RuntimeError(f"stemsplit.io processing failed: {status_data.get('errorMessage')}")

        if attempt < max_attempts - 1:
            time.sleep(check_interval)

    raise RuntimeError(f"stemsplit.io processing timed out after {max_attempts * check_interval} seconds")


def separate_vocals(audio_path: str, work_dir: str) -> tuple:
    """
    Separate vocals using stemsplit.io (real AI separation, free tier +
    cheap pay-as-you-go). Falls back to a crude FFmpeg phase-cancellation
    trick only if the API itself is unreachable — that fallback is low
    quality and should rarely, if ever, actually trigger.
    Returns (vocals_path, background_path)
    """
    try:
        return separate_vocals_stemsplit(audio_path, work_dir)
    except Exception as e:
        print(f"[video_service] stemsplit.io separation failed: {str(e)}. Falling back to crude FFmpeg phase cancellation.")
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
