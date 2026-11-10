"use client";
import { useEffect, useState, type RefObject } from "react";

const EVENT = "echofy-sound";

/**
 * Speaker button for a muted-autoplay video. Browsers only allow sound after a tap, so this
 * is the control that turns it on. Only one video has sound at a time.
 */
export default function SoundToggle({ videoRef, className = "" }: { videoRef: RefObject<HTMLVideoElement | null>; className?: string }) {
  const [muted, setMuted] = useState(true);

  useEffect(() => {
    const onOther = (e: Event) => {
      const v = videoRef.current;
      if (v && (e as CustomEvent<HTMLVideoElement>).detail !== v) { v.muted = true; setMuted(true); }
    };
    window.addEventListener(EVENT, onOther);
    return () => window.removeEventListener(EVENT, onOther);
  }, [videoRef]);

  const toggle = (e: React.SyntheticEvent) => {
    e.stopPropagation(); // never start a drag or a card click underneath
    const v = videoRef.current;
    if (!v) return;
    const next = !v.muted;
    v.muted = next;
    setMuted(next);
    if (!next) {
      window.dispatchEvent(new CustomEvent(EVENT, { detail: v }));
      v.play().catch(() => {});
    }
  };

  return (
    <button
      type="button"
      className={`sound-btn ${className}`}
      aria-label={muted ? "Turn sound on" : "Turn sound off"}
      aria-pressed={!muted}
      onClick={toggle}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M4 9.5v5h3.6L12 18.5v-13L7.6 9.5H4z" fill="currentColor" stroke="none" />
        {muted ? <path d="M16 9.5l5 5M21 9.5l-5 5" /> : <path d="M15.5 9a4.2 4.2 0 0 1 0 6M18.2 6.6a7.6 7.6 0 0 1 0 10.8" />}
      </svg>
    </button>
  );
}
