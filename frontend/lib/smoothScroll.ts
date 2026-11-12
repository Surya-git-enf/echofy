import type Lenis from "lenis";

// Shared handle to the Lenis instance, so the loader can freeze scrolling and the nav can scroll to sections.
let instance: Lenis | null = null;
let locked = false;

export function registerLenis(l: Lenis | null) {
  instance = l;
  if (l && locked) l.stop();
}

export function setScrollLocked(on: boolean) {
  locked = on;
  if (!instance) return;
  if (on) instance.stop();
  else instance.start();
}

export function scrollToTarget(hash: string) {
  const el = hash === "#top" ? null : document.querySelector(hash);
  if (instance) instance.scrollTo(el ?? 0, { duration: 1.4 });
  else if (el) el.scrollIntoView({ behavior: "smooth" });
  else window.scrollTo({ top: 0, behavior: "smooth" });
}
