import os
import json
import shutil
import subprocess
import tempfile
from gradio_client import Client, handle_file

BATCH_SIZE = 25  # max simultaneous ffmpeg inputs per mix pass

class FFmpegError(RuntimeError):
    pass

# ... [Keep your existing _run, validate_video, get_duration_seconds, extract_audio, _mix_batch, and build_dubbed_track functions exactly as they are] ...

def separate_vocals(audio_path: str, work_dir: str) -> tuple:
    """
    Splits audio into (vocals_path, background_path) by offloading compute
    to a free Hugging Face GPU via gradio_client. Zero RAM usage locally.
    """
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise FFmpegError("HF_TOKEN is not set. Cannot run Hugging Face separation.")

    try:
        # Connect to the public Demucs space
        client = Client("abidlabs/music-separation", hf_token=hf_token)
        
        # Upload the audio and trigger the separation model
        result = client.predict(
            track=handle_file(audio_path),
            api_name="/predict"
        )
        
        # The space returns a tuple of temporary paths: (vocals, instrumental)
        hf_vocals_path, hf_instrumental_path = result[0], result[1]
        
        local_vocals = os.path.join(work_dir, "separated_vocals.wav")
        local_background = os.path.join(work_dir, "instrumental_bg.wav")
        
        # Copy from gradio's temp cache into our job's working directory
        shutil.copy(hf_vocals_path, local_vocals)
        shutil.copy(hf_instrumental_path, local_background)
        
        return local_vocals, local_background
        
    except Exception as exc:
        raise FFmpegError(f"Hugging Face vocal separation failed: {exc}")

# ... [Keep your existing mix_with_background_music and merge_audio_into_video functions exactly as they are] ...
