# -> main.py
import os
import sys
import traceback
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
ALLOWED_VOICE_ENGINES = {"fish", "echofy", "edge", "sarvam", "gtts"}
MAX_UPLOAD_BYTES = 800 * 1024 * 1024  # ~800MB — enough headroom for a 20-min compressed video

app = FastAPI(title="Echofy Dubbing MVP (Supabase-backed)")

origins = os.getenv("ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if origins == "*" else origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _job_public_view(job: dict) -> dict:
    view = {
        "job_id": job["id"],
        "status": job.get("status"),
        "stage": job.get("stage"),
        "progress": job.get("progress", 0),
        "from_language": job.get("from_language"),
        "error": job.get("error_message") if job.get("status") == "failed" else None,
        "download_ready": job.get("status") == "completed",
        "download_url": None,
    }
    if view["download_ready"] and job.get("output_video_url"):
        try:
            view["download_url"] = supabase_service.create_signed_url(
                supabase_service.DUBBING_OUTPUTS_BUCKET, job["output_video_url"], expires_in_seconds=3600
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[main] Failed to create signed URL for job {job['id']}: {exc}")
    return view


@app.get("/api/languages")
def get_languages():
    return {"languages": public_language_list()}


@app.post("/api/dub")
async def create_dub_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    target_language: str = Form(...),
    voice_engine: str = Form("echofy"),
):
    ext = os.path.splitext(video.filename or "")[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")

    if not is_supported(target_language):
        raise HTTPException(status_code=400, detail=f"Unsupported target language: {target_language}")

    if voice_engine not in ALLOWED_VOICE_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"voice_engine must be one of {sorted(ALLOWED_VOICE_ENGINES)}, got '{voice_engine}'",
        )

    if voice_engine == "fish" and not os.getenv("FISH_AUDIO_API_KEY"):
        raise HTTPException(status_code=400, detail="voice_engine='fish' requires FISH_AUDIO_API_KEY on the server.")

    if voice_engine == "echofy" and not os.getenv("ECHOFY_VOICE_SERVICE_URL"):
        raise HTTPException(status_code=400, detail="voice_engine='echofy' requires ECHOFY_VOICE_SERVICE_URL on the server.")

    temp_id = uuid.uuid4().hex
    local_temp_path = os.path.join(LOCAL_TMP_DIR, f"{temp_id}{ext}")

    try:
        size = 0
        with open(local_temp_path, "wb") as f:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    f.close()
                    os.remove(local_temp_path)
                    raise HTTPException(status_code=400, detail="File too large for this MVP (300MB limit)")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if os.path.exists(local_temp_path):
            os.remove(local_temp_path)
        raise HTTPException(status_code=500, detail=f"Failed to receive uploaded file: {exc}") from exc

    video_bucket_path = f"uploads/{temp_id}{ext}"
    try:
        supabase_service.upload_file(
            supabase_service.VIDEO_UPLOADS_BUCKET,
            video_bucket_path,
            local_temp_path,
            video.content_type or "video/mp4",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to upload video to storage: {exc}") from exc
    finally:
        if os.path.exists(local_temp_path):
            os.remove(local_temp_path)

    try:
        job_id = supabase_service.create_dubbing_job(
            video_name=video.filename or "video",
            target_language=target_language,
            voice_engine=voice_engine,
            video_path=video_bucket_path,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to create dubbing job record: {exc}") from exc

    background_tasks.add_task(
        pipeline.run_pipeline, job_id, video_bucket_path, target_language, voice_engine,
    )

    return {"job_id": job_id}


@app.get("/api/dub/{job_id}")
def get_dub_status(job_id: str):
    try:
        job = supabase_service.get_dubbing_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to fetch job status: {exc}") from exc

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_public_view(job)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    from fastapi.responses import JSONResponse
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": f"Unhandled server error: {exc}"})


FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    
