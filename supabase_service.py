# -> backend/services/supabase_service.py
"""
All Supabase reads/writes go through this module — storage (buckets) and
the two tables the dubbing pipeline touches: dubbing_jobs, dubbing_segments.

Uses the service role key, so it bypasses RLS entirely. That's fine for now
since there's no auth layer yet — once you add accounts, switch to scoping
these calls per-user and add RLS policies as described in the schema file.
"""
import os

from supabase import Client, create_client

VIDEO_UPLOADS_BUCKET = "video_uploads"
DUBBING_OUTPUTS_BUCKET = "dubbing_outputs"

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL / SUPABASE_SERVICE_KEY are not set. Add them to backend/.env."
            )
        _client = create_client(url, key)
    return _client


# ---------------- Storage ----------------

def upload_file(bucket: str, path: str, local_file_path: str, content_type: str = "application/octet-stream"):
    client = get_client()
    with open(local_file_path, "rb") as f:
        data = f.read()
    client.storage.from_(bucket).upload(
        path, data, {"content-type": content_type, "upsert": "true"}
    )


def download_to_file(bucket: str, path: str, local_file_path: str):
    client = get_client()
    data = client.storage.from_(bucket).download(path)
    with open(local_file_path, "wb") as f:
        f.write(data)


def create_signed_url(bucket: str, path: str, expires_in_seconds: int = 3600) -> str:
    client = get_client()
    result = client.storage.from_(bucket).create_signed_url(path, expires_in_seconds)
    # supabase-py returns {'signedURL': '...'} or {'signedUrl': '...'} depending on version
    return result.get("signedURL") or result.get("signedUrl")


# ---------------- dubbing_jobs ----------------

def create_dubbing_job(video_name: str, target_language: str, voice_engine: str, video_path: str) -> str:
    client = get_client()
    row = {
        "video_name": video_name,
        "target_language": target_language,
        "voice_engine": voice_engine,
        "video_url": video_path,
        "status": "processing",
        "stage": "Queued",
        "progress": 0,
    }
    result = client.table("dubbing_jobs").insert(row).execute()
    return result.data[0]["id"]


def update_dubbing_job(job_id: str, **fields):
    client = get_client()
    client.table("dubbing_jobs").update(fields).eq("id", job_id).execute()


def get_dubbing_job(job_id: str) -> dict | None:
    client = get_client()
    result = client.table("dubbing_jobs").select("*").eq("id", job_id).execute()
    return result.data[0] if result.data else None


# ---------------- dubbing_segments ----------------

def insert_segments(job_id: str, segments: list[dict]):
    """
    segments: list of {segment_index, speaker, start_seconds, end_seconds,
                        original_text, translated_text, tts_audio_url}
    """
    if not segments:
        return
    client = get_client()
    rows = [{**seg, "job_id": job_id} for seg in segments]
    client.table("dubbing_segments").insert(rows).execute()
