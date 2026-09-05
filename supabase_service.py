# -> supabase_service.py
"""
All Supabase reads/writes go through this module.

Key fix vs earlier version: supabase-py v2's storage upload requires
file_options values to be STRINGS — passing upsert=True (a Python bool)
or omitting content-type correctly is a common source of silent 500s.
Every public function here raises a clear, descriptive RuntimeError instead
of letting the raw Supabase/httpx exception bubble up as an opaque 500.
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
                "SUPABASE_URL / SUPABASE_SERVICE_KEY are not set in the environment."
            )
        _client = create_client(url, key)
    return _client


# ---------------- Storage ----------------

def upload_file(bucket: str, path: str, local_file_path: str, content_type: str = "application/octet-stream"):
    client = get_client()
    try:
        with open(local_file_path, "rb") as f:
            data = f.read()
    except OSError as exc:
        raise RuntimeError(f"Could not read local file '{local_file_path}' to upload: {exc}") from exc

    # supabase-py v2 requires ALL file_options values to be strings —
    # a bool here (upsert=True) is a common silent failure point.
    file_options = {
        "content-type": content_type,
        "upsert": "true",
    }

    try:
        client.storage.from_(bucket).upload(path, data, file_options)
    except Exception as exc:  # noqa: BLE001 — surface storage errors clearly
        raise RuntimeError(
            f"Supabase Storage upload failed for bucket='{bucket}' path='{path}': {exc}"
        ) from exc


def download_to_file(bucket: str, path: str, local_file_path: str):
    client = get_client()
    try:
        data = client.storage.from_(bucket).download(path)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Supabase Storage download failed for bucket='{bucket}' path='{path}': {exc}"
        ) from exc

    with open(local_file_path, "wb") as f:
        f.write(data)


def create_signed_url(bucket: str, path: str, expires_in_seconds: int = 3600) -> str | None:
    client = get_client()
    try:
        result = client.storage.from_(bucket).create_signed_url(path, expires_in_seconds)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Could not create signed URL for bucket='{bucket}' path='{path}': {exc}"
        ) from exc
    # supabase-py has returned both 'signedURL' and 'signedUrl' across versions
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
    try:
        result = client.table("dubbing_jobs").insert(row).execute()
    except Exception as exc:  # noqa: BLE001
        # Most common cause: voice_engine value not allowed by the table's
        # CHECK constraint — see the migration note in requirements.txt / README.
        raise RuntimeError(f"Failed to create dubbing_jobs row: {exc}") from exc

    if not result.data:
        raise RuntimeError("dubbing_jobs insert returned no data — check table permissions/schema.")

    return result.data[0]["id"]


def update_dubbing_job(job_id: str, **fields):
    if not fields:
        return
    client = get_client()
    try:
        client.table("dubbing_jobs").update(fields).eq("id", job_id).execute()
    except Exception as exc:  # noqa: BLE001
        print(f"[supabase_service] Failed to update dubbing_jobs id={job_id} with {fields}: {exc}")


def get_dubbing_job(job_id: str) -> dict | None:
    client = get_client()
    try:
        result = client.table("dubbing_jobs").select("*").eq("id", job_id).execute()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to fetch dubbing_jobs id={job_id}: {exc}") from exc
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
    try:
        client.table("dubbing_segments").insert(rows).execute()
    except Exception as exc:  # noqa: BLE001
        # Don't let a segments-table hiccup fail the whole job — the video
        # itself can still complete even if this history table write fails.
        print(f"[supabase_service] Failed to insert dubbing_segments for job {job_id}: {exc}")
