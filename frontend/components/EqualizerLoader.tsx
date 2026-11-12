"use client";
import { useEffect, useState } from "react";

const PILLS = 25;

/**
 * Equalizer loader. With `progress` (0..1) each pill turns solid black in turn, so the bar
 * reads as a real progress meter. Without it the pills just pulse at half opacity.
 */
export default function EqualizerLoader({ progress, phrases, caption, showPercent }: { progress?: number; phrases?: string[]; caption?: string; showPercent?: boolean }) {
  const [i, setI] = useState(0);

  useEffect(() => {
    if (!phrases || phrases.length < 2) return;
    const t = window.setInterval(() => setI((n) => (n + 1) % phrases.length), 2600);
    return () => window.clearInterval(t);
  }, [phrases]);

  const lit = progress === undefined ? 0 : Math.round(Math.min(1, Math.max(0, progress)) * PILLS);

  return (
    <div
      className="eql"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={progress === undefined ? undefined : Math.round(progress * 100)}
    >
      <div className="eql-bars" aria-hidden="true">
        {Array.from({ length: PILLS }, (_, n) => {
          const edge = Math.abs(n - 12) / 12; // 0 centre .. 1 edges
          return (
            <span
              key={n}
              className={`eql-pill${n < lit ? " is-on" : ""}${progress === undefined ? " is-idle" : ""}`}
              style={{
                animationDelay: `${(n % 7) * 0.09}s`,
                animationDuration: `${0.9 + ((n * 37) % 10) / 10}s`,
                ["--lo" as string]: String(0.18 + edge * 0.1),
                ["--hi" as string]: String(0.55 + edge * 0.45),
              }}
            />
          );
        })}
      </div>
      {showPercent && progress !== undefined && (
        <p className="eql-pct" aria-hidden="true">{Math.round(Math.min(1, Math.max(0, progress)) * 100)}%</p>
      )}
      <p className="eql-phrase" key={i} aria-live="polite">{phrases ? phrases[i] : caption}</p>
    </div>
  );
}
