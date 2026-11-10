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
  const headlineRef = useRef<HTMLDivElement>(null);
  const subheadRef = useRef<HTMLDivElement>(null);
  const taglineRef = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  const dirty = useRef(true);
  const { nearest, loaded } = useImageSequence();
  const onEndRef = useRef(onEnd);
  onEndRef.current = onEnd;
  const [frameReady, setFrameReady] = useState(false);

  // Wait for first frame to be actually drawable
  useEffect(() => {
    if (loaded) {
      const checkFrame = () => {
        const img = nearest(0);
        if (img?.complete && img.naturalWidth > 0) {
          setFrameReady(true);
        } else {
          requestAnimationFrame(checkFrame);
        }
      };
      checkFrame();
    }
  }, [loaded, nearest]);

  useEffect(() => {
    if (!loaded || !frameReady) return;
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
      if (!img || !img.complete || img.naturalWidth === 0) {
        // Fallback: draw solid background while frame loads
        ctx.fillStyle = "#f4f6fa";
        ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);
        return;
      }
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
      pinReparent: true, // Ensure pinned element stays in correct stacking context
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
        // Animate text reveal based on scroll progress (works both directions)
        const p = clampedProgress;

        // Headline: reveals 60% → 80%, rises from 40px to 0, fades 0→1
        if (headlineRef.current) {
          if (p >= 0.60) {
            const t = Math.min((p - 0.60) / 0.20, 1);
            headlineRef.current.style.opacity = String(t);
            headlineRef.current.style.transform = `translateY(${40 - 40 * t}px)`;
          } else {
            headlineRef.current.style.opacity = "0";
            headlineRef.current.style.transform = "translateY(40px)";
          }
        }

        // Subhead: reveals 70% → 85%, rises from 30px to 0, fades 0→1
        if (subheadRef.current) {
          if (p >= 0.70) {
            const t = Math.min((p - 0.70) / 0.15, 1);
            subheadRef.current.style.opacity = String(t);
            subheadRef.current.style.transform = `translateY(${30 - 30 * t}px)`;
          } else {
            subheadRef.current.style.opacity = "0";
            subheadRef.current.style.transform = "translateY(30px)";
          }
        }

        // Tagline: reveals 85% → 95%, rises from 20px to 0, fades 0→1
        if (taglineRef.current) {
          if (p >= 0.85) {
            const t = Math.min((p - 0.85) / 0.10, 1);
            taglineRef.current.style.opacity = String(t);
            taglineRef.current.style.transform = `translateY(${20 - 20 * t}px)`;
          } else {
            taglineRef.current.style.opacity = "0";
            taglineRef.current.style.transform = "translateY(20px)";
          }
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
  }, [loaded, frameReady, nearest]);

  // Render loading state until first frame is ready
  if (!frameReady) {
    return (
      <div ref={sectionRef} className="hero" style={{ background: "#f4f6fa" }}>
        <h1 className="sr-only">Echofy: dub your video into any language</h1>
        <canvas ref={canvasRef} className="hero-canvas" aria-label="Echofy: a listener with headphones" role="img" style={{ background: "#f4f6fa" }} />
        <p className="hero-tag" aria-hidden="true">Dub once. Be heard in every language.</p>
        <div ref={cueRef} className="hero-cue" aria-hidden="true">
          <span>Scroll</span>
          <i />
        </div>
      </div>
    );
  }

  return (
    <div ref={sectionRef} className="hero" style={{ zIndex: 10, position: "relative" }}>
      <h1 className="sr-only">Echofy: dub your video into any language</h1>
      <canvas ref={canvasRef} className="hero-canvas" aria-label="Echofy: a listener with headphones" role="img" style={{ background: "#f4f6fa" }} />

      {/* Scroll-reveal text layers - higher z-index than Studio */}
      <div
        ref={headlineRef}
        className="hero-headline"
        aria-hidden="true"
        style={{
          opacity: 0,
          transform: "translateY(40px)",
          transition: "opacity 0.4s ease-out, transform 0.4s ease-out",
          zIndex: 20,
          position: "relative",
        }}
      >
        <p className="hero-headline-label">Dub once.</p>
        <h2 className="hero-headline-main">Be heard in every language.</h2>
      </div>

      <div
        ref={subheadRef}
        className="hero-subhead"
        aria-hidden="true"
        style={{
          opacity: 0,
          transform: "translateY(30px)",
          transition: "opacity 0.4s ease-out, transform 0.4s ease-out",
          zIndex: 20,
          position: "relative",
        }}
      >
        <p>Your video. Every voice. Any language.</p>
      </div>

      <div
        ref={taglineRef}
        className="hero-tagline"
        aria-hidden="true"
        style={{
          opacity: 0,
          transform: "translateY(20px)",
          transition: "opacity 0.4s ease-out, transform 0.4s ease-out",
          zIndex: 20,
          position: "relative",
        }}
      >
        <p>Original music preserved · Distinct voices · Studio quality</p>
      </div>

      <p className="hero-tag" aria-hidden="true">Dub once. Be heard in every language.</p>
      <div ref={cueRef} className="hero-cue" aria-hidden="true">
        <span>Scroll</span>
        <i />
      </div>
    </div>
  );
}