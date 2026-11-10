"use client";
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useImageSequence } from "@/hooks/useImageSequence";
import { FRAME_COUNT, FRAMES_DIR, frameSrc } from "@/lib/media";

gsap.registerPlugin(ScrollTrigger);

export default function HeroCanvas({ onEnd }: { onEnd: () => void }) {
  const sectionRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cueRef = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  const dirty = useRef(true);
  const { nearest, loaded, progress: loadProgress } = useImageSequence();
  const onEndRef = useRef(onEnd);
  onEndRef.current = onEnd;
  const [allFramesReady, setAllFramesReady] = useState(false);

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
      const iw = img.naturalWidth, ih = img.naturalHeight;
      if (cw < ch && iw > ih) {
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

    size();
    raf = requestAnimationFrame(loop);

    // Track when all frames are actually loaded
    const checkAllLoaded = setInterval(() => {
      const allLoaded = Array.from({ length: FRAME_COUNT }, (_, i) => nearest(i)).every(Boolean);
      if (allLoaded) {
        clearInterval(checkAllLoaded);
        setAllFramesReady(true);
      }
    }, 100);

    // Pin distance: 300 frames → ~300vh for 1:1 frame-per-vh feel on desktop
    // This gives ~1 frame per 1% viewport scroll = smooth Apple feel
    const PIN_VH = 300;

    const trigger = ScrollTrigger.create({
      trigger: sectionRef.current,
      start: "top top",
      end: `+=${PIN_VH}%`,
      pin: true,
      pinSpacing: true,
      scrub: true,
      anticipatePin: 1,
      onUpdate: (self) => {
        // Clamp progress to [0, 1] for exact frame mapping
        const clampedProgress = Math.max(0, Math.min(1, self.progress));
        // Exact frame index: 0 to FRAME_COUNT-1 (300 frames = indices 0-299)
        const idx = Math.floor(clampedProgress * FRAME_COUNT);
        const safeIdx = Math.max(0, Math.min(FRAME_COUNT - 1, idx));
        if (safeIdx !== frame.current) {
          frame.current = safeIdx;
          dirty.current = true;
        }
        // Fade out scroll cue by frame ~280 (93%)
        if (cueRef.current) {
          const cueProgress = Math.max(0, 1 - clampedProgress / 0.93);
          cueRef.current.style.opacity = String(cueProgress);
        }
        // Fire onEnd exactly at last frame (index 299 = frame 300)
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
      clearInterval(checkAllLoaded);
      cancelAnimationFrame(raf);
      trigger.kill();
    };
  }, [loaded, nearest]);

  // Show subtle loading indicator until all frames ready
  if (!allFramesReady) {
    return (
      <div ref={sectionRef} className="hero">
        <h1 className="sr-only">Echofy: dub your video into any language</h1>
        <canvas ref={canvasRef} className="hero-canvas" aria-label="Echofy: a listener with headphones" role="img" />
        <p className="hero-tag" aria-hidden="true">Dub once. Be heard in every language.</p>
        <div ref={cueRef} className="hero-cue" aria-hidden="true">
          <span>Scroll</span>
          <i />
        </div>
        <div className="hero-load-indicator" aria-hidden="true">
          <span>Preparing frames… {Math.round(loadProgress * 100)}%</span>
        </div>
      </div>
    );
  }

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