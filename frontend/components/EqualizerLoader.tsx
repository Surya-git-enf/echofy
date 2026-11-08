"use client";
import { useEffect, useState } from "react";
import EchoMark from "./EchoMark";

const PILLS = 25; // the middle 5 are replaced by the logo curves

export default function EqualizerLoader({ phrases, caption }: { phrases?: string[]; caption?: string }) {
  const [i, setI] = useState(0);

  useEffect(() => {
    if (!phrases || phrases.length < 2) return;
    const t = window.setInterval(() => setI((n) => (n + 1) % phrases.length), 2600);
    return () => window.clearInterval(t);
  }, [phrases]);

  return (
    <div className="eql" role="status" aria-live="polite">
      <div className="eql-bars" aria-hidden="true">
        {Array.from({ length: PILLS }, (_, n) => {
          const middle = n >= 10 && n <= 14;
          const edge = Math.abs(n - 12) / 12; // 0 centre .. 1 edges
          return (
            <span
              key={n}
              className={`eql-pill${middle ? " is-hidden" : ""}`}
              style={{
                animationDelay: `${(n % 7) * 0.09}s`,
                animationDuration: `${0.9 + ((n * 37) % 10) / 10}s`,
                ["--lo" as string]: String(0.18 + edge * 0.1),
                ["--hi" as string]: String(0.55 + edge * 0.45),
              }}
            />
          );
        })}
        <EchoMark color="#000" className="eql-mark" />
      </div>
      <p className="eql-phrase" key={i}>{phrases ? phrases[i] : caption}</p>
    </div>
  );
}
