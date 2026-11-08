"use client";
import { useEffect, useRef } from "react";
import EchoMark from "./EchoMark";

const BLUE_TOP = "#1EB0E8";
const BLUE_BOTTOM = "#007BA7";
const ROSE = "#FF2D95";

/** Blue pills that rise and fall; about 30% pick up a neon rose gradient at random. */
export default function EqualizerBand() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, n = 0, pillW = 10, gap = 6;
    let cur: number[] = [], tgt: number[] = [], rose: boolean[] = [];
    let raf = 0, nextPick = 0;

    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      pillW = w < 600 ? 6 : 10; gap = w < 600 ? 4 : 6;
      n = Math.floor((w + gap) / (pillW + gap));
      cur = Array.from({ length: n }, () => Math.random());
      tgt = cur.slice();
      rose = Array.from({ length: n }, () => Math.random() < 0.3);
    };

    const draw = (t: number) => {
      if (t > nextPick && !reduced) {
        nextPick = t + 160;
        for (let i = 0; i < n; i++) if (Math.random() < 0.35) { tgt[i] = 0.12 + Math.random() * 0.88; rose[i] = Math.random() < 0.3; }
      }
      ctx.clearRect(0, 0, w, h);
      const total = n * (pillW + gap) - gap;
      const x0 = (w - total) / 2;
      for (let i = 0; i < n; i++) {
        if (!reduced) cur[i] += (tgt[i] - cur[i]) * 0.14;
        const ph = Math.max(pillW, cur[i] * h * 0.92);
        const x = x0 + i * (pillW + gap), y = (h - ph) / 2;
        const g = ctx.createLinearGradient(0, y, 0, y + ph);
        if (rose[i]) { g.addColorStop(0, ROSE); g.addColorStop(1, BLUE_TOP); }
        else { g.addColorStop(0, BLUE_TOP); g.addColorStop(1, BLUE_BOTTOM); }
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.roundRect(x, y, pillW, ph, pillW / 2);
        ctx.fill();
      }
      if (!reduced) raf = requestAnimationFrame(draw);
    };

    size();
    raf = requestAnimationFrame(draw);
    const onResize = () => { size(); if (reduced) draw(0); };
    window.addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); };
  }, []);

  return (
    <div className="eq-band" aria-hidden="true">
      <canvas ref={ref} />
      <EchoMark animated className="eq-band-mark" />
    </div>
  );
}
