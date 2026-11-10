"use client";
import { useEffect, useState } from "react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { LANGUAGE_VIDEO, PRELOAD_IMAGES, SHOWCASE_VIDEOS } from "@/lib/media";
import { reportLoad, useLoadProgress } from "@/lib/loadProgress";
import EqualizerLoader from "./EqualizerLoader";

const GIVE_UP_MS = 15000; // longer for mobile

/** Preloads all non-frame assets: images, fonts, video metadata. */
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

    const sources = Array.from(new Set([LANGUAGE_VIDEO, ...SHOWCASE_VIDEOS.map((v) => v.src)]));
    let videosDone = 0;
    const holders = sources.map((src) => {
      const v = document.createElement("video");
      v.preload = "metadata";
      v.muted = true;
      const step = () => { videosDone++; if (alive) reportLoad("videos", videosDone / sources.length); };
      v.onloadedmetadata = v.onerror = step;
      v.src = src;
      return v;
    });

    return () => { alive = false; holders.forEach((v) => { v.removeAttribute("src"); v.load(); }); };
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

  const finished = progress >= 0.999 || leaving;

  useEffect(() => {
    document.documentElement.style.overflow = gone ? "" : "hidden";
    return () => { document.documentElement.style.overflow = ""; };
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
      <EqualizerLoader progress={progress} />
    </div>
  );
}