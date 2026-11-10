"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { reportLoad } from "@/lib/loadProgress";
import { FRAME_COUNT, FRAMES_DIR, MOBILE_FRAMES_DIR, frameSrc } from "@/lib/media";

const FIRST_BATCH = 100;

/**
 * Loads the hero frames in two stages: the first 100 block the page loader, the rest
 * stream in behind it. `nearest(i)` returns the closest already-loaded frame at or
 * before i, so scrolling fast never shows a blank canvas.
 */
export function useImageSequence() {
  const images = useRef<(HTMLImageElement | null)[]>(new Array(FRAME_COUNT).fill(null));
  const [loaded, setLoaded] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let done = 0;
    const dir = MOBILE_FRAMES_DIR && window.innerWidth < window.innerHeight ? MOBILE_FRAMES_DIR : FRAMES_DIR;

    const load = (i: number) =>
      new Promise<void>((resolve) => {
        const img = new Image();
        img.decoding = "async";
        img.onload = img.onerror = () => {
          if (img.naturalWidth > 0) images.current[i] = img;
          done++;
          if (!cancelled && done <= FIRST_BATCH) { setProgress(done / FIRST_BATCH); reportLoad("frames", done / FIRST_BATCH); }
          resolve();
        };
        img.src = frameSrc(i, dir);
      });

    (async () => {
      await Promise.all(Array.from({ length: FIRST_BATCH }, (_, i) => load(i)));
      if (cancelled) return;
      setLoaded(true);
      for (let i = FIRST_BATCH; i < FRAME_COUNT && !cancelled; i += 6) {
        await Promise.all(Array.from({ length: Math.min(6, FRAME_COUNT - i) }, (_, k) => load(i + k)));
      }
    })();

    return () => { cancelled = true; };
  }, []);

  const nearest = useCallback((index: number): HTMLImageElement | null => {
    for (let i = Math.min(index, FRAME_COUNT - 1); i >= 0; i--) {
      const img = images.current[i];
      if (img) return img;
    }
    return null;
  }, []);

  return { nearest, loaded, progress };
}
