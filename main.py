# -> repo root: main.py
import os
import uuid

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import pipeline
import supabase_service
from languages import SUPPORTED_LANGUAGES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_TMP_DIR = os.path.join(BASE_DIR, "storage", "tmp")
os.makedirs(LOCAL_TMP_DIR, exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # 300MB

app = FastAPI(title="Echofy Dubbing MVP")

origins = os.getenv("ALLOWED_ORIGINS", "*")[span_2](start_span)[span_2](end_span)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if origins == "*" else origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _job_public_view(job: dict) -> dict:
    """Only return safe public properties and signed download URLs."""
    download_url = None
    is_done = job.get("status") == "completed[span_3](start_span)"[span_3](end_span)

    if is_done and job.get("output_video_url"):
        download_url = supabase_service.get_signed_url_from_path(
            bucket="dubbing_outputs",
            storage_path=job["output_video_url"],
            expires_in=3600,
        )[span_4](start_span)[span_4](end_span)

    return {
        "job_id": job["id"],
        "status": job.get("status"),
        "stage": job.get("stage"),
        "progress": job.get("progress", 0),
        "detected_source_language": job.get("from_language") or job.get("detected_source_language"),
        "error": job.get("error_message") or job.get("error"),
        "download_ready": is_done,
        "download_url": download_url,
    }[span_5](start_span)[span_5](end_span)


@app.get("/api/languages")
def get_languages():
    return {"languages": SUPPORTED_LANGUAGES}[span_6](start_span)[span_6](end_span)


@app.post("/api/dub")
async def create_dub_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    target_language: str = Form("telugu"),
    voice_engine: str = Form("fish"),
):
    if not video.filename:
        raise HTTPException(status_code=400, detail="No video file provided.")[span_7](start_span)[span_7](end_span)

    ext = os.path.splitext(video.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")

    target_lang = target_language.lower().strip()[span_8](start_span)[span_8](end_span)
    if target_lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported target language: {target_lang}")

    allowed_engines = {"gtts", "sarvam", "fish", "edge"}
    selected_engine = voice_engine.lower().strip()
    if selected_engine not in allowed_engines:
        raise HTTPException(
            status_code=400,
            detail=f"voice_engine must be one of: {list(allowed_engines)}"
        )

    # Read video into bytes and check upload size limit
    video_bytes = await video.read()[span_9](start_span)[span_9](end_span)
    if len(video_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large for this MVP (300MB limit)")

    job_id = str(uuid.uuid4())[span_10](start_span)[span_10](end_span)
    video_bucket_path = f"inputs/{job_id}_{video.filename}[span_11](start_span)"[span_11](end_span)

    # Upload raw bytes directly to Supabase Storage
    try:
        source_url = supabase_service.upload_file(
            bucket="video_uploads",
            destination_path=video_bucket_path,
            file_bytes=video_bytes,
            content_type=video.content_type or "video/mp4",
        )[span_12](start_span)[span_12](end_span)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase storage upload failed: {str(e)}")[span_13](start_span)[span_13](end_span)

    # Record job in Supabase database
    try:
        supabase_service.create_job(
            job_id=job_id,
            video_name=video.filename,
            to_language=target_lang,
            source_url=source_url,
            voice_engine=selected_engine,
        )[span_14](start_span)[span_14](end_span)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job record: {str(e)}")

    # Dispatch async pipeline worker
    background_tasks.add_task(
        pipeline.run_dubbing_pipeline,
        job_id=job_id,
        video_bytes=video_bytes,
        filename=video.filename,
        target_language=target_lang,
        voice_engine=selected_engine,
    )[span_15](start_span)[span_15](end_span)

    return {"job_id": job_id}[span_16](start_span)[span_16](end_span)


@app.get("/api/dub/{job_id}")
def get_dub_status(job_id: str):
    job = supabase_service.get_job(job_id)[span_17](start_span)[span_17](end_span)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")[span_18](start_span)[span_18](end_span)
    return _job_public_view(job)


FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    
