import { useEffect, useState } from "react";
import { api, type Health } from "../api";
import { useInterval } from "../hooks";
import { Link } from "../router";
import "./StatusBar.css";

const MODEL_STATE: Record<Health["model_state"], string> = {
  not_loaded: "loads on first job",
  loading: "loading",
  ready: "ready",
  load_failed: "failed to load",
  external: "external",
};

interface Jobs { running: number; queued: number }

/** Bottom bar: model state, the verification queue and keyboard hints. */
export function StatusBar({ onShowKeys }: { onShowKeys: () => void }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [jobs, setJobs] = useState<Jobs>({ running: 0, queued: 0 });

  async function refresh() {
    try {
      const [state, running, queued] = await Promise.all([
        api.health(),
        api.search(new URLSearchParams({ verification_status: "running" })),
        api.search(new URLSearchParams({ verification_status: "queued" })),
      ]);
      setHealth(state);
      setJobs({ running: running.length, queued: queued.length });
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }

  useEffect(() => {
    refresh();
  }, []);
  const busy = jobs.running + jobs.queued > 0 || health?.model_state === "loading";
  useInterval(refresh, busy ? 2500 : 10000, true);

  const queue = jobs.running + jobs.queued
    ? [jobs.running && `Verifying ${jobs.running}`, jobs.queued && `${jobs.queued >= 100 ? "100+" : jobs.queued} queued`]
        .filter(Boolean)
        .join(" · ")
    : "No verification jobs";

  return (
    <footer className="statusbar">
      {offline ? (
        <span className="statusbar__item statusbar__item--warn">Server not responding. Start it with python -m traffic_poc serve.</span>
      ) : (
        <>
          <span className={`statusbar__item statusbar__model statusbar__model--${health?.model_state ?? "unknown"}`}>
            {health ? `${health.model_id.split("/").pop()} · ${MODEL_STATE[health.model_state]}` : "Checking model"}
          </span>
          <span className="statusbar__item" aria-live="polite">{queue}</span>
        </>
      )}
      <span className="statusbar__hint">
        <kbd>/</kbd> search <kbd>↑</kbd><kbd>↓</kbd> events <kbd>←</kbd><kbd>→</kbd> frames
        <button type="button" className="link-button" onClick={onShowKeys}>All keys</button>
      </span>
      <Link href="/privacy" className="statusbar__link">Privacy and terms</Link>
    </footer>
  );
}
