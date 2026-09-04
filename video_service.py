"""
All audio/video manipulation goes through ffmpeg directly (subprocess),
so the only system dependency is the ffmpeg binary — no extra Python
audio libraries required. Keeps the MVP lightweight for free-tier hosting.
"""
import json
import subprocess


class FFmpegError(RuntimeError):
    pass


def _run(cmd: list):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.decode(errors="ignore")[-2000:])
    return result


def get_duration_seconds(media_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", media_path,
    ]
    result = _run(cmd)
    data = json.loads(result.stdout.decode())
    return float(data["format"]["duration"])


def extract_audio(video_path: str, audio_out_path: str):
    """Extract mono 16kHz WAV — good format for STT/translation input."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        audio_out_path,
    ]
    _run(cmd)


def build_dubbed_track(segment_files: list, total_duration_seconds: float, output_path: str):
    """
    segment_files: list of {"start": float_seconds, "path": str} — one TTS
    clip per transcript segment, each already generated as an audio file.
    Places every clip at its correct start offset and mixes them into a
    single track the length of the original video.
    """
    if not segment_files:
        # Nothing to dub — emit silence for the full duration so the merge step still works.
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(total_duration_seconds),
            output_path,
        ]
        _run(cmd)
        return

    inputs = []
    filter_parts = []
    for i, seg in enumerate(segment_files):
        inputs += ["-i", seg["path"]]
        delay_ms = max(0, int(seg["start"] * 1000))
        filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}]")

    mix_inputs = "".join(f"[a{i}]" for i in range(len(segment_files)))
    filter_complex = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={len(segment_files)}:duration=longest:normalize=0[out]"

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-t", str(total_duration_seconds),
        output_path,
    ]
    _run(cmd)


def merge_audio_into_video(video_path: str, dubbed_audio_path: str, output_path: str):
    """Replace the original audio track with the dubbed track, keep original video stream."""
    cmd = [
        "ffmpeg", "-y",
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

