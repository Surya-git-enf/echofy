import { useSyncExternalStore } from "react";

// One place that adds up everything the first screen waits for. Each part reports 0..1
// and the page loader shows the weighted total, so the equalizer fills as real assets arrive.
export type LoadPart = "frames" | "assets" | "videos";

const WEIGHT: Record<LoadPart, number> = { frames: 0.7, assets: 0.2, videos: 0.1 };
const value: Record<LoadPart, number> = { frames: 0, assets: 0, videos: 0 };
const listeners = new Set<() => void>();
let total = 0;

export function reportLoad(part: LoadPart, fraction: number) {
  value[part] = Math.max(value[part], Math.min(1, fraction));
  total = (Object.keys(WEIGHT) as LoadPart[]).reduce((sum, k) => sum + value[k] * WEIGHT[k], 0);
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => { listeners.delete(l); };
};

/** Total first-load progress from 0 to 1. */
export const useLoadProgress = () => useSyncExternalStore(subscribe, () => total, () => 0);
