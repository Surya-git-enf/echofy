"use client";
import { useRef, useEffect, useState } from "react";
import { LANGUAGES } from "@/lib/api";

interface LanguageSelectProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export default function LanguageSelect({ value, onChange, disabled }: LanguageSelectProps) {
  const selectRef = useRef<HTMLSelectElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLSelectElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setIsOpen(!isOpen);
    } else if (e.key === "Escape") {
      setIsOpen(false);
      selectRef.current?.blur();
    } else if (e.key === "ArrowDown" && !isOpen) {
      e.preventDefault();
      setIsOpen(true);
    }
  };

  const handleBlur = () => {
    setFocused(false);
    setTimeout(() => setIsOpen(false), 150);
  };

  const handleFocus = () => setFocused(true);

  const selectedLang = LANGUAGES.find((l) => l.key === value) ?? LANGUAGES[0];

  return (
    <div className="lang-select-wrapper" ref={wrapperRef}>
      <label htmlFor="target-language" className="lang-select-label">
        Dub into
      </label>
      <div className={`lang-select-trigger${focused ? " focused" : ""}${isOpen ? " open" : ""}${disabled ? " disabled" : ""}`} role="combobox" aria-expanded={isOpen} aria-haspopup="listbox" aria-label="Target language">
        <select
          ref={selectRef}
          id="target-language"
          value={value}
          onChange={(e) => { onChange(e.target.value); setIsOpen(false); }}
          onKeyDown={handleKeyDown}
          onFocus={handleFocus}
          onBlur={handleBlur}
          disabled={disabled}
          className="lang-select-native"
          autoComplete="off"
        >
          {LANGUAGES.map((lang) => (
            <option key={lang.key} value={lang.key} lang={lang.lang}>
              {lang.native} — {lang.label}
            </option>
          ))}
        </select>
        <span className="lang-select-display" aria-hidden="true">
          <span className="lang-native">{selectedLang.native}</span>
          <span className="lang-label">{selectedLang.label}</span>
        </span>
        <svg className="lang-select-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
      {isOpen && (
        <ul className="lang-select-options" role="listbox" aria-label="Available languages">
          {LANGUAGES.map((lang) => (
            <li
              key={lang.key}
              role="option"
              aria-selected={lang.key === value}
              className={`lang-select-option${lang.key === value ? " selected" : ""}`}
              onClick={() => { onChange(lang.key); setIsOpen(false); }}
              onMouseEnter={() => selectRef.current?.focus()}
            >
              <span className="lang-native" lang={lang.lang}>{lang.native}</span>
              <span className="lang-label">{lang.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}