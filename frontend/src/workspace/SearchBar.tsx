import { useEffect, useState, type FormEvent, type RefObject } from "react";
import { KNOWN_TYPES, typeLabel } from "../format";
import "./SearchBar.css";

interface Option { value: string; label: string }

const FILTERS: { key: string; label: string; options: Option[] }[] = [
  { key: "type", label: "Type", options: KNOWN_TYPES.map((type) => ({ value: type, label: typeLabel(type) })) },
  { key: "camera_type", label: "Camera", options: [{ value: "CCTV", label: "CCTV" }, { value: "DASHCAM", label: "Dashcam" }] },
  {
    key: "verdict", label: "Tier-2",
    options: [
      { value: "supported", label: "Supported" },
      { value: "not_supported", label: "Not supported" },
      { value: "insufficient_evidence", label: "Insufficient evidence" },
    ],
  },
  {
    key: "verification_status", label: "Status",
    options: [
      { value: "queued", label: "Queued" },
      { value: "running", label: "Verifying" },
      { value: "completed", label: "Verified" },
      { value: "failed", label: "Failed" },
      { value: "skipped", label: "Skipped" },
    ],
  },
  {
    key: "decision", label: "Decision",
    options: [
      { value: "unreviewed", label: "Unreviewed" },
      { value: "approved", label: "Approved" },
      { value: "rejected", label: "Rejected" },
    ],
  },
  {
    key: "source", label: "Source",
    options: [{ value: "tier1_bundle", label: "Tier-1 events" }, { value: "manual_upload", label: "Uploaded images" }],
  },
];

const MORE = ["source_video", "imported_from", "imported_to"];

export function SearchBar({ params, onSearch, inputRef }: {
  params: URLSearchParams;
  onSearch: (next: URLSearchParams) => void;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [more, setMore] = useState(() => Object.fromEntries(MORE.map((key) => [key, params.get(key) ?? ""])));
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const key = params.toString();

  useEffect(() => {
    setQuery(params.get("q") ?? "");
    setMore(Object.fromEntries(MORE.map((name) => [name, params.get(name) ?? ""])));
    // Re-sync the fields only when the URL changes (back button, links).
  }, [key]);

  function apply(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [name, value] of Object.entries(changes)) {
      if (value.trim()) next.set(name, value.trim());
      else next.delete(name);
    }
    const from = next.get("imported_from");
    const to = next.get("imported_to");
    if (from && to && from > to) {
      setError("The start date must be on or before the end date.");
      return;
    }
    setError(null);
    onSearch(next);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    apply({ q: query, ...more });
  }

  const activeCount = [...FILTERS.map(({ key }) => key), ...MORE].filter((name) => params.get(name)).length;
  const active = activeCount > 0;
  const moreActive = MORE.some((name) => params.get(name));

  return (
    <form className="search" role="search" onSubmit={submit}>
      <div className="search__row">
        <label className="visually-hidden" htmlFor="search-q">Describe the event</label>
        <input
          id="search-q"
          ref={inputRef}
          type="search"
          value={query}
          maxLength={300}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Describe the event, for example: car driving against traffic at night"
        />
        <button className="btn btn--primary search__go">Search</button>
      </div>
      <button type="button" className="link-button search__toggle" aria-expanded={filtersOpen} aria-controls="search-filters"
        onClick={() => setFiltersOpen(!filtersOpen)}>
        {filtersOpen ? "Hide filters" : `Filters${active ? ` (${activeCount} on)` : ""}`}
      </button>
      <div className={`search__filters${filtersOpen ? " search__filters--open" : ""}`} id="search-filters">
        {FILTERS.map(({ key, label, options }) => {
          const value = params.get(key) ?? "";
          return (
            <label key={key} className={`chip${value ? " chip--on" : ""}`}>
              <span className="chip__label">{label}</span>
              <select value={value} onChange={(event) => apply({ [key]: event.target.value })}>
                <option value="">Any</option>
                {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
          );
        })}
        <details className="search__more" open={moreActive || undefined}>
          <summary className={moreActive ? "chip chip--on" : "chip"}>More filters</summary>
          <div className="search__more-body">
            <div className="field">
              <label htmlFor="f-video">Recording file name</label>
              <input id="f-video" value={more.source_video} maxLength={200} placeholder="v41.mov"
                onChange={(event) => setMore({ ...more, source_video: event.target.value })} />
            </div>
            <div className={`field${error ? " field--error" : ""}`}>
              <label htmlFor="f-from">Imported from</label>
              <input id="f-from" type="date" value={more.imported_from}
                onChange={(event) => setMore({ ...more, imported_from: event.target.value })} />
            </div>
            <div className={`field${error ? " field--error" : ""}`}>
              <label htmlFor="f-to">Imported to</label>
              <input id="f-to" type="date" value={more.imported_to}
                onChange={(event) => setMore({ ...more, imported_to: event.target.value })} />
            </div>
            <button type="submit" className="btn btn--small">Apply</button>
          </div>
        </details>
        {active && (
          <button type="button" className="link-button search__clear"
            onClick={() => onSearch(new URLSearchParams(params.get("q") ? { q: params.get("q")! } : {}))}>
            Clear filters
          </button>
        )}
      </div>
      {error && <p className="error-text" role="alert">{error}</p>}
    </form>
  );
}
