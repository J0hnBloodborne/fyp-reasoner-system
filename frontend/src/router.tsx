// A small history router. The app has six fixed routes, which App.tsx matches.
import { useEffect, useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from "react";

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());
window.addEventListener("popstate", notify);

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const snapshot = () => window.location.pathname + window.location.search;

export function useLocation() {
  const href = useSyncExternalStore(subscribe, snapshot);
  return new URL(href, window.location.origin);
}

export function navigate(to: string, { replace = false } = {}) {
  if (to === snapshot()) return;
  window.history[replace ? "replaceState" : "pushState"](null, "", to);
  notify();
}

export function Link({ href, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) {
  function handle(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(href);
  }
  return <a href={href} onClick={handle} {...rest} />;
}

/** Each view names itself in the browser tab. */
export function useTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · Traffic Search` : "Traffic Search";
  }, [title]);
}
