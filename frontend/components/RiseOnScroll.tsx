"use client";
import { useEffect } from "react";

const TARGETS = [
  ".grad-title", ".up-card", ".section-title", ".showcase-note",
  ".footer-title", ".footer p", ".socials li",
].join(",");

/** Headings and copy rise into place the first time they scroll into view. */
export default function RiseOnScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) return;
    const seen = new WeakSet<Element>();
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => {
        if (!e.isIntersecting) return;
        e.target.classList.add("rise-in");
        io.unobserve(e.target);
      }),
      { threshold: 0.15, rootMargin: "0px 0px -8% 0px" },
    );
    const scan = () => document.querySelectorAll(TARGETS).forEach((el) => {
      if (seen.has(el) || el.closest(".hero")) return;
      seen.add(el);
      el.classList.add("rise");
      io.observe(el);
    });
    scan();
    const mo = new MutationObserver(scan); // picks up the result block when a dub finishes
    mo.observe(document.querySelector("main") ?? document.body, { childList: true, subtree: true });
    return () => { io.disconnect(); mo.disconnect(); };
  }, []);
  return null;
}
