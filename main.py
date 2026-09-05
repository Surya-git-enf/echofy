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
from languages import is_supported, public_language_list

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_TMP_DIR = os.path.join(BASE_DIR, "storage", "tmp")
os.makedirs(LOCAL_TMP_DIR, exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # 300MB — generous free-tier-friendly ceiling

app = FastAPI(title="Echofy Dubbing MVP (Supabase-backed)")

origins = os.getenv("ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if origins == "*" else origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _job_public_view(job: dict) -> dict:
    """
    Only return what the frontend actually needs — never raw bucket paths,
    internal ids beyond job_id, or anything else sitting on the row.
    A signed, time-limited download URL is generated on demand instead of
    exposing the bucket path directly.
    """
    view = {
        "job_id": job["id"],
        "status": job.get("status"),
        "stage": job.get("stage"),
        "progress": job.get("progress", 0),
        "detected_source_language": job.get("detected_source_language"),
        "error": job.get("error") if job.get("status") == "failed" else None,
        "download_ready": job.get("status") == "completed",
        "download_url": None,
    }
    if view["download_ready"] and job.get("output_url"):
        view["download_url"] = supabase_service.create_signed_url(
            supabase_service.DUBBING_OUTPUTS_BUCKET, job["output_url"], expires_in_seconds=3600
        )
    return view


@app.get("/api/languages")
def get_languages():
    return {"languages": public_language_list()}


@app.post("/api/dub")
async def create_dub_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    target_language: str = Form(...),
    voice_engine: str = Form("gtts"),
):
    ext = os.path.splitext(video.filename or "")[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")

    if not is_supported(target_language):
        raise HTTPException(status_code=400, detail=f"Unsupported target language: {target_language}")

    if voice_engine not in ("gtts", "sarvam","fish","edge"):
        raise HTTPException(status_code=400, detail="voice_engine must be 'gtts' or 'sarvam'")

    # Stream the upload to a short-lived local temp file just long enough to
    # push it into Supabase — nothing is meant to persist on local disk,
    # since that disk is wiped on every restart/redeploy on Render's free tier.
    temp_id = uuid.uuid4().hex
    local_temp_path = os.path.join(LOCAL_TMP_DIR, f"{temp_id}{ext}")

    size = 0
    with open(local_temp_path, "wb") as f:
        while chunk := await video.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                f.close()
                os.remove(local_temp_path)
                raise HTTPException(status_code=400, detail="File too large for this MVP (300MB limit)")
            f.write(chunk)

    video_bucket_path = f"uploads/{temp_id}{ext}"
    try:
        supabase_service.upload_file(
            supabase_service.VIDEO_UPLOADS_BUCKET, video_bucket_path, local_temp_path, video.content_type or "video/mp4"
        )
    finally:
        os.remove(local_temp_path)

    job_id = supabase_service.create_dubbing_job(
        video_name=video.filename or "video",
        target_language=target_language,
        voice_engine=voice_engine,
        video_path=video_bucket_path,
    )

    background_tasks.add_task(
        pipeline.run_pipeline, job_id, video_bucket_path, target_language, voice_engine,
    )

    return {"job_id": job_id}


@app.get("/api/dub/{job_id}")
def get_dub_status(job_id: str):
    job = supabase_service.get_dubbing_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_public_view(job)


# Serve the static frontend from the same process, from a ./frontend folder
# if you keep one alongside these files. Safe to leave in even if that
# folder doesn't exist yet — it just won't mount.
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    
