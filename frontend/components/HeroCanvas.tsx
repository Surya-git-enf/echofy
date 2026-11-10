"use client";
import { useEffect, useRef } from "react";
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
  const { nearest, loaded } = useImageSequence();
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
      const iw = img.naturalWidth, ih = img.naturalHeight;
      if (cw < ch && iw > ih) {
        // Portrait phone with 16:9 frames: show the whole frame (headline included) along the
        // bottom edge and extend its soft top row upward. Vertical frames would fill the screen.
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

    const trigger = ScrollTrigger.create({
      trigger: sectionRef.current,
      start: "top top",
      end: "+=300%",
      pin: true,
      scrub: true,
      onUpdate: (self) => {
        const idx = Math.round(self.progress * (FRAME_COUNT - 1));
        if (idx !== frame.current) { frame.current = idx; }
        dirty.current = true;
        if (cueRef.current) cueRef.current.style.opacity = String(Math.max(0, 1 - self.progress * 14));
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
