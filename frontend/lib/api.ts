export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "https://echofy-ty4q.onrender.com").replace(/\/$/, "");
export const MAX_UPLOAD_BYTES = 800 * 1024 * 1024; // matches the backend limit

// Languages the default Gnani voice engine can speak.
export const LANGUAGES = [
  { key: "hindi", label: "Hindi", native: "हिन्दी", lang: "hi" },
  { key: "telugu", label: "Telugu", native: "తెలుగు", lang: "te" },
  { key: "tamil", label: "Tamil", native: "தமிழ்", lang: "ta" },
  { key: "kannada", label: "Kannada", native: "ಕನ್ನಡ", lang: "kn" },
  { key: "malayalam", label: "Malayalam", native: "മലയാളം", lang: "ml" },
  { key: "marathi", label: "Marathi", native: "मराठी", lang: "mr" },
  { key: "bengali", label: "Bengali", native: "বাংলা", lang: "bn" },
  { key: "gujarati", label: "Gujarati", native: "ગુજરાતી", lang: "gu" },
  { key: "punjabi", label: "Punjabi", native: "ਪੰਜਾਬੀ", lang: "pa" },
  { key: "hinglish", label: "Hinglish", native: "Hinglish", lang: "hi" },
  { key: "english", label: "English", native: "English", lang: "en" },
];

export interface JobStatus {
  job_id: string;
  status: "processing" | "completed" | "failed";
  stage: string | null;
  progress: number | null;
  error: string | null;
  download_ready: boolean;
  download_url: string | null;
}

/** Asks the server to answer. Render's free tier sleeps when idle and takes up to a minute to wake. */
async function ping(timeoutMs = 8000): Promise<boolean> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}/`, { cache: "no-store", signal: ctl.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

/** Fire-and-forget nudge so a sleeping server starts waking as soon as the page opens. */
export function warmUp() { void ping(30000); }

/** Waits until the server is awake, up to `maxMs`. Returns whether it answered. */
export async function wakeServer(maxMs = 90000): Promise<boolean> {
  const until = Date.now() + maxMs;
  while (Date.now() < until) {
    if (await ping()) return true;
    await new Promise((r) => setTimeout(r, 3000));
  }
  return false;
}

function uploadOnce(file: File, language: string, onUpload: (f: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("video", file);
    form.append("target_language", language);
    form.append("voice_engine", "gnani");
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/dub`);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onUpload(e.loaded / e.total); };
    xhr.onerror = () => reject(new NetworkError());
    xhr.onload = () => {
      let body: { job_id?: string; detail?: unknown } = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* not json */ }
      if (xhr.status >= 200 && xhr.status < 300 && body.job_id) return resolve(body.job_id);
      reject(new Error(typeof body.detail === "string" ? body.detail : `Upload failed (HTTP ${xhr.status}).`));
    };
    xhr.send(form);
  });
}

class NetworkError extends Error {}

/**
 * Uploads the video and starts the dub. Wakes the server first, and if the connection drops
 * mid-upload it wakes the server again and retries once before giving up with a specific reason.
 */
export async function startDub(
  file: File,
  language: string,
  onUpload: (f: number) => void,
  onWaking: (waking: boolean) => void = () => {},
): Promise<string> {
  onWaking(true);
  const awake = await wakeServer();
  onWaking(false);
  if (!awake) throw new Error(`The Echofy server (${new URL(API_URL).host}) is not responding. It may be starting up or down. Wait a minute and try again.`);

  for (let attempt = 1; ; attempt++) {
    try {
      return await uploadOnce(file, language, onUpload);
    } catch (e) {
      if (!(e instanceof NetworkError)) throw e;
      if (attempt >= 2) {
        const up = await ping();
        throw new Error(up
          ? "The upload was interrupted. Check your connection (a large video on mobile data can drop) and try again."
          : "The server stopped responding during the upload. Try again in a minute.");
      }
      onUpload(0);
      onWaking(true);
      await wakeServer(60000);
      onWaking(false);
    }
  }
}

export async function getJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_URL}/api/dub/${jobId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Status check failed (HTTP ${res.status}).`);
  return res.json();
}

export const absoluteUrl = (u: string) => (u.startsWith("http") ? u : `${API_URL}${u.startsWith("/") ? "" : "/"}${u}`);

export function readDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(v.duration); };
    v.onerror = () => { URL.revokeObjectURL(url); reject(new Error("The browser cannot read this video. Try an MP4.")); };
    v.src = url;
  });
}
