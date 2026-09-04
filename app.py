// -> frontend/app.js
const API_BASE = ""; // same origin — backend serves this frontend directly

const form = document.getElementById("dub-form");
const videoInput = document.getElementById("video");
const targetLanguageSelect = document.getElementById("target_language");
const voiceEngineSelect = document.getElementById("voice_engine");
const submitBtn = document.getElementById("submit-btn");

const progressArea = document.getElementById("progress-area");
const stageLabel = document.getElementById("stage-label");
const progressFill = document.getElementById("progress-fill");
const progressPct = document.getElementById("progress-pct");

const errorArea = document.getElementById("error-area");
const resultArea = document.getElementById("result-area");
const resultVideo = document.getElementById("result-video");
const downloadLink = document.getElementById("download-link");

let pollTimer = null;

async function loadLanguages() {
  const res = await fetch(`${API_BASE}/api/languages`);
  const data = await res.json();
  targetLanguageSelect.innerHTML = data.languages
    .map((lang) => `<option value="${lang.key}">${lang.label}</option>`)
    .join("");
}

function resetUI() {
  errorArea.classList.add("hidden");
  errorArea.textContent = "";
  resultArea.classList.add("hidden");
  progressArea.classList.remove("hidden");
  stageLabel.textContent = "Queued";
  progressFill.style.width = "0%";
  progressPct.textContent = "0%";
}

function showError(message) {
  clearInterval(pollTimer);
  progressArea.classList.add("hidden");
  errorArea.textContent = message;
  errorArea.classList.remove("hidden");
  submitBtn.disabled = false;
  submitBtn.textContent = "Dub this video";
}

function showResult(downloadUrl) {
  clearInterval(pollTimer);
  progressArea.classList.add("hidden");
  resultVideo.src = downloadUrl;      // Supabase signed URL — direct, not proxied through the backend
  downloadLink.href = downloadUrl;
  resultArea.classList.remove("hidden");
  submitBtn.disabled = false;
  submitBtn.textContent = "Dub this video";
}

function pollStatus(jobId) {
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/dub/${jobId}`);
      if (!res.ok) throw new Error("Lost track of this job.");
      const job = await res.json();

      stageLabel.textContent = job.stage || "Processing";
      progressFill.style.width = `${job.progress || 0}%`;
      progressPct.textContent = `${job.progress || 0}%`;

      if (job.status === "completed" && job.download_url) {
        showResult(job.download_url);
      } else if (job.status === "failed") {
        showError(job.error || "Something went wrong while dubbing this video.");
      }
    } catch (err) {
      showError(err.message);
    }
  }, 2000);
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!videoInput.files[0]) return;

  resetUI();
  submitBtn.disabled = true;
  submitBtn.textContent = "Uploading...";

  const formData = new FormData();
  formData.append("video", videoInput.files[0]);
  formData.append("target_language", targetLanguageSelect.value);
  formData.append("voice_engine", voiceEngineSelect.value);

  try {
    const res = await fetch(`${API_BASE}/api/dub`, { method: "POST", body: formData });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || "Upload failed.");
    }
    const data = await res.json();
    submitBtn.textContent = "Dubbing in progress...";
    pollStatus(data.job_id);
  } catch (err) {
    showError(err.message);
  }
});

loadLanguages();
