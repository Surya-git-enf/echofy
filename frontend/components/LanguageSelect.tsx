"use client";
import { useEffect, useId, useRef, useState } from "react";
import { LANGUAGES } from "@/lib/api";

interface LanguageSelectProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/**
 * Our own dropdown: a button that opens a list directly below it. No native <select>, so it looks
 * the same on every phone and browser. Keyboard: arrows, Home/End, Enter/Space, Escape, type-ahead.
 */
export default function LanguageSelect({ value, onChange, disabled }: LanguageSelectProps) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const selected = Math.max(0, LANGUAGES.findIndex((l) => l.key === value));
  const [active, setActive] = useState(selected);
  const typed = useRef({ text: "", at: 0 });

  const show = () => { if (!disabled) { setActive(selected); setOpen(true); } };
  const choose = (i: number) => { onChange(LANGUAGES[i].key); setOpen(false); (root.current?.querySelector("button") as HTMLElement | null)?.focus(); };

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  useEffect(() => {
    if (open) list.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const last = LANGUAGES.length - 1;
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); show(); }
      return;
    }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(last, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(last); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(active); }
    else if (e.key === "Escape" || e.key === "Tab") setOpen(false);
    else if (e.key.length === 1) {
      const now = Date.now();
      typed.current.text = now - typed.current.at > 700 ? e.key.toLowerCase() : typed.current.text + e.key.toLowerCase();
      typed.current.at = now;
      const hit = LANGUAGES.findIndex((l) => l.label.toLowerCase().startsWith(typed.current.text));
      if (hit >= 0) setActive(hit);
    }
  };

  const current = LANGUAGES[selected];

  return (
    <div className="lang-select" ref={root} onKeyDown={onKeyDown}>
      <span className="lang-select-label" id={`${id}-label`}>Dub into</span>
      <button
        type="button"
        className={`lang-select-trigger${open ? " is-open" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-labelledby={`${id}-label ${id}-value`}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : show())}
      >
        <span className="lang-select-value" id={`${id}-value`}>
          <span className="lang-native" lang={current.lang}>{current.native}</span>
          <span className="lang-label">{current.label}</span>
        </span>
        <svg className="lang-select-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <ul ref={list} id={`${id}-list`} className="lang-select-options" role="listbox" aria-labelledby={`${id}-label`} aria-activedescendant={`${id}-opt-${active}`}>
          {LANGUAGES.map((l, i) => (
            <li
              key={l.key}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === selected}
              className={`lang-select-option${i === selected ? " is-selected" : ""}${i === active ? " is-active" : ""}`}
              onPointerEnter={() => setActive(i)}
              onClick={() => choose(i)}
            >
              <span className="lang-native" lang={l.lang}>{l.native}</span>
              <span className="lang-label">{l.label}</span>
              {i === selected && (
                <svg className="lang-select-tick" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="5 12.5 10 17.5 19 7.5" /></svg>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
