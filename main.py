import os
import uuid
from dotenv import load_dotenv

load_dotenv()[span_7](start_span)[span_7](end_span)

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile[span_8](start_span)[span_8](end_span)
from fastapi.middleware.cors import CORSMiddleware[span_9](start_span)[span_9](end_span)
from fastapi.staticfiles import StaticFiles[span_10](start_span)[span_10](end_span)

import pipeline[span_11](start_span)[span_11](end_span)
import supabase_service[span_12](start_span)[span_12](end_span)
from languages import SUPPORTED_LANGUAGES, is_supported[span_13](start_span)[span_13](end_span)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # 300MB

app = FastAPI(title="Echofy Dubbing MVP")[span_14](start_span)[span_14](end_span)

origins = os.getenv("ALLOWED_ORIGINS", "*")[span_15](start_span)[span_15](end_span)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if origins == "*" else origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)[span_16](start_span)[span_16](end_span)


def _format_job_view(job: dict) -> dict:
    download_url = None
    is_completed = job.get("status") == "completed[span_17](start_span)"[span_17](end_span)
    
    if is_completed and job.get("output_video_url"):
        download_url = supabase_service.get_signed_url_from_path(
            bucket="dubbing_outputs",
            storage_path=job["output_video_url"],
            expires_in=3600,
        )[span_18](start_span)[span_18](end_span)

    return {
        "job_id": job["id"],
        "status": job.get("status"),
        "stage": job.get("stage"),
        "progress": job.get("progress", 0),
        "detected_source_language": job.get("from_language") or job.get("detected_source_language"),
        "error": job.get("error_message") or job.get("error"),
        "download_ready": is_completed,
        "download_url": download_url,
    }[span_19](start_span)[span_19](end_span)


@app.get("/api/languages")
def get_languages():
    return {"languages": SUPPORTED_LANGUAGES}[span_20](start_span)[span_20](end_span)


@app.post("/api/dub")
async def create_dub_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    target_language: str = Form("telugu"),
    voice_engine: str = Form("fish"),
):
    if not video.filename:
        raise HTTPException(status_code=400, detail="No video file provided.")[span_21](start_span)[span_21](end_span)

    ext = os.path.splitext(video.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")

    target_lang = target_language.lower().strip()[span_22](start_span)[span_22](end_span)
    if not is_supported(target_lang):
        raise HTTPException(status_code=400, detail=f"Unsupported target language: {target_lang}")

    allowed_engines = {"fish", "edge", "sarvam", "gtts"}
    engine = voice_engine.lower().strip()
    if engine not in allowed_engines:
        raise HTTPException(
            status_code=400,
            detail=f"voice_engine must be one of {list(allowed_engines)}"
        )

    video_bytes = await video.read()[span_23](start_span)[span_23](end_span)
    if len(video_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large (300MB limit)")

    job_id = str(uuid.uuid4())[span_24](start_span)[span_24](end_span)
    storage_dest = f"inputs/{job_id}_{video.filename}[span_25](start_span)"[span_25](end_span)

    try:
        source_url = supabase_service.upload_file(
            bucket="video_uploads",
            destination_path=storage_dest,
            file_bytes=video_bytes,
            content_type=video.content_type or "video/mp4",
        )[span_26](start_span)[span_26](end_span)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase storage upload failed: {str(e)}")[span_27](start_span)[span_27](end_span)

    try:
        supabase_service.create_job(
            job_id=job_id,
            video_name=video.filename,
            to_language=target_lang,
            source_url=source_url,
            voice_engine=engine,
        )[span_28](start_span)[span_28](end_span)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job row: {str(e)}")

    background_tasks.add_task(
        pipeline.run_dubbing_pipeline,
        job_id=job_id,
        video_bytes=video_bytes,
        filename=video.filename,
        target_language=target_lang,
        voice_engine=engine,
    )[span_29](start_span)[span_29](end_span)

    return {"job_id": job_id}[span_30](start_span)[span_30](end_span)


@app.get("/api/dub/{job_id}")
def get_dub_status(job_id: str):
    job = supabase_service.get_job(job_id)[span_31](start_span)[span_31](end_span)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")[span_32](start_span)[span_32](end_span)
    return _format_job_view(job)


FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    
