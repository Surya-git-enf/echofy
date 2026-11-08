"use client";
import { useSyncExternalStore } from "react";

/**
 * Credits live in the browser (localStorage) until accounts exist, so clearing site
 * data or using incognito grants a new welcome card. Move the balance to the server
 * before charging money.
 */
const BALANCE_KEY = "echofy.credits.v1";
const WELCOME_KEY = "echofy.welcome.v1";
export const WELCOME_CREDITS = 100;
export const CREDITS_PER_MINUTE = 2;

const listeners = new Set<() => void>();
let memory = 0;
let memoryWelcome = false;

function read(): number {
  try {
    const n = Number(window.localStorage.getItem(BALANCE_KEY));
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  } catch {
    return memory;
  }
}

function write(n: number) {
  memory = Math.max(0, Math.floor(n));
  try { window.localStorage.setItem(BALANCE_KEY, String(memory)); } catch { /* private mode */ }
  listeners.forEach((l) => l());
}

export function welcomeSeen(): boolean {
  try { return window.localStorage.getItem(WELCOME_KEY) === "1"; } catch { return memoryWelcome; }
}

/** Adds the welcome credits once. Returns false if they were already claimed. */
export function claimWelcome(): boolean {
  if (welcomeSeen()) return false;
  memoryWelcome = true;
  try { window.localStorage.setItem(WELCOME_KEY, "1"); } catch { /* private mode */ }
  write(read() + WELCOME_CREDITS);
  return true;
}

export const costFor = (seconds: number) => Math.max(1, Math.ceil(seconds / 60)) * CREDITS_PER_MINUTE;

export function spend(n: number): boolean {
  const bal = read();
  if (n > bal) return false;
  write(bal - n);
  return true;
}

export const refund = (n: number) => write(read() + n);

export function useCredits(): number {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      const onStorage = (e: StorageEvent) => { if (e.key === BALANCE_KEY) cb(); };
      window.addEventListener("storage", onStorage);
      return () => { listeners.delete(cb); window.removeEventListener("storage", onStorage); };
    },
    read,
    () => 0,
  );
}
