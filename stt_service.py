# -> stt_service.py
"""
Speech-to-text with Gnani Vachana (model prisma-v3.0).

The synchronous endpoint takes at most 30 seconds of audio and returns text only: no
timestamps and no speaker labels. So this module finds the spoken stretches itself
(ffmpeg silence detection), sends each one to Gnani, and keeps the stretch's own start and
end as the line's timing. Gemini later decides who is speaking and writes the dub.

Docs: https://docs.gnani.ai/vachana/STT/speech-to-text
"""
import os
import re
import time

import requests

import video_service

GNANI_STT_URL = "https://api.vachana.ai/stt/v3"
STT_MODEL = "prisma-v3.0"
# prisma-v3.0 accepts up to four comma-separated language codes. Override with GNANI_STT_LANGUAGE.
DEFAULT_LANGUAGES = "en-IN,hi-IN,te-IN,ta-IN"

API_LIMIT_SECONDS = 30.0   # Gnani rejects longer audio
MAX_CHUNK_SECONDS = 25.0   # hard cap per request, with margin
TARGET_LINE_SECONDS = 12.0  # stretches longer than this are split again at quieter points
MIN_SPEECH_SECONDS = 0.3
PAD_SECONDS = 0.12
MAX_RETRIES = 4

# (noise floor in dB, minimum pause in seconds), strictest first. Long stretches are retried looser.
SILENCE_PASSES = [(-38, 0.25), (-32, 0.15), (-26, 0.08)]

_SIL_START = re.compile(r"silence_start: (-?[0-9.]+)")
_SIL_END = re.compile(r"silence_end: (-?[0-9.]+)")


def _silences(path: str, start: float, end: float, noise_db: int, min_pause: float) -> list:
    """Silent spans inside [start, end] as absolute (begin, finish) seconds."""
    result = video_service._run([
        "ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_pause}", "-f", "null", "-",
    ])
    log = result.stderr.decode("utf-8", "ignore")
    spans, open_at = [], None
    for line in log.splitlines():
        m = _SIL_START.search(line)
        if m:
            open_at = max(0.0, float(m.group(1)))
            continue
        m = _SIL_END.search(line)
        if m and open_at is not None:
            spans.append((start + open_at, start + float(m.group(1))))
            open_at = None
    if open_at is not None:  # silence ran to the end of the range
        spans.append((start + open_at, end))
    return spans


def _speech_between(silences: list, start: float, end: float) -> list:
    """The gaps between silent spans, i.e. the spoken stretches."""
    speech, cursor = [], start
    for s_begin, s_end in sorted(silences):
        if s_begin - cursor >= MIN_SPEECH_SECONDS:
            speech.append((cursor, s_begin))
        cursor = max(cursor, s_end)
    if end - cursor >= MIN_SPEECH_SECONDS:
        speech.append((cursor, end))
    return speech


def _hard_split(start: float, end: float) -> list:
    pieces = max(1, int((end - start) // MAX_CHUNK_SECONDS) + (1 if (end - start) % MAX_CHUNK_SECONDS else 0))
    step = (end - start) / pieces
    return [(start + i * step, start + (i + 1) * step) for i in range(pieces)]


def _refine(path: str, start: float, end: float, pass_index: int) -> list:
    """Split a long stretch at its pauses, trying looser silence settings until it is short enough."""
    if end - start <= TARGET_LINE_SECONDS:
        return [(start, end)]
    if pass_index >= len(SILENCE_PASSES):
        return _hard_split(start, end) if end - start > MAX_CHUNK_SECONDS else [(start, end)]
    noise_db, min_pause = SILENCE_PASSES[pass_index]
    parts = _speech_between(_silences(path, start, end, noise_db, min_pause), start, end)
    if len(parts) <= 1:  # nothing to split at with these settings
        return _refine(path, start, end, pass_index + 1)
    out = []
    for a, b in parts:
        out.extend(_refine(path, a, b, pass_index + 1))
    return out


def find_speech_intervals(path: str, total_duration: float) -> list:
    """Spoken stretches of the audio as (start, end) seconds, each short enough for one Gnani request."""
    noise_db, min_pause = SILENCE_PASSES[0]
    first = _speech_between(_silences(path, 0.0, total_duration, noise_db, min_pause), 0.0, total_duration)
    out = []
    for a, b in first:
        out.extend(_refine(path, a, b, 1))
    return out


def transcribe_chunk(wav_path: str, language_code: str) -> str:
    """One Gnani request. Returns the transcript, or an empty string when there is no speech."""
    api_key = os.getenv("GNANI_API_KEY")
    if not api_key:
        raise RuntimeError("GNANI_API_KEY is not set. Transcription with Gnani cannot run without it.")

    headers = {"X-API-Key-ID": api_key}
    data = {"language_code": language_code, "model": STT_MODEL}
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(wav_path, "rb") as fh:
                resp = requests.post(GNANI_STT_URL, headers=headers, data=data, files={"audio_file": fh}, timeout=90)
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            time.sleep(2 ** attempt)
            continue

        if resp.status_code in (401, 403):
            raise RuntimeError(f"Gnani STT rejected the request ({resp.status_code}): check GNANI_API_KEY and credits. {resp.text[:300]}")
        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = f"status {resp.status_code}: {resp.text[:200]}"
            time.sleep(2 ** attempt)
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"Gnani STT failed ({resp.status_code}): {resp.text[:300]}")

        body = resp.json()
        if not body.get("success", True):
            raise RuntimeError(f"Gnani STT error: {body.get('error')}")
        return str(body.get("transcript") or "").strip()

    raise RuntimeError(f"Gnani STT failed after {MAX_RETRIES} attempts: {last_error}")


def transcribe_audio(audio_path: str, total_duration: float, work_dir: str, language_code: str = None,
                     on_chunk=None) -> list:
    """
    Transcribe a whole audio file. Returns lines [{"id", "start", "end", "text"}] in time order.
    Chunks are sent one at a time. Stretches Gnani hears no speech in are dropped.
    """
    language = language_code or os.getenv("GNANI_STT_LANGUAGE") or DEFAULT_LANGUAGES
    intervals = find_speech_intervals(audio_path, total_duration)

    lines = []
    for n, (start, end) in enumerate(intervals):
        a = max(0.0, start - PAD_SECONDS)
        b = min(total_duration, end + PAD_SECONDS)
        chunk_path = os.path.join(work_dir, f"stt_chunk_{n}.wav")
        video_service._run([
            "ffmpeg", "-y", "-hide_banner", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", audio_path,
            "-ac", "1", "-ar", "16000", chunk_path,
        ])
        text = transcribe_chunk(chunk_path, language)
        if on_chunk:
            on_chunk(n + 1, len(intervals))
        if text:
            lines.append({"id": len(lines), "start": round(start, 3), "end": round(end, 3), "text": text})
    return lines
