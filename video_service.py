# -> video_service.py
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import requests
import time
import uuid
import supabase_service

BATCH_SIZE = 25  # max simultaneous ffmpeg inputs per mix pass — keeps command size/memory sane
LOUDNESS_TARGET_LUFS = -17.0  # final mix target; the reference dub measures about -18.6 LUFS
MAX_SPEEDUP = 1.35  # a dubbed line is sped up by at most this much to fit its time slot
BACKGROUND_GAIN_DB = -3.0  # background level before ducking; ducking then lowers it further under speech
VOICE_TARGET_LUFS = -19.0  # dubbed dialogue is levelled to this before mixing so ducking behaves the same for every TTS engine


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


def has_audio_stream(media_path: str) -> bool:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "json", media_path]
    return bool(json.loads(_run(cmd).stdout.decode()).get("streams"))


def extract_audio(video_path: str, audio_out_path: str, sample_rate: int = 16000, channels: int = 1):
    if not has_audio_stream(video_path):
        raise FFmpegError("The uploaded video has no audio track, so there is nothing to dub.")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-i", video_path,
        "-vn", "-ac", str(channels), "-ar", str(sample_rate), "-acodec", "pcm_s16le",
        audio_out_path,
    ]
    _run(cmd)


def prepare_segment(src_path: str, dst_path: str, max_duration: float = None, pitch_semitones: float = 0.0) -> dict:
    """
    Make one TTS clip ready for the timeline: trim leading/trailing silence, shift pitch
    (only for engines that cannot vary the voice themselves), speed it up slightly if it is
    longer than its time slot, and convert to 44.1 kHz stereo. Returns timing facts for the gate.
    """
    trimmed = dst_path + ".trim.wav"
    trim_filter = (
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse"
    )
    _run(["ffmpeg", "-y", "-hide_banner", "-i", src_path, "-af", trim_filter, trimmed])
    raw_duration = get_duration_seconds(trimmed)
    if raw_duration < 0.05:
        raise FFmpegError("The voice engine returned silence for this line.")

    speedup = 1.0
    if max_duration and raw_duration > max_duration:
        speedup = min(raw_duration / max_duration, MAX_SPEEDUP)

    if abs(pitch_semitones) > 0.01:
        factor = 2 ** (pitch_semitones / 12)
        # asetrate shifts pitch and speed together; atempo undoes the speed change.
        shape = f"aresample=44100,asetrate={44100 * factor:.2f},aresample=44100,atempo={speedup / factor:.5f}"
    elif speedup > 1.001:
        shape = f"atempo={speedup:.5f}"
    else:
        shape = "anull"
    _run([
        "ffmpeg", "-y", "-hide_banner", "-i", trimmed,
        "-af", f"{shape},aformat=sample_fmts=s16:sample_rates=44100:channel_layouts=stereo",
        dst_path,
    ])
    os.remove(trimmed)
    return {"raw_duration": raw_duration, "speedup": speedup, "duration": get_duration_seconds(dst_path)}


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

        # Pad with silence to the full video length. Without this the track ends at the last
        # line and the rest of the video loses its audio (and -shortest would cut the video).
        _run(["ffmpeg", "-y", "-hide_banner", "-i", running_track, "-af", "apad",
              "-t", str(total_duration_seconds), output_path])


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


def _sha1_of_file(path: str) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _channel_count(path: str) -> int:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels", "-of", "json", path]
    return int(json.loads(_run(cmd).stdout.decode())["streams"][0]["channels"])


def _mean_volume_db(path: str) -> float:
    """Average level in dB (-120 for digital silence). Peaks alone say nothing about whether music survived."""
    result = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    match = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", result.stderr.decode(errors="ignore"))
    if not match or match.group(1) == "-inf":
        return -120.0
    return float(match.group(1))


def _ffmpeg_background(audio_path: str, work_dir: str) -> tuple:
    """
    Last-resort background track when the separation API is unavailable. Never returns
    silence: if centre-channel cancellation leaves nothing (mono or fake-stereo source),
    the original audio is used quietly underneath instead, so the scene keeps its music.
    """
    background_path = os.path.join(work_dir, "background_music.wav")
    if _channel_count(audio_path) == 2:
        _run(["ffmpeg", "-y", "-hide_banner", "-i", audio_path,
              "-af", "pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0", background_path])
        # Keep the cancelled result only if real content survived: loud enough in absolute
        # terms and not wildly quieter than the source (a few stray peaks are not music).
        remaining = _mean_volume_db(background_path)
        if remaining > -45 and remaining > _mean_volume_db(audio_path) - 25:
            return background_path, "ffmpeg-center-cancel"
    _run(["ffmpeg", "-y", "-hide_banner", "-i", audio_path, "-af", "volume=-9dB", background_path])
    return background_path, "ffmpeg-attenuated-original"


def separate_vocals(audio_path: str, work_dir: str, cache_dir: str = None) -> tuple:
    """
    Split the soundtrack into vocals and background. Returns (vocals_path, background_path, method).

    Uses stemsplit.io (real AI separation). Results can be cached by audio hash in cache_dir
    (or STEM_CACHE_DIR) so repeated test runs do not use up stemsplit minutes. If the API is
    unavailable a basic FFmpeg fallback still produces a background track (vocals_path is None).
    """
    cache_dir = cache_dir or os.getenv("STEM_CACHE_DIR")
    key = _sha1_of_file(audio_path) if cache_dir else None
    vocals_out = os.path.join(work_dir, "vocals.wav")
    background_out = os.path.join(work_dir, "background.wav")

    if cache_dir:
        cached_vocals = os.path.join(cache_dir, f"{key}.vocals.wav")
        cached_background = os.path.join(cache_dir, f"{key}.background.wav")
        if os.path.exists(cached_vocals) and os.path.exists(cached_background):
            shutil.copy(cached_vocals, vocals_out)
            shutil.copy(cached_background, background_out)
            return vocals_out, background_out, "stemsplit-cache"

    try:
        vocals_path, background_path = separate_vocals_stemsplit(audio_path, work_dir)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            shutil.copy(vocals_path, cached_vocals)
            shutil.copy(background_path, cached_background)
        return vocals_path, background_path, "stemsplit"
    except Exception as e:  # noqa: BLE001
        print(f"[video_service] stemsplit.io separation failed: {e}. Using the FFmpeg fallback background.")
        background_path, method = _ffmpeg_background(audio_path, work_dir)
        return None, background_path, method


def measure_lufs(path: str) -> float:
    """Integrated loudness in LUFS (-70 if the file is effectively silent)."""
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    matches = re.findall(r"\n\s+I:\s+(-?[\d.]+|-inf) LUFS", result.stderr.decode(errors="ignore"))
    if not matches or matches[-1] == "-inf":
        return -70.0
    return float(matches[-1])


def mix_with_background_music(dubbed_track_path: str, background_music_path: str, output_path: str,
                              bg_gain_db: float = BACKGROUND_GAIN_DB, bg_applied_path: str = None):
    """
    Studio-style mix: the original background (music/effects) sits under the dubbed
    dialogue, ducks automatically while anyone speaks (sidechain compression driven by the
    dubbed voices themselves) and swells back in the gaps. The result is loudness-normalised.

    If bg_applied_path is given, the background exactly as mixed (after gain and ducking) is
    also written there so the quality gate can measure it. Returns the gain (dB) applied to the
    dubbed dialogue, which the gate needs to compare dialogue and background levels.
    """
    voice_gain_db = max(-15.0, min(20.0, VOICE_TARGET_LUFS - measure_lufs(dubbed_track_path)))
    chains = [
        f"[1:a]aresample=44100,aformat=channel_layouts=stereo,volume={bg_gain_db}dB[bg]",
        f"[0:a]aresample=44100,aformat=channel_layouts=stereo,volume={voice_gain_db:.2f}dB,asplit=2[voice_sc][voice_mix]",
        "[bg][voice_sc]sidechaincompress=threshold=0.03:ratio=3:attack=20:release=500:makeup=1[bgd]",
    ]
    maps = ["-map", "[out]"]
    if bg_applied_path:
        chains.append("[bgd]asplit=2[bgd_mix][bgd_out]")
        mix_bg = "[bgd_mix]"
    else:
        mix_bg = "[bgd]"
    chains.append(
        f"[voice_mix]{mix_bg}amix=inputs=2:duration=first:normalize=0,"
        f"loudnorm=I={LOUDNESS_TARGET_LUFS}:TP=-1.5:LRA=11[out]"
    )

    cmd = ["ffmpeg", "-y", "-hide_banner", "-i", dubbed_track_path, "-i", background_music_path,
           "-filter_complex", ";".join(chains), *maps, output_path]
    if bg_applied_path:
        cmd += ["-map", "[bgd_out]", bg_applied_path]
    _run(cmd)
    return voice_gain_db


def merge_audio_into_video(video_path: str, dubbed_audio_path: str, output_path: str):
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", video_path,
        "-i", dubbed_audio_path,
        "-c:v", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    _run(cmd)
