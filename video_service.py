# -> video_service.py
import json
import os
import subprocess
import tempfile

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
    instead of needing every segment as one giant simultaneous input list.
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


def separate_vocals(audio_path: str, work_dir: str) -> tuple:
    """
    Reduces center-panned vocals/dialogue using phase cancellation — pure
    FFmpeg audio filtering, NO ML model loaded. Uses only a few MB of RAM,
    fits comfortably under Render's 512MB free tier (unlike Demucs,
    MDX-Net, or even "lite" Spleeter, which all need 1GB+ for their model).

    Trade-off: meaningfully lower quality than any ML separator — some
    vocal bleed remains, and other center-panned elements (bass, kick
    drum) get slightly reduced too. Works best on professionally mixed
    stereo content (movies, anime, most video) where dialogue is
    center-panned — which is most of what you're dubbing.

    Returns (None, background_path) — there is no separate clean vocals
    file with this technique, so transcription should run on the
    ORIGINAL full audio instead (Gemini handles that fine).
    """
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
