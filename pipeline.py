# -> pipeline.py
import os
import shutil
import traceback
import uuid

import gemini_service
import supabase_service
import tts_service
import video_service
import voice_casting
from languages import engine_can_speak, get_language

TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "tmp")


def _noop_progress(stage: str, progress: int):
    pass


def _time_slot(segments: list, index: int, total_duration: float) -> float:
    """Seconds a line may occupy: its own span, stretched into the following gap (never into the next line)."""
    seg = segments[index]
    own = seg["end"] - seg["start"]
    later_starts = [s["start"] for s in segments[index + 1:] if s["start"] > seg["start"]]
    room = (min(later_starts) if later_starts else total_duration) - seg["start"] - 0.05
    return max(own, min(room, own * 1.5))


def process_video(local_video_path: str, target_language: str, voice_engine: str, work_dir: str,
                  on_progress=None, stem_cache_dir: str = None) -> dict:
    """
    The whole dubbing job on local files only (no Supabase job table or uploads except the
    temporary file the stem separator needs). Original background music/effects are ALWAYS kept:
    vocals are separated out, the dubbed dialogue is mixed over the original background.

    Returns everything the caller and the quality gate need (paths, script, cast, timings).
    """
    progress = on_progress or _noop_progress
    os.makedirs(work_dir, exist_ok=True)

    ok, reason = engine_can_speak(voice_engine, target_language)
    if not ok:
        raise ValueError(reason)

    video_service.validate_video(local_video_path)
    total_duration = video_service.get_duration_seconds(local_video_path)

    progress("Extracting audio", 12)
    source_audio = os.path.join(work_dir, "source_audio.wav")
    video_service.extract_audio(local_video_path, source_audio, sample_rate=44100, channels=2)

    progress("Separating vocals from music", 22)
    vocals_path, background_path, separation_method = video_service.separate_vocals(
        source_audio, work_dir, cache_dir=stem_cache_dir
    )

    # Gemini hears the clean vocals when we have them, at a size it can take quickly.
    transcribe_input = os.path.join(work_dir, "transcribe_input.wav")
    video_service.extract_audio(vocals_path or source_audio, transcribe_input)

    progress("Transcribing & adapting dialogue", 35)
    lang = get_language(target_language)
    script = gemini_service.transcribe_and_translate(transcribe_input, lang["label"], total_duration)
    segments = script["segments"]
    if not segments:
        raise RuntimeError("No spoken dialogue was found in this video, so there is nothing to dub.")

    cast = voice_casting.build_cast(script["characters"], voice_engine, target_language)

    progress("Generating dubbed speech", 45)
    segment_files = []
    for i, seg in enumerate(segments):
        voice = voice_casting.ensure_speaker(cast, seg["speaker"], voice_engine, target_language)
        raw_path = os.path.join(work_dir, f"segment_{i}_raw.mp3")
        tts_service.generate_speech(
            seg["translated_text"], target_language, raw_path,
            engine=voice_engine, character_profile=seg["character_profile"],
            emotion=seg["emotion"], voice=voice,
        )
        slot = _time_slot(segments, i, total_duration)
        fit_path = os.path.join(work_dir, f"segment_{i}.wav")
        fit = video_service.prepare_segment(raw_path, fit_path, max_duration=slot, pitch_semitones=voice["pitch_semitones"])
        seg.update(index=i, voice_id=voice["voice_id"], tts_path=raw_path, slot_seconds=slot,
                   raw_duration=fit["raw_duration"], speedup=fit["speedup"], dubbed_duration=fit["duration"])
        segment_files.append({"start": seg["start"], "end": seg["end"], "path": fit_path})
        progress("Generating dubbed speech", min(70, int(45 + 25 * (i + 1) / len(segments))))

    progress("Mixing dubbed audio track", 75)
    voice_track_path = os.path.join(work_dir, "dubbed_track.wav")
    video_service.build_dubbed_track(segment_files, total_duration, voice_track_path)

    progress("Remixing with original background music", 82)
    final_audio_path = os.path.join(work_dir, "final_audio.wav")
    bg_applied_path = os.path.join(work_dir, "background_applied.wav")
    voice_gain_db = video_service.mix_with_background_music(
        voice_track_path, background_path, final_audio_path, bg_applied_path=bg_applied_path
    )

    progress("Merging with video", 88)
    output_path = os.path.join(work_dir, "output.mp4")
    video_service.merge_audio_into_video(local_video_path, final_audio_path, output_path)

    return {
        "output_path": output_path,
        "voice_track_path": voice_track_path,
        "background_applied_path": bg_applied_path,
        "total_duration": total_duration,
        "target_language": target_language,
        "language_label": lang["label"],
        "voice_engine": voice_engine,
        "detected_source_language": script.get("detected_source_language"),
        "scene_summary": script.get("scene_summary"),
        "characters": script["characters"],
        "cast": cast,
        "segments": segments,
        "separation_method": separation_method,
        "voice_gain_db": voice_gain_db,
    }


def run_pipeline(job_id: str, video_bucket_path: str, target_language: str, voice_engine: str, preserve_background_music: bool = True):
    # preserve_background_music is accepted only so older callers keep working.
    # Background music is always preserved; it is not optional.
    job_tmp = None
    try:
        # Mark the job as actually started RIGHT AWAY — if anything below
        # fails before the first real update, this line still ran, so the
        # job never gets stuck silently at its initial "Queued" state.
        supabase_service.update_dubbing_job(job_id, stage="Starting job", progress=1)

        job_tmp = os.path.join(TMP_DIR, job_id)
        os.makedirs(job_tmp, exist_ok=True)

        supabase_service.update_dubbing_job(job_id, stage="Downloading video", progress=5)
        local_video_path = os.path.join(job_tmp, "source" + os.path.splitext(video_bucket_path)[1])
        supabase_service.download_to_file(supabase_service.VIDEO_UPLOADS_BUCKET, video_bucket_path, local_video_path)

        def on_progress(stage: str, progress: int):
            supabase_service.update_dubbing_job(job_id, stage=stage, progress=progress)

        result = process_video(local_video_path, target_language, voice_engine, job_tmp, on_progress=on_progress)
        supabase_service.update_dubbing_job(job_id, from_language=result.get("detected_source_language"))

        segment_rows = []
        for seg in result["segments"]:
            seg_bucket_path = f"jobs/{job_id}/segments/{seg['index']}_{uuid.uuid4().hex[:8]}.mp3"
            supabase_service.upload_file(
                supabase_service.DUBBING_OUTPUTS_BUCKET, seg_bucket_path, seg["tts_path"], "audio/mpeg"
            )
            segment_rows.append({
                "segment_index": seg["index"],
                "speaker": seg["speaker"],
                "character_profile": seg["character_profile"],
                "emotion": seg["emotion"],
                "start_seconds": seg["start"],
                "end_seconds": seg["end"],
                "original_text": seg["original_text"],
                "translated_text": seg["translated_text"],
                "tts_audio_url": seg_bucket_path,
            })
        supabase_service.insert_segments(job_id, segment_rows)

        supabase_service.update_dubbing_job(job_id, stage="Uploading final video", progress=95)
        output_bucket_path = f"jobs/{job_id}/output.mp4"
        supabase_service.upload_file(
            supabase_service.DUBBING_OUTPUTS_BUCKET, output_bucket_path, result["output_path"], "video/mp4"
        )

        supabase_service.update_dubbing_job(
            job_id,
            status="completed", stage="Done", progress=100,
            output_video_url=output_bucket_path, error_message=None,
        )

    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        supabase_service.update_dubbing_job(job_id, status="failed", stage="Failed", error_message=str(exc))

    finally:
        if job_tmp and os.path.isdir(job_tmp):
            shutil.rmtree(job_tmp, ignore_errors=True)
