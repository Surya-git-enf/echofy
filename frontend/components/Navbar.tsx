"use client";
import { useCredits } from "@/lib/credits";

export default function Navbar() {
  const credits = useCredits();
  return (
    <header className="nav">
      <a href="#top" className="nav-brand">
        <img src="/logo.png" alt="" width={36} height={36} />
        <span>Echofy</span>
      </a>
      <div className="nav-credits" aria-live="polite">
        <strong>{credits}</strong> credits
      </div>
    </header>
  );
}
