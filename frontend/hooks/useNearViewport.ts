"use client";
import { useEffect, useState, type RefObject } from "react";

/** Turns true (and stays true) once the element is within `margin` of the viewport. Used to hold back heavy media. */
export function useNearViewport(ref: RefObject<Element | null>, margin = "700px") {
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) { setNear(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setNear(true); io.disconnect(); } }, { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, margin]);
  return near;
}
