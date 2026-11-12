"use client";
import { useEffect, useState } from "react";
import { useCredits } from "@/lib/credits";
import { scrollToTarget } from "@/lib/smoothScroll";

const LINKS = [
  { href: "#top", label: "Home" },
  { href: "#dub", label: "Dub" },
  { href: "#studio", label: "Studio" },
  { href: "#showcase", label: "Showcase" },
  { href: "#support", label: "Support" },
];
const SETTLE_MS = 180; // scrolling counts as stopped after this long without movement

export default function Navbar() {
  const credits = useCredits();
  const [hidden, setHidden] = useState(false);

  // The bar slides away while the page is moving and returns when it comes to rest.
  useEffect(() => {
    let timer = 0;
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      const moved = Math.abs(y - last) > 1;
      last = y;
      if (y < 24) { setHidden(false); return; }
      if (moved) setHidden(true);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setHidden(false), SETTLE_MS);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); window.clearTimeout(timer); };
  }, []);

  const go = (e: React.MouseEvent, href: string) => { e.preventDefault(); scrollToTarget(href); };

  return (
    <header className={`nav${hidden ? " is-hidden" : ""}`}>
      <a href="#top" className="nav-brand" onClick={(e) => go(e, "#top")}>
        <img src="/logo.png" alt="" width={36} height={36} />
        <span>Echofy</span>
      </a>
      <nav className="nav-links" aria-label="Sections">
        {LINKS.map((l) => (
          <a key={l.href} href={l.href} onClick={(e) => go(e, l.href)}>{l.label}</a>
        ))}
      </nav>
      <div className="nav-credits" aria-live="polite">
        <strong>{credits}</strong> credits
      </div>
    </header>
  );
}
