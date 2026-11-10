"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { reportLoad } from "@/lib/loadProgress";
import { FRAME_COUNT, FRAMES_DIR, MOBILE_FRAMES_DIR, frameSrc } from "@/lib/media";

const FIRST_BATCH = 30;
const MOBILE_FIRST_BATCH = 20;

/**
 * Loads hero frames in two stages:
 * - Stage 1 (priority): first 30/20 frames — blocks PageLoader, reports "frames" progress 0→1
 * - Stage 2 (background): remaining frames — loads silently, does NOT block PageLoader
 * `nearest(i)` returns closest loaded frame at/before i — no blank canvas on fast scroll.
 */
export function useImageSequence() {
  const images = useRef<(HTMLImageElement | null)[]>(new Array(FRAME_COUNT).fill(null));
  const [loaded, setLoaded] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let done = 0;
    const isMobile = window.innerWidth < window.innerHeight;
    const dir = MOBILE_FRAMES_DIR && isMobile ? MOBILE_FRAMES_DIR : FRAMES_DIR;
    const batchSize = isMobile ? MOBILE_FIRST_BATCH : FIRST_BATCH;

    const load = (i: number) =>
      new Promise<void>((resolve) => {
        const img = new Image();
        img.decoding = "async";
        img.fetchPriority = i < batchSize ? "high" : "low";
        img.onload = img.onerror = () => {
          if (img.naturalWidth > 0) images.current[i] = img;
          done++;
          if (!cancelled && done <= batchSize) {
            const p = done / batchSize;
            setProgress(p);
            reportLoad("frames", p); // PageLoader waits for this to reach 1
          }
          resolve();
        };
        img.src = frameSrc(i, dir);
      });

    (async () => {
      // Stage 1: Priority frames (blocks PageLoader)
      await Promise.all(Array.from({ length: batchSize }, (_, i) => load(i)));
      if (cancelled) return;
      setLoaded(true);
      setProgress(1);
      reportLoad("frames", 1); // Critical frames done → PageLoader can proceed

      // Stage 2: Remaining frames (background, no PageLoader blocking)
      for (let i = batchSize; i < FRAME_COUNT && !cancelled; i += 6) {
        await Promise.all(
          Array.from({ length: Math.min(6, FRAME_COUNT - i) }, (_, k) => load(i + k))
        );
      }
    })();

    return () => { cancelled = true; };
  }, []);

  const nearest = useCallback((index: number): HTMLImageElement | null => {
    for (let i = Math.min(index, FRAME_COUNT - 1); i >= 0; i--) {
      const img = images.current[i];
      if (img?.complete && img.naturalWidth > 0) return img;
    }
    return null;
  }, []);

  return { nearest, loaded, progress };
}