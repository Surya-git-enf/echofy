# -> pipeline.py
import os
import shutil
import traceback
import uuid

import gemini_service
import supabase_service
import tts_service
import video_service
from languages import get_language

TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "tmp")


def run_pipeline(job_id: str, video_bucket_path: str, target_language: str, voice_engine: str):
    job_tmp = os.path.join(TMP_DIR, job_id)
    os.makedirs(job_tmp, exist_ok=True)

    try:
        supabase_service.update_dubbing_job(job_id, stage="Downloading video", progress=5)
        local_video_path = os.path.join(job_tmp, "source" + os.path.splitext(video_bucket_path)[1])
        supabase_service.download_to_file(supabase_service.VIDEO_UPLOADS_BUCKET, video_bucket_path, local_video_path)

        supabase_service.update_dubbing_job(job_id, stage="Extracting audio", progress=15)
        audio_path = os.path.join(job_tmp, "source_audio.wav")
        video_service.extract_audio(local_video_path, audio_path)
        total_duration = video_service.get_duration_seconds(local_video_path)

        supabase_service.update_dubbing_job(job_id, stage="Transcribing & adapting dialogue", progress=30)
        lang_label = get_language(target_language)["label"]
        result = gemini_service.transcribe_and_translate(audio_path, lang_label)
        segments = result.get("segments", [])
        supabase_service.update_dubbing_job(job_id, from_language=result.get("detected_source_language"))

        supabase_service.update_dubbing_job(job_id, stage="Generating dubbed speech", progress=45)
        segment_files = []
        segment_rows = []
        for i, seg in enumerate(segments):
            text = (seg.get("translated_text") or "").strip()
            if not text:
                continue

            character_profile = seg.get("character_profile", "default")

            seg_audio_path = os.path.join(job_tmp, f"segment_{i}.mp3")
            tts_service.generate_speech(
                text, target_language, seg_audio_path,
                engine=voice_engine, character_profile=character_profile,
            )
            segment_files.append({"start": float(seg.get("start", 0)), "path": seg_audio_path})

            seg_bucket_path = f"jobs/{job_id}/segments/{i}_{uuid.uuid4().hex[:8]}.mp3"
            supabase_service.upload_file(
                supabase_service.DUBBING_OUTPUTS_BUCKET, seg_bucket_path, seg_audio_path, "audio/mpeg"
            )

            segment_rows.append({
                "segment_index": i,
                "speaker": seg.get("speaker"),
                "character_profile": character_profile,
                "start_seconds": seg.get("start", 0),
                "end_seconds": seg.get("end", 0),
                "original_text": seg.get("original_text", ""),
                "translated_text": text,
                "tts_audio_url": seg_bucket_path,
            })

            step = 25 / max(len(segments), 1)
            supabase_service.update_dubbing_job(job_id, progress=min(70, int(45 + step * (i + 1))))

        supabase_service.insert_segments(job_id, segment_rows)

        supabase_service.update_dubbing_job(job_id, stage="Mixing dubbed audio track", progress=75)
        dubbed_track_path = os.path.join(job_tmp, "dubbed_track.wav")
        video_service.build_dubbed_track(segment_files, total_duration, dubbed_track_path)

        supabase_service.update_dubbing_job(job_id, stage="Merging with video", progress=88)
        output_local_path = os.path.join(job_tmp, "output.mp4")
        video_service.merge_audio_into_video(local_video_path, dubbed_track_path, output_local_path)

        supabase_service.update_dubbing_job(job_id, stage="Uploading final video", progress=95)
        output_bucket_path = f"jobs/{job_id}/output.mp4"
        supabase_service.upload_file(
            supabase_service.DUBBING_OUTPUTS_BUCKET, output_bucket_path, output_local_path, "video/mp4"
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
        shutil.rmtree(job_tmp, ignore_errors=True)
        
