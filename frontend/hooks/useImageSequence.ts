"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { reportLoad } from "@/lib/loadProgress";
import { FRAME_COUNT, FRAMES_DIR, MOBILE_FRAMES_DIR, frameSrc } from "@/lib/media";

const PARALLEL = 8;
const COARSE_STEP = 4; // every 4th frame loads first, so a fast scroll never lands on a gap

/**
 * Loads every hero frame. The page loader waits for the full set: `reportLoad("frames", p)`
 * climbs from 0 to 1 across all frames, not just the first batch.
 * Frames load coarse-first (every 4th, then the rest). `nearest(i)` returns the closest
 * loaded frame at or before i, so the canvas is never blank while the rest arrive.
 * `loaded` turns true once the coarse set is in, so the hero can start if the loader gives up.
 */
export function useImageSequence() {
  const images = useRef<(HTMLImageElement | null)[]>(new Array(FRAME_COUNT).fill(null));
  const [loaded, setLoaded] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const isMobile = window.innerWidth < window.innerHeight;
    const dir = MOBILE_FRAMES_DIR && isMobile ? MOBILE_FRAMES_DIR : FRAMES_DIR;

    const order: number[] = [];
    for (let i = 0; i < FRAME_COUNT; i += COARSE_STEP) order.push(i);
    const coarse = order.length;
    for (let i = 0; i < FRAME_COUNT; i++) if (i % COARSE_STEP) order.push(i);

    let next = 0;
    let done = 0;

    const load = (i: number) =>
      new Promise<void>((resolve) => {
        const img = new Image();
        img.decoding = "async";
        img.onload = img.onerror = () => {
          if (img.naturalWidth > 0) images.current[i] = img;
          done++;
          if (!cancelled) {
            const p = done / FRAME_COUNT;
            setProgress(p);
            reportLoad("frames", p);
            if (done === coarse) setLoaded(true);
          }
          resolve();
        };
        img.src = frameSrc(i, dir);
      });

    const worker = async () => {
      while (!cancelled && next < order.length) await load(order[next++]);
    };
    Promise.all(Array.from({ length: PARALLEL }, worker));

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
