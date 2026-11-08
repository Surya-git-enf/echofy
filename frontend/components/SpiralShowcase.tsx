"use client";
import { useEffect, useRef, useState } from "react";
import { SHOWCASE_VIDEOS } from "@/lib/media";

const STEP = 360 / SHOWCASE_VIDEOS.length;

export default function SpiralShowcase() {
  const ring = useRef<HTMLDivElement>(null);
  const videos = useRef<(HTMLVideoElement | null)[]>([]);
  const rot = useRef(0);
  const hovering = useRef(false);
  const dragging = useRef(false);
  const lastX = useRef(0);
  const moved = useRef(0);
  const [radius, setRadius] = useState(300);

  useEffect(() => {
    const fit = () => setRadius(window.innerWidth < 640 ? 210 : 300);
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let last = performance.now();
    const loop = (t: number) => {
      const dt = Math.min(0.05, (t - last) / 1000);
      last = t;
      if (!hovering.current && !dragging.current && !reduced) rot.current -= 12 * dt;
      if (ring.current) ring.current.style.transform = `translateZ(${-radius}px) rotateX(-4deg) rotateY(${rot.current}deg)`;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [radius]);

  const enter = (i: number, e: React.PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    hovering.current = true;
    videos.current[i]?.play().catch(() => {});
  };
  const leave = (i: number, e: React.PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    hovering.current = false;
    videos.current[i]?.pause();
  };
  const click = (i: number) => {
    if (moved.current > 6) return;
    const v = videos.current[i];
    if (!v) return;
    if (v.paused) { hovering.current = true; v.play().catch(() => {}); }
    else v.muted = !v.muted; // hover plays muted; a click turns sound on or off
  };

  return (
    <section className="showcase" id="showcase">
      <h2 className="grad-title">Hear the difference</h2>
      <p className="showcase-note">Hover a video to play it. Drag to spin. Click to turn sound on.</p>
      <div
        className="orbit"
        onPointerDown={(e) => { dragging.current = true; moved.current = 0; lastX.current = e.clientX; }}
        onPointerMove={(e) => {
          if (!dragging.current) return;
          const dx = e.clientX - lastX.current;
          moved.current += Math.abs(dx);
          rot.current += dx * 0.35;
          lastX.current = e.clientX;
        }}
        onPointerUp={() => { dragging.current = false; }}
        onPointerLeave={() => { dragging.current = false; }}
      >
        <div ref={ring} className="orbit-ring">
          {SHOWCASE_VIDEOS.map((v, i) => (
            <div
              key={v.id}
              className="reel"
              style={{ transform: `rotateY(${i * STEP}deg) translateZ(${radius}px)` }}
              onPointerEnter={(e) => enter(i, e)}
              onPointerLeave={(e) => leave(i, e)}
              onClick={() => click(i)}
            >
              <video
                ref={(el) => { videos.current[i] = el; }}
                src={v.src}
                muted
                loop
                playsInline
                preload="metadata"
                aria-label={v.label}
              />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
