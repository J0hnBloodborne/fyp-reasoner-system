import { Fragment } from "react";
import type { RecordSummary } from "../api";
import { Tally } from "../components/Tally";
import { dateTime, eventTitle, frameSeconds, markOf, OUTCOME_LABEL, timecode, type Mark } from "../format";
import "./Register.css";

export type SortKey = "type" | "recording" | "frame" | "camera" | "tier2" | "decision" | "imported";
export interface Sort { key: SortKey; descending: boolean }

const MARK_ORDER: Mark[] = ["supported", "insufficient_evidence", "not_supported", "pending", "failed", "skipped", "unverified"];

const VALUE: Record<SortKey, (row: RecordSummary) => string | number> = {
  type: (row) => eventTitle(row),
  recording: (row) => row.source_video ?? "",
  frame: (row) => row.trigger_frame ?? 0,
  camera: (row) => row.camera_type ?? "",
  tier2: (row) => MARK_ORDER.indexOf(markOf(row)),
  decision: (row) => row.decision ?? "unreviewed",
  imported: (row) => row.created_at,
};

export function sortRows(rows: RecordSummary[], sort: Sort | null) {
  if (!sort) return rows;
  const value = VALUE[sort.key];
  const sorted = [...rows].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    return typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
  });
  return sort.descending ? sorted.reverse() : sorted;
}

/** FTS5 snippets mark matched terms with [brackets]. */
function Snippet({ text }: { text: string }) {
  const parts = text.replace(/\s+/g, " ").split(/\[([^\]]+)\]/);
  return (
    <span className="register__snippet">
      {parts.map((part, index) => (index % 2 ? <mark key={index}>{part}</mark> : <Fragment key={index}>{part}</Fragment>))}
    </span>
  );
}

const COLUMNS: [SortKey, string][] = [
  ["type", "Event"], ["recording", "Recording"], ["frame", "Frame"], ["camera", "Camera"],
  ["tier2", "Tier-2"], ["decision", "Decision"], ["imported", "Imported"],
];

export function Register({ rows, sort, onSort, selectedId, onSelect, ranked }: {
  rows: RecordSummary[];
  sort: Sort | null;
  onSort: (sort: Sort | null) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  ranked: boolean;
}) {
  function toggle(key: SortKey) {
    if (sort?.key !== key) onSort({ key, descending: false });
    else if (!sort.descending) onSort({ key, descending: true });
    else onSort(null);
  }
  return (
    <div className="register">
      <table>
        <caption className="visually-hidden">
          Search results{sort ? "" : ranked ? ", best match first" : ", newest first"}. Select a row to open it.
        </caption>
        <thead>
          <tr>
            {COLUMNS.map(([key, label]) => (
              <th key={key} scope="col" aria-sort={sort?.key === key ? (sort.descending ? "descending" : "ascending") : undefined}>
                <button type="button" onClick={() => toggle(key)}>
                  {label}
                  <span className="register__arrow" aria-hidden="true">{sort?.key === key ? (sort.descending ? "▼" : "▲") : ""}</span>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} aria-selected={row.id === selectedId} onClick={() => onSelect(row.id)}>
              <td>
                <button type="button" className="register__open" onClick={(event) => { event.stopPropagation(); onSelect(row.id); }}>
                  {eventTitle(row)}
                </button>
                {row.snippet && <Snippet text={row.snippet} />}
              </td>
              <td>{row.source_video ?? <span className="muted">Uploaded image</span>}</td>
              <td className="mono">
                {row.trigger_frame
                  ? <>{timecode(row.trigger_frame, row.fps)}<span className="muted"> F{row.trigger_frame}{row.fps ? ` · ${frameSeconds(row.trigger_frame, row.fps).toFixed(2)} s` : ""}</span></>
                  : <span className="muted">Still image</span>}
              </td>
              <td>{row.camera_type ?? <span className="muted">None</span>}</td>
              <td>
                {row.source === "tier1_bundle"
                  ? <Tally mark={markOf(row)} status={row.verification_status} />
                  : <span className="muted">{row.outcome ? OUTCOME_LABEL[row.outcome] : row.status}</span>}
              </td>
              <td className={row.decision ? "" : "muted"}>{row.decision ? row.decision[0].toUpperCase() + row.decision.slice(1) : "Unreviewed"}</td>
              <td className="mono muted">{dateTime(row.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function toCSV(rows: RecordSummary[]) {
  const header = ["id", "type", "recording", "trigger_frame", "time_seconds", "camera", "verification_status", "verdict", "outcome", "decision", "imported_at"];
  const cell = (value: unknown) => {
    const text = value == null ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = rows.map((row) => [
    row.id, row.types.join("; "), row.source_video, row.trigger_frame,
    row.trigger_frame && row.fps ? frameSeconds(row.trigger_frame, row.fps).toFixed(3) : "",
    row.camera_type, row.verification_status, row.verdict, row.outcome, row.decision ?? "unreviewed", row.created_at,
  ].map(cell).join(","));
  return [header.join(","), ...lines].join("\n") + "\n";
}
