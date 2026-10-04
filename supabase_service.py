# -> supabase_service.py
"""
All Supabase reads/writes go through this module.

Key fix vs earlier version: both upload_file() and download_to_file() now
VERIFY the transferred byte count against what Supabase reports for the
file, and retry automatically on a mismatch. This is the fix for a real
production bug: an 11.27MB video silently arrived as 1.43MB with the SDK
reporting success the whole time — ffmpeg only caught it much later as a
"moov atom not found" error. A partial transfer now fails loudly, with a
retry first, instead of corrupting the pipeline downstream.

Also: supabase-py v2's storage upload requires file_options values to be
STRINGS — passing upsert=True (a Python bool) is a common source of silent
500s. Every public function here raises a clear, descriptive RuntimeError
instead of letting the raw Supabase/httpx exception bubble up as an opaque
500.
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

def _remote_size(client: Client, bucket: str, path: str) -> int | None:
    """Looks up a stored object's reported size via list(), or None if not found."""
    folder = "/".join(path.split("/")[:-1])
    filename = path.split("/")[-1]
    try:
        listing = client.storage.from_(bucket).list(folder)
    except Exception as exc:  # noqa: BLE001
        print(f"[supabase_service] Could not list bucket='{bucket}' folder='{folder}': {exc}")
        return None

    for entry in listing:
        if entry.get("name") == filename:
            metadata = entry.get("metadata") or {}
            size = metadata.get("size")
            return int(size) if size is not None else None
    return None


def upload_file(
    bucket: str,
    path: str,
    local_file_path: str,
    content_type: str = "application/octet-stream",
    max_retries: int = 2,
):
    try:
        with open(local_file_path, "rb") as f:
            data = f.read()
    except OSError as exc:
        raise RuntimeError(f"Could not read local file '{local_file_path}' to upload: {exc}") from exc

    local_size = len(data)
    client = get_client()

    # supabase-py v2 requires ALL file_options values to be strings —
    # a bool here (upsert=True) is a common silent failure point.
    file_options = {
        "content-type": content_type,
        "upsert": "true",
    }

    last_error: RuntimeError | None = None

    for attempt in range(1, max_retries + 1):
        try:
            client.storage.from_(bucket).upload(path, data, file_options)
        except Exception as exc:  # noqa: BLE001
            last_error = RuntimeError(
                f"Supabase Storage upload failed for bucket='{bucket}' path='{path}' "
                f"(attempt {attempt}/{max_retries}): {exc}"
            )
            print(f"[supabase_service] {last_error}")
            continue

        remote_size = _remote_size(client, bucket, path)

        if remote_size is None:
            last_error = RuntimeError(
                f"Upload of bucket='{bucket}' path='{path}' could not be verified "
                f"(attempt {attempt}/{max_retries}): file not found in bucket listing after upload."
            )
            print(f"[supabase_service] {last_error}")
            continue

        if remote_size != local_size:
            last_error = RuntimeError(
                f"Upload verification failed for bucket='{bucket}' path='{path}' "
                f"(attempt {attempt}/{max_retries}): local file is {local_size} bytes "
                f"but Supabase reports {remote_size} bytes — upload was truncated."
            )
            print(f"[supabase_service] {last_error}")
            continue

        return  # success, verified

    raise last_error or RuntimeError(
        f"Supabase Storage upload failed for bucket='{bucket}' path='{path}' after {max_retries} attempts."
    )


def download_to_file(
    bucket: str,
    path: str,
    local_file_path: str,
    max_retries: int = 2,
):
    client = get_client()
    expected_size = _remote_size(client, bucket, path)
    if expected_size is None:
        print(
            f"[supabase_service] Warning: could not determine expected size for "
            f"bucket='{bucket}' path='{path}' — downloading without size verification."
        )

    last_error: RuntimeError | None = None

    for attempt in range(1, max_retries + 1):
        try:
            data = client.storage.from_(bucket).download(path)
        except Exception as exc:  # noqa: BLE001
            last_error = RuntimeError(
                f"Supabase Storage download failed for bucket='{bucket}' path='{path}' "
                f"(attempt {attempt}/{max_retries}): {exc}"
            )
            print(f"[supabase_service] {last_error}")
            continue

        actual_size = len(data)
        if expected_size is not None and actual_size != expected_size:
            last_error = RuntimeError(
                f"Download verification failed for bucket='{bucket}' path='{path}' "
                f"(attempt {attempt}/{max_retries}): expected {expected_size} bytes, "
                f"got {actual_size} bytes — download was truncated."
            )
            print(f"[supabase_service] {last_error}")
            continue

        with open(local_file_path, "wb") as f:
            f.write(data)
        return  # success, verified

    raise last_error or RuntimeError(
        f"Supabase Storage download failed for bucket='{bucket}' path='{path}' after {max_retries} attempts."
    )


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
