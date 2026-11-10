"use client";
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useImageSequence } from "@/hooks/useImageSequence";
import { FRAME_COUNT } from "@/lib/media";

gsap.registerPlugin(ScrollTrigger);

export default function HeroCanvas({ onEnd }: { onEnd: () => void }) {
  const sectionRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cueRef = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  const dirty = useRef(true);
  const { nearest, loaded, allLoaded } = useImageSequence();
  const onEndRef = useRef(onEnd);
  onEndRef.current = onEnd;
  const [ready, setReady] = useState(false);

  // Wait for all frames to be loaded before enabling scroll scrub
  useEffect(() => {
    if (allLoaded) setReady(true);
  }, [allLoaded]);

  useEffect(() => {
    if (!loaded || !ready) return;
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
      if (!img || !img.complete || img.naturalWidth === 0) return;
      const cw = window.innerWidth, ch = window.innerHeight;
      const iw = img.naturalWidth, ih = img.naturalHeight;
      if (cw < ch && iw > ih) {
        // Portrait: show full frame at bottom with blurred top extension
        const dh = (ih * cw) / iw, y = ch - dh;
        ctx.save();
        ctx.filter = "blur(10px)";
        ctx.drawImage(img, 0, 0, iw, 2, -20, -20, cw + 40, y + 22);
        ctx.restore();
        ctx.drawImage(img, 0, y, cw, dh);
        return;
      }
      const scale = Math.max(cw / iw, ch / ih);
      const dw = iw * scale, dh = ih * scale;
      ctx.drawImage(img, (cw - dw) / 2, (ch - dh) / 2, dw, dh);
    };

    const loop = () => {
      if (dirty.current) { draw(); dirty.current = false; }
      raf = requestAnimationFrame(loop);
    };

    // Draw frame 0 immediately
    size();
    draw();
    raf = requestAnimationFrame(loop);

    // Pin distance: 400vh for 300 frames = smooth Apple feel
    // pinSpacing: true creates spacer below pin → next section (Studio) sits in that space
    const PIN_VH = 400;

    const trigger = ScrollTrigger.create({
      trigger: sectionRef.current,
      start: "top top",
      end: `+=${PIN_VH}%`,
      pin: true,
      pinSpacing: true,
      scrub: true,
      anticipatePin: 1,
      onUpdate: (self) => {
        const clampedProgress = Math.max(0, Math.min(1, self.progress));
        const idx = Math.floor(clampedProgress * FRAME_COUNT);
        const safeIdx = Math.max(0, Math.min(FRAME_COUNT - 1, idx));
        if (safeIdx !== frame.current) {
          frame.current = safeIdx;
          dirty.current = true;
        }
        // Fade out scroll cue by ~93% progress
        if (cueRef.current) {
          const cueProgress = Math.max(0, 1 - clampedProgress / 0.93);
          cueRef.current.style.opacity = String(cueProgress);
        }
        // Fire onEnd at last frame (99.5% progress)
        if (safeIdx === FRAME_COUNT - 1 && clampedProgress >= 0.995) {
          onEndRef.current();
        }
      },
      onLeave: () => {
        // Pin released - normal scroll resumes
      },
    });

    const onResize = () => { size(); ScrollTrigger.refresh(); };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(raf);
      trigger.kill();
    };
  }, [loaded, ready, nearest]);

  return (
    <div ref={sectionRef} className="hero">
      <h1 className="sr-only">Echofy: dub your video into any language</h1>
      <canvas ref={canvasRef} className="hero-canvas" aria-label="Echofy: a listener with headphones" role="img" />
      <p className="hero-tag" aria-hidden="true">Dub once. Be heard in every language.</p>
      <div ref={cueRef} className="hero-cue" aria-hidden="true">
        <span>Scroll</span>
        <i />
      </div>
    </div>
  );
}