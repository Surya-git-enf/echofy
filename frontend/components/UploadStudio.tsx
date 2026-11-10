"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { absoluteUrl, getJob, LANGUAGES, MAX_UPLOAD_BYTES, readDuration, startDub } from "@/lib/api";
import { costFor, CREDITS_PER_MINUTE, refund, spend, useCredits } from "@/lib/credits";
import EqualizerLoader from "./EqualizerLoader";

const PHRASES = [
  "Cooking up your dub... 🔥",
  "Giving your video a new voice...",
  "Voice makeover in progress...",
  "Making language barriers disappear...",
  "Your video is going global...",
  "Syncing the vibes...",
  "Bringing your words to life...",
  "Almost ready to break language barriers...",
];

type Phase =
  | { kind: "idle"; error?: string }
  | { kind: "ready"; file: File; seconds: number }
  | { kind: "uploading"; file: File; fraction: number }
  | { kind: "processing"; name: string; stage: string; progress: number }
  | { kind: "done"; name: string; url: string }
  | { kind: "failed"; message: string };

const JOB_KEY = "echofy.job.v1";
interface SavedJob { id: string; cost: number; name: string }
const saveJob = (j: SavedJob | null) => {
  try { j ? localStorage.setItem(JOB_KEY, JSON.stringify(j)) : localStorage.removeItem(JOB_KEY); } catch { /* ignore */ }
};
const loadJob = (): SavedJob | null => {
  try { const r = localStorage.getItem(JOB_KEY); return r ? JSON.parse(r) : null; } catch { return null; }
};
const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export default function UploadStudio() {
  const credits = useCredits();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [language, setLanguage] = useState("hindi");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<number | null>(null);

  const stopPoll = () => { if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null; } };

  const poll = useCallback((job: SavedJob) => {
    stopPoll();
    let misses = 0;
    const tick = async () => {
      try {
        const s = await getJob(job.id);
        misses = 0;
        if (s.status === "completed" && s.download_url) {
          stopPoll(); saveJob(null);
          setPhase({ kind: "done", name: job.name, url: absoluteUrl(s.download_url) });
        } else if (s.status === "failed") {
          stopPoll(); saveJob(null); refund(job.cost);
          setPhase({ kind: "failed", message: s.error || "The dub failed on the server. Your credits were returned." });
        } else {
          setPhase({ kind: "processing", name: job.name, stage: s.stage || "Queued", progress: s.progress ?? 0 });
        }
      } catch {
        if (++misses >= 6) {
          stopPoll();
          setPhase({ kind: "failed", message: "Lost contact with the server. Reload the page to check this job again." });
        }
      }
    };
    tick();
    pollRef.current = window.setInterval(tick, 2500);
  }, []);

  useEffect(() => {
    const saved = loadJob();
    if (saved) { setPhase({ kind: "processing", name: saved.name, stage: "Reconnecting", progress: 0 }); poll(saved); }
    return stopPoll;
  }, [poll]);

  const pick = async (file: File | undefined | null) => {
    if (!file) return;
    if (!file.type.startsWith("video/")) return setPhase({ kind: "idle", error: "Choose an MP4 video." });
    if (file.size > MAX_UPLOAD_BYTES) return setPhase({ kind: "idle", error: "That file is over 800 MB. Trim it and try again." });
    try { setPhase({ kind: "ready", file, seconds: await readDuration(file) }); }
    catch (e) { setPhase({ kind: "idle", error: (e as Error).message }); }
  };

  const cost = phase.kind === "ready" ? costFor(phase.seconds) : 0;
  const short = phase.kind === "ready" && cost > credits;

  const start = async () => {
    if (phase.kind !== "ready" || short) return;
    const { file } = phase;
    setPhase({ kind: "uploading", file, fraction: 0 });
    try {
      const id = await startDub(file, language, (fraction) => setPhase({ kind: "uploading", file, fraction }));
      if (!spend(cost)) throw new Error("Not enough credits.");
      const job = { id, cost, name: file.name };
      saveJob(job);
      poll(job);
    } catch (e) {
      setPhase({ kind: "failed", message: (e as Error).message });
    }
  };

  const reset = () => { stopPoll(); saveJob(null); setPhase({ kind: "idle" }); if (inputRef.current) inputRef.current.value = ""; };

  const busy = phase.kind === "uploading" || phase.kind === "processing";
  const pct = phase.kind === "uploading" ? Math.round(phase.fraction * 100) : phase.kind === "processing" ? Math.round(phase.progress) : 0;
  const stageText =
    phase.kind === "uploading"
      ? phase.fraction >= 1 ? "Waking the studio. This can take a minute." : `Uploading ${pct}%`
      : phase.kind === "processing" ? `${phase.stage} · ${pct}%` : "";

  return (
    <section className="upload" id="dub">
      <div className="smoke" aria-hidden="true" />
      <h2 className="grad-title">Ready to Go Global</h2>

      <div className="up-card">
        {phase.kind === "idle" && (
          <div
            className={`drop${dragging ? " is-drag" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files?.[0]); }}
          >
            <i className="vf vf-tl" /><i className="vf vf-tr" /><i className="vf vf-bl" /><i className="vf vf-br" />
            <p className="drop-title">Drop your MP4 here</p>
            <button type="button" className="btn-ghost" onClick={() => inputRef.current?.click()}>Choose a video</button>
            <p className="note">{phase.error ?? "MP4 up to 800 MB"}</p>
          </div>
        )}

        {phase.kind === "ready" && (
          <div className="ready">
            <p className="file" title={phase.file.name}>{phase.file.name}</p>
            <p className="note">{fmtTime(phase.seconds)} long · {(phase.file.size / 1048576).toFixed(1)} MB</p>
            <fieldset className="chips">
              <legend>Dub into</legend>
              {LANGUAGES.map((l) => (
                <label key={l.key} className={`chip${l.key === language ? " on" : ""}`}>
                  <input type="radio" name="language" value={l.key} checked={l.key === language} onChange={() => setLanguage(l.key)} />
                  <span lang={l.lang}>{l.native}</span>
                  {l.label !== l.native && <small>{l.label}</small>}
                </label>
              ))}
            </fieldset>
            <button type="button" className="btn-grad" onClick={start} disabled={short}>let&rsquo;s dub it</button>
            <p className="note">
              {short
                ? `You have ${credits} credits and this video needs ${cost}.`
                : `${cost} credits (${CREDITS_PER_MINUTE} per minute). You have ${credits}.`}
            </p>
            <button type="button" className="link" onClick={reset}>Choose another video</button>
          </div>
        )}

        {busy && (
          <div className="busy">
            <EqualizerLoader phrases={PHRASES} progress={pct / 100} />
            <p className="note" role="status">{stageText}</p>
          </div>
        )}

        {phase.kind === "failed" && (
          <div className="ready">
            <p className="drop-title">That didn&rsquo;t finish</p>
            <p className="note" role="alert">{phase.message}</p>
            <button type="button" className="btn-ghost" onClick={reset}>Try again</button>
          </div>
        )}

        {phase.kind === "done" && (
          <div className="ready">
            <p className="drop-title">Your dub is ready</p>
            <button type="button" className="btn-ghost" onClick={reset}>Dub another video</button>
          </div>
        )}
        <input ref={inputRef} type="file" accept="video/mp4,video/quicktime" hidden onChange={(e) => pick(e.target.files?.[0])} />
      </div>

      {phase.kind === "done" && (
        <div className="output">
          <h2 className="grad-title">Here it is</h2>
          <video src={phase.url} controls playsInline className="output-video" />
          <a className="btn-grad" href={phase.url} download>Download video</a>
        </div>
      )}
    </section>
  );
}
