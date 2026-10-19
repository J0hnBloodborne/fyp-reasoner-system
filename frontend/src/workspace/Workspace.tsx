import { useEffect, useMemo, useRef, useState } from "react";
import { api, isPending, type RecordDetail, type RecordSummary } from "../api";
import { eventTitle } from "../format";
import { eventElement, isTyping, useInterval, useStoredString } from "../hooks";
import { Link, navigate, useTitle } from "../router";
import { Inspector } from "./Inspector";
import { Monitor, sortedFrames } from "./Monitor";
import { groupResults } from "./recordings";
import { Register, sortRows, toCSV, type Sort } from "./Register";
import { SearchBar } from "./SearchBar";
import { Legend, Timeline } from "./Timeline";
import "./Workspace.css";

const PLAY_INTERVAL_MS = 250;

function downloadCSV(rows: RecordSummary[]) {
  const url = URL.createObjectURL(new Blob([toCSV(rows)], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `traffic-search-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export function Workspace({ selectedId, params }: { selectedId: string | null; params: URLSearchParams }) {
  const query = params.toString();
  const searchRef = useRef<HTMLInputElement>(null);
  const [results, setResults] = useState<RecordSummary[] | null>(null);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [view, setView] = useStoredString("traffic-results-view", "timeline");
  const [sort, setSort] = useState<Sort | null>(null);
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [frame, setFrame] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);

  // Responses for an older search or selection are dropped.
  const latest = useRef({ query, selectedId });
  latest.current = { query, selectedId };

  async function loadResults() {
    const asked = query;
    try {
      const next = await api.search(params);
      if (latest.current.query !== asked) return;
      setResults(next);
      setResultsError(null);
    } catch (exc) {
      if (latest.current.query === asked) setResultsError((exc as Error).message);
    }
  }
  useEffect(() => {
    setResults(null);
    loadResults();
  }, [query]);
  useInterval(loadResults, 2500, !!results?.some(isPending));

  async function loadRecord(id: string) {
    try {
      const next = await api.record(id);
      if (latest.current.selectedId !== id) return;
      setRecord(next);
      setRecordError(null);
    } catch (exc) {
      if (latest.current.selectedId === id) setRecordError((exc as Error).message);
    }
  }
  useEffect(() => {
    setRecord(null);
    setRecordError(null);
    setFrame(null);
    setPlaying(false);
    if (selectedId) loadRecord(selectedId);
  }, [selectedId]);
  useInterval(() => selectedId && loadRecord(selectedId), 2000, !!record && isPending(record));

  const { recordings, stills } = useMemo(() => groupResults(results ?? []), [results]);
  const ordered = useMemo(
    () => (view === "register" ? sortRows(results ?? [], sort) : [...recordings.flatMap((item) => item.events), ...stills]),
    [view, results, sort, recordings, stills],
  );
  const index = ordered.findIndex((item) => item.id === selectedId);
  const frames = sortedFrames(record);

  function open(id: string) {
    navigate(`/incident/${id}${query ? `?${query}` : ""}`);
  }
  function step(offset: number) {
    if (!ordered.length) return;
    const next = index === -1 ? (offset > 0 ? 0 : ordered.length - 1) : index + offset;
    if (next >= 0 && next < ordered.length) open(ordered[next].id);
  }
  function stepFrame(offset: number) {
    if (!frames.length || !record?.tier1_event) return;
    const current = frames.findIndex((item) => item.frame_index === (frame ?? record.tier1_event!.trigger_frame));
    const next = frames[Math.min(frames.length - 1, Math.max(0, current + offset))];
    setPlaying(false);
    setFrame(next.frame_index);
  }

  // Play loops through the evidence window slowly enough to follow motion.
  useInterval(() => {
    if (!frames.length || !record?.tier1_event) return;
    const current = frames.findIndex((item) => item.frame_index === (frame ?? record.tier1_event!.trigger_frame));
    setFrame(frames[(current + 1) % frames.length].frame_index);
  }, PLAY_INTERVAL_MS, playing && frames.length > 1);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === "/" && !isTyping(event)) {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      const element = eventElement(event);
      if (isTyping(event) || element?.closest("[role='tablist'], dialog")) return;
      const actions: Record<string, () => void> = {
        ArrowDown: () => step(1),
        ArrowUp: () => step(-1),
        ArrowRight: () => stepFrame(1),
        ArrowLeft: () => stepFrame(-1),
        Home: () => stepFrame(-Infinity),
        End: () => stepFrame(Infinity),
        " ": () => frames.length > 1 && setPlaying((value) => !value),
        t: () => record?.tier1_event && (setPlaying(false), setFrame(record.tier1_event.trigger_frame)),
      };
      const action = actions[event.key];
      if (!action) return;
      if (event.key === " " && element?.closest("button, a")) return;
      event.preventDefault();
      action();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const selectedSummary = ordered[index] ?? results?.find((item) => item.id === selectedId);
  useTitle(
    selectedSummary
      ? `${eventTitle(selectedSummary)}${selectedSummary.source_video ? ` · ${selectedSummary.source_video} F${selectedSummary.trigger_frame}` : ""}`
      : params.get("q") ? `Search: ${params.get("q")}` : "Search",
  );

  const filtered = [...params.keys()].some((key) => key !== "q");
  const total = results?.length ?? 0;
  const eventCount = recordings.reduce((sum, item) => sum + item.events.length, 0);
  const summary = results === null ? "Loading results"
    : total === 0 ? "No results"
    : [
        recordings.length && `${eventCount} ${eventCount === 1 ? "event" : "events"} in ${recordings.length} ${recordings.length === 1 ? "recording" : "recordings"}`,
        stills.length && `${stills.length} ${stills.length === 1 ? "image" : "images"}`,
      ].filter(Boolean).join(" · ") + (params.get("q") ? ", best match first" : ", newest first");

  const emptyText = !results ? "Loading results." : total === 0 ? "Nothing to open yet."
    : `Select a marker on the timeline or a row in the register, or press the down arrow to open the first of ${total} results.`;

  let bin;
  if (resultsError) {
    bin = <div className="bin__state"><p className="error-text" role="alert">{resultsError}</p><button type="button" className="btn" onClick={loadResults}>Try again</button></div>;
  } else if (results === null) {
    bin = <div className="bin__state" aria-busy="true"><div className="skeleton" aria-label="Loading results"><i /><i /><i /></div></div>;
  } else if (total === 0 && (params.get("q") || filtered)) {
    bin = (
      <div className="bin__state">
        <h2>No events match{params.get("q") ? ` "${params.get("q")}"` : " these filters"}.</h2>
        <p className="muted">Try fewer or different words, for example the event type or a detail such as "night" or "truck". Filters narrow results further.</p>
        {filtered && <button type="button" className="btn" onClick={() => navigate(params.get("q") ? `/?q=${encodeURIComponent(params.get("q")!)}` : "/")}>Clear filters</button>}
      </div>
    );
  } else if (total === 0) {
    bin = (
      <div className="bin__state">
        <h2>No recordings imported yet.</h2>
        <p className="muted">Run the Tier-1 detector on a video to get a ZIP bundle, then import it. Each event is verified by the vision model after import.</p>
        <div className="bin__actions">
          <Link href="/import" className="btn btn--primary">Import a Tier-1 bundle</Link>
          <Link href="/analyze" className="btn">Analyze an image</Link>
        </div>
      </div>
    );
  } else if (view === "register") {
    bin = <Register rows={ordered} sort={sort} onSort={setSort} selectedId={selectedId} onSelect={open} ranked={!!params.get("q")} />;
  } else {
    bin = <Timeline recordings={recordings} stills={stills} selectedId={selectedId} onSelect={open} />;
  }

  return (
    <main className={`workspace${selectedId ? "" : " workspace--browsing"}`} id="main">
      <div className="workspace__search">
        <SearchBar params={params} inputRef={searchRef} onSearch={(next) => navigate(next.size ? `/?${next}` : "/")} />
      </div>
      <div className="workspace__monitor">
        <Monitor
          record={record}
          loading={!!selectedId && !record}
          error={recordError}
          frame={frame}
          onFrame={(next) => { setPlaying(false); setFrame(next); }}
          playing={playing}
          onPlaying={setPlaying}
          position={index === -1 ? null : { index, total: ordered.length }}
          onStep={step}
          emptyText={emptyText}
        />
      </div>
      <div className="workspace__inspector">
        <Inspector record={record} loading={!!selectedId && !record && !recordError} onFrame={(next) => { setPlaying(false); setFrame(next); }}
          onRecord={(next) => { setRecord(next); loadResults(); }} />
      </div>
      <section className="workspace__bin bin" aria-label="Results">
        <div className="bin__bar">
          <div className="panel-tabs bin__tabs" role="tablist" aria-label="Results view"
            onKeyDown={(event) => {
              if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
              event.preventDefault();
              const next = view === "timeline" ? "register" : "timeline";
              setView(next);
              document.getElementById(`bin-tab-${next}`)?.focus();
            }}>
            {([["timeline", "Timeline"], ["register", "Register"]] as const).map(([key, label]) => (
              <button key={key} id={`bin-tab-${key}`} type="button" role="tab" aria-selected={view === key} aria-controls="bin-panel"
                tabIndex={view === key ? 0 : -1} onClick={() => setView(key)}>
                {label}
              </button>
            ))}
          </div>
          <span className="bin__summary" aria-live="polite">{summary}</span>
          {view === "timeline" ? <Legend />
            : <button type="button" className="btn btn--small" disabled={!total} onClick={() => downloadCSV(ordered)}>Download CSV</button>}
        </div>
        {total >= 100 && <p className="bin__limit">Showing the first 100 results. Add words or filters to narrow the search.</p>}
        <div className="bin__body" id="bin-panel" role="tabpanel" aria-labelledby={`bin-tab-${view}`}>{bin}</div>
      </section>
    </main>
  );
}
