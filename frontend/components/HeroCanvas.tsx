"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useImageSequence } from "@/hooks/useImageSequence";
import { FRAME_COUNT } from "@/lib/media";
import EqualizerLoader from "./EqualizerLoader";
import EqualizerBand from "./EqualizerBand";

gsap.registerPlugin(ScrollTrigger);

export default function HeroCanvas({ onEnd }: { onEnd: () => void }) {
  const sectionRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const bandRef = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  const progressRef = useRef(0);
  const dirty = useRef(true);
  const { nearest, loaded, progress } = useImageSequence();
  const onEndRef = useRef(onEnd);
  onEndRef.current = onEnd;

  useEffect(() => {
    if (!loaded) return;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;

    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      dirty.current = true;
    };

    const draw = () => {
      const img = nearest(frame.current);
      if (!img) return;
      const cw = window.innerWidth, ch = window.innerHeight;
      const scale = Math.max(cw / img.naturalWidth, ch / img.naturalHeight);
      const dw = img.naturalWidth * scale, dh = img.naturalHeight * scale;
      // On portrait screens follow the subject, who drifts to the right as the shot ends.
      const anchor = cw < ch && img.naturalWidth > img.naturalHeight ? 0.4 + 0.3 * progressRef.current : 0.5;
      ctx.drawImage(img, (cw - dw) * anchor, (ch - dh) / 2, dw, dh);
    };

    const loop = () => {
      if (dirty.current) { draw(); dirty.current = false; }
      raf = requestAnimationFrame(loop);
    };

    size();
    raf = requestAnimationFrame(loop);

    const trigger = ScrollTrigger.create({
      trigger: sectionRef.current,
      start: "top top",
      end: "+=400%",
      pin: true,
      scrub: true,
      onUpdate: (self) => {
        progressRef.current = self.progress;
        const idx = Math.round(self.progress * (FRAME_COUNT - 1));
        if (idx !== frame.current) { frame.current = idx; }
        dirty.current = true;
        if (bandRef.current) {
          const fade = Math.min(1, Math.max(0, (0.85 - self.progress) / 0.15));
          bandRef.current.style.opacity = String(fade);
        }
        if (self.progress >= 0.985) onEndRef.current();
      },
    });

    const onResize = () => { size(); ScrollTrigger.refresh(); };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(raf);
      trigger.kill();
    };
  }, [loaded, nearest]);

  return (
    <div ref={sectionRef} className="hero">
      {!loaded && (
        <div className="hero-loading">
          <EqualizerLoader caption={`Warming up ${Math.round(progress * 100)}%`} />
        </div>
      )}
      <h1 className="sr-only">Echofy: dub your video into any language</h1>
      <canvas ref={canvasRef} className="hero-canvas" aria-label="Echofy: a listener with headphones" role="img" />
      <div ref={bandRef} className="hero-band">
        <EqualizerBand />
      </div>
    </div>
  );
}
