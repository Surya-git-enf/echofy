"use client";
import { useEffect, useState } from "react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { PRELOAD_IMAGES } from "@/lib/media";
import { reportLoad, useLoadProgress } from "@/lib/loadProgress";
import { setScrollLocked } from "@/lib/smoothScroll";
import EqualizerLoader from "./EqualizerLoader";

const GIVE_UP_MS = 30000; // slow connections: show the page anyway after this long

/** Preloads all non-frame assets: images and fonts. */
function usePreloadAssets() {
  useEffect(() => {
    let alive = true;

    let assetsDone = 0;
    const assetTotal = PRELOAD_IMAGES.length + 1; // images + fonts
    const assetStep = () => { assetsDone++; if (alive) reportLoad("assets", assetsDone / assetTotal); };
    PRELOAD_IMAGES.forEach((src) => {
      const img = new Image();
      img.onload = img.onerror = assetStep;
      img.src = src;
    });
    (document.fonts ? document.fonts.ready : Promise.resolve()).then(assetStep, assetStep);

    // Videos stream in lazily as their sections near the screen, so the loader never waits on them.
    reportLoad("videos", 1);

    return () => { alive = false; };
  }, []);
}

export default function PageLoader() {
  const progress = useLoadProgress();
  const [gone, setGone] = useState(false);
  const [leaving, setLeaving] = useState(false);
  usePreloadAssets();

  useEffect(() => {
    const t = window.setTimeout(() => setLeaving(true), GIVE_UP_MS);
    return () => window.clearTimeout(t);
  }, []);

  // Frames (70%) + assets (20%) + videos (10%): the page opens when all of it has arrived.
  const finished = progress >= 0.999 || leaving;

  useEffect(() => {
    document.documentElement.style.overflow = gone ? "" : "hidden";
    setScrollLocked(!gone);
    return () => { document.documentElement.style.overflow = ""; setScrollLocked(false); };
  }, [gone]);

  useEffect(() => {
    if (!finished) return;
    const t = window.setTimeout(() => {
      setGone(true);
      ScrollTrigger.refresh();
    }, 500);
    return () => window.clearTimeout(t);
  }, [finished]);

  if (gone) return null;
  return (
    <div className={`page-loader${finished ? " is-done" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
      <EqualizerLoader progress={progress} showPercent />
    </div>
  );
}