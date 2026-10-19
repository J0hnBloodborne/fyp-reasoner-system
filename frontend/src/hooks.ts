import { useEffect, useRef, useState } from "react";

/** Call `callback` every `delay` ms while `active`; the latest callback always runs. */
export function useInterval(callback: () => void, delay: number, active: boolean) {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => saved.current(), delay);
    return () => window.clearInterval(timer);
  }, [delay, active]);
}

/** A per-browser preference. Storage can be blocked, so failures fall back to memory. */
export function useStoredString(key: string, initial: string) {
  const [value, setValue] = useState(() => {
    try {
      return localStorage.getItem(key) ?? initial;
    } catch {
      return initial;
    }
  });
  function update(next: string) {
    setValue(next);
    try {
      localStorage.setItem(key, next);
    } catch {
      // Keep the in-memory value only.
    }
  }
  return [value, update] as const;
}

/** Keyboard shortcuts apply only when the user is not typing in a field. */
export function isTyping(event: KeyboardEvent) {
  return !!eventElement(event)?.closest("input, textarea, select, [contenteditable='true']");
}

/** The element a key event came from; events sent to the document have none. */
export function eventElement(event: Event) {
  return event.target instanceof Element ? event.target : null;
}
