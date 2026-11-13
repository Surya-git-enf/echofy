"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useImageSequence } from "@/hooks/useImageSequence";
import { FRAME_COUNT } from "@/lib/media";

gsap.registerPlugin(ScrollTrigger);

const PIN_VH = 400;       // scroll distance the hero is pinned for
const FOLLOW = 9;         // how quickly the picture chases the scroll position (higher = snappier)
const BG = "#f4f6fa";

// Text layers reveal over a slice of the scroll: [start, end, rise in px]
const LAYERS = [
  { key: "headline", from: 0.6, to: 0.8, rise: 40 },
  { key: "subhead", from: 0.7, to: 0.85, rise: 30 },
  { key: "tagline", from: 0.85, to: 0.95, rise: 20 },
] as const;

export default function HeroCanvas({ onEnd }: { onEnd: () => void }) {
  const sectionRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cueRef = useRef<HTMLDivElement>(null);
  const layerRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const { nearest, loaded } = useImageSequence();
  const onEndRef = useRef(onEnd);
  onEndRef.current = onEnd;

  useEffect(() => {
    if (!loaded) return;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let target = 0;   // frame position the scroll is asking for (fractional)
    let current = 0;  // frame position on screen, eased towards target
    let drawn = -1;
    let ended = false;
    let raf = 0;
    let last = performance.now();

    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(window.innerWidth * dpr);
      canvas.height = Math.round(window.innerHeight * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawn = -1;
    };

    const paint = (img: HTMLImageElement, alpha: number) => {
      const cw = window.innerWidth, ch = window.innerHeight;
      const iw = img.naturalWidth, ih = img.naturalHeight;
      ctx.globalAlpha = alpha;
      if (cw < ch && iw > ih) {
        // Portrait: whole frame at the bottom, its top edge blurred upwards to fill the screen.
        const dh = (ih * cw) / iw, y = ch - dh;
        ctx.save();
        ctx.filter = "blur(10px)";
        ctx.drawImage(img, 0, 0, iw, 2, -20, -20, cw + 40, y + 22);
        ctx.restore();
        ctx.drawImage(img, 0, y, cw, dh);
      } else {
        const scale = Math.max(cw / iw, ch / ih);
        const dw = iw * scale, dh = ih * scale;
        ctx.drawImage(img, (cw - dw) / 2, (ch - dh) / 2, dw, dh);
      }
      ctx.globalAlpha = 1;
    };

    // Draws a position between two frames by cross-fading them, so slow scrolling glides
    // instead of stepping from one picture to the next.
    const draw = (pos: number) => {
      const a = Math.floor(pos);
      const t = pos - a;
      const imgA = nearest(a);
      ctx.fillStyle = BG;
      ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);
      if (!imgA) return;
      paint(imgA, 1);
      if (t > 0.02 && a + 1 < FRAME_COUNT) {
        const imgB = nearest(a + 1);
        if (imgB && imgB !== imgA) paint(imgB, t);
      }
    };

    const reveal = (p: number) => {
      LAYERS.forEach(({ key, from, to, rise }) => {
        const el = layerRefs.current[key];
        if (!el) return;
        const t = Math.min(1, Math.max(0, (p - from) / (to - from)));
        const e = 1 - Math.pow(1 - t, 3);
        el.style.opacity = String(e);
        el.style.transform = `translate3d(0, ${((1 - e) * rise).toFixed(1)}px, 0)`;
      });
      if (cueRef.current) cueRef.current.style.opacity = String(Math.max(0, 1 - p / 0.93));
    };

    const loop = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const gap = target - current;
      current = reduced || Math.abs(gap) < 0.002 ? target : current + gap * (1 - Math.exp(-FOLLOW * dt));
      if (current !== drawn) {
        draw(current);
        reveal(current / (FRAME_COUNT - 1));
        drawn = current;
      }
      raf = requestAnimationFrame(loop);
    };

    size();
    reveal(0);
    raf = requestAnimationFrame(loop);

    const trigger = ScrollTrigger.create({
      trigger: sectionRef.current,
      start: "top top",
      end: `+=${PIN_VH}%`,
      pin: true,
      pinSpacing: true,
      scrub: true,
      anticipatePin: 1,
      refreshPriority: 2, // measured before the sections below, which sit in this pin's spacer
      onUpdate: (self) => {
        const p = Math.max(0, Math.min(1, self.progress));
        target = p * (FRAME_COUNT - 1);
        if (!ended && p >= 0.995) { ended = true; onEndRef.current(); }
      },
    });

    window.addEventListener("resize", size);
    return () => {
      window.removeEventListener("resize", size);
      cancelAnimationFrame(raf);
      trigger.kill(true);
    };
  }, [loaded, nearest]);

  const setLayer = (key: string) => (el: HTMLDivElement | null) => { layerRefs.current[key] = el; };

  return (
    <div ref={sectionRef} className="hero">
      <h1 className="sr-only">Echofy: dub your video into any language</h1>
      <canvas ref={canvasRef} className="hero-canvas" aria-label="Echofy: a listener with headphones" role="img" />

      <div className="hero-copy" aria-hidden="true">
        <div className="hero-headline">
          <div ref={setLayer("headline")} className="hero-rise">
            <p className="hero-headline-label">Dub once.</p>
            <h2 className="hero-headline-main">Be heard in every language.</h2>
          </div>
        </div>
        <div className="hero-subhead">
          <div ref={setLayer("subhead")} className="hero-rise">
            <p>Your video. Every voice. Any language.</p>
          </div>
        </div>
        <div className="hero-tagline">
          <div ref={setLayer("tagline")} className="hero-rise">
            <p>Original music preserved · Distinct voices · Studio quality</p>
          </div>
        </div>
      </div>

      <p className="hero-tag" aria-hidden="true">Dub once. Be heard in every language.</p>
      <div ref={cueRef} className="hero-cue" aria-hidden="true">
        <span>Scroll</span>
        <i />
      </div>
    </div>
  );
}
