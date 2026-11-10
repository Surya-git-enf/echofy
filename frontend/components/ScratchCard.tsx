"use client";
import { useEffect, useRef, useState } from "react";
import { claimWelcome } from "@/lib/credits";

const SIZE = 700; // internal canvas resolution
const BRUSH = 40;
// The glitter panel inside the poster, as fractions of the image. Progress is measured here.
const PANEL = { x0: 0.24, x1: 0.76, y0: 0.34, y1: 0.84 };
const REVEAL_AT = 0.45;

export default function ScratchCard({ onClose }: { onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const lastCheck = useRef(0);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const c = canvasRef.current!;
    const ctx = c.getContext("2d")!;
    const img = new Image();
    img.onload = () => ctx.drawImage(img, 0, 0, SIZE, SIZE);
    img.src = "/scratch/cover.webp";
  }, []);

  const reveal = () => {
    setRevealed((r) => {
      if (!r) claimWelcome();
      return true;
    });
  };

  const cleared = () => {
    const ctx = canvasRef.current!.getContext("2d")!;
    const x = Math.floor(PANEL.x0 * SIZE), y = Math.floor(PANEL.y0 * SIZE);
    const w = Math.floor((PANEL.x1 - PANEL.x0) * SIZE), h = Math.floor((PANEL.y1 - PANEL.y0) * SIZE);
    const d = ctx.getImageData(x, y, w, h).data;
    let clear = 0, total = 0;
    for (let i = 3; i < d.length; i += 4 * 9) { total++; if (d[i] < 128) clear++; }
    return clear / total;
  };

  const scratch = (e: React.PointerEvent) => {
    const c = canvasRef.current!;
    const r = c.getBoundingClientRect();
    const x = ((e.clientX - r.left) * SIZE) / r.width;
    const y = ((e.clientY - r.top) * SIZE) / r.height;
    const ctx = c.getContext("2d")!;
    ctx.globalCompositeOperation = "destination-out";
    ctx.lineWidth = BRUSH * 2;
    ctx.lineCap = "round";
    ctx.beginPath();
    const from = last.current ?? { x, y };
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(x, y);
    ctx.stroke();
    last.current = { x, y };
    const now = performance.now();
    if (now - lastCheck.current > 250) {
      lastCheck.current = now;
      if (cleared() >= REVEAL_AT) reveal();
    }
  };

  return (
    <div className="scratch" role="dialog" aria-modal="true" aria-label="Your welcome gift">
      <div className="scratch-box">
        <img src="/scratch/won.webp" alt="100 credits won" className="scratch-img" />
        <canvas
          ref={canvasRef}
          width={SIZE}
          height={SIZE}
          className={`scratch-cover${revealed ? " is-gone" : ""}`}
          onPointerDown={(e) => { drawing.current = true; last.current = null; e.currentTarget.setPointerCapture(e.pointerId); scratch(e); }}
          onPointerMove={(e) => { if (drawing.current) scratch(e); }}
          onPointerUp={() => { drawing.current = false; last.current = null; if (cleared() >= REVEAL_AT) reveal(); }}
          onPointerCancel={() => { drawing.current = false; last.current = null; }}
        />
        {revealed && (
          <button type="button" className="scratch-claim" onClick={onClose} aria-label="Claim now: 100 credits added" />
        )}
        <button type="button" className="scratch-close" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
      {!revealed && (
        <button type="button" className="scratch-skip" onClick={reveal}>Reveal without scratching</button>
      )}
    </div>
  );
}
