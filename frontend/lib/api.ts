export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "https://echofy-ty4q.onrender.com").replace(/\/$/, "");
export const MAX_UPLOAD_BYTES = 800 * 1024 * 1024; // matches the backend limit

// Languages the default Gnani voice engine can speak.
export const LANGUAGES = [
  { key: "hindi", label: "Hindi" },
  { key: "telugu", label: "Telugu" },
  { key: "tamil", label: "Tamil" },
  { key: "kannada", label: "Kannada" },
  { key: "malayalam", label: "Malayalam" },
  { key: "marathi", label: "Marathi" },
  { key: "bengali", label: "Bengali" },
  { key: "gujarati", label: "Gujarati" },
  { key: "punjabi", label: "Punjabi" },
  { key: "english", label: "English" },
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

export function startDub(file: File, language: string, onUpload: (f: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("video", file);
    form.append("target_language", language);
    form.append("voice_engine", "gnani");
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/dub`);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onUpload(e.loaded / e.total); };
    xhr.onerror = () => reject(new Error("Could not reach the Echofy server. Check your connection and try again."));
    xhr.onload = () => {
      let body: { job_id?: string; detail?: unknown } = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* not json */ }
      if (xhr.status >= 200 && xhr.status < 300 && body.job_id) return resolve(body.job_id);
      reject(new Error(typeof body.detail === "string" ? body.detail : `Upload failed (HTTP ${xhr.status}).`));
    };
    xhr.send(form);
  });
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
