"use client";
import { useEffect, useRef, useState } from "react";
import { SHOWCASE_VIDEOS } from "@/lib/media";
import SoundToggle from "./SoundToggle";

const STEP = 360 / SHOWCASE_VIDEOS.length;

type ReelProps = {
  video: (typeof SHOWCASE_VIDEOS)[number];
  index: number;
  radius: number;
  moved: React.RefObject<number>;
  onHover: (on: boolean) => void;
};

function Reel({ video, index, radius, moved, onHover }: ReelProps) {
  const ref = useRef<HTMLVideoElement>(null);

  const enter = (e: React.PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    onHover(true);
    ref.current?.play().catch(() => {});
  };
  const leave = (e: React.PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    onHover(false);
    if (ref.current?.muted) ref.current.pause(); // a video you turned sound on for keeps playing
  };
  const click = () => {
    if (moved.current > 6) return; // that was a drag, not a tap
    const v = ref.current;
    if (!v) return;
    if (v.paused) v.play().catch(() => {});
    else v.pause();
  };

  return (
    <div
      className="reel"
      style={{ transform: `rotateY(${index * STEP}deg) translateZ(${radius}px)` }}
      onPointerEnter={enter}
      onPointerLeave={leave}
      onClick={click}
    >
      <video ref={ref} src={video.src} muted loop playsInline preload="metadata" aria-label={video.label} />
      <SoundToggle videoRef={ref} />
    </div>
  );
}

export default function SpiralShowcase() {
  const ring = useRef<HTMLDivElement>(null);
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
      const el = ring.current;
      if (el) {
        el.style.transform = `translateZ(${-radius}px) rotateX(-4deg) rotateY(${rot.current}deg)`;
        // Depth cue: reels fade into a rose shade as they swing round to the back.
        Array.from(el.children).forEach((child, i) => {
          const facing = Math.cos(((i * STEP + rot.current) * Math.PI) / 180); // 1 front .. -1 back
          (child as HTMLElement).style.setProperty("--shade", ((1 - facing) / 2).toFixed(3));
        });
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [radius]);

  return (
    <section className="showcase" id="showcase">
      <h2 className="section-title">Hear the difference</h2>
      <p className="showcase-note">Hover or tap a video to play it. Tap the speaker for sound. Drag to spin.</p>
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
            <Reel key={v.id} video={v} index={i} radius={radius} moved={moved} onHover={(on) => { hovering.current = on; }} />
          ))}
        </div>
      </div>
    </section>
  );
}
