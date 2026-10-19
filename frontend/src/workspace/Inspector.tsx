import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { api, files, type CustodyEntry, type Decision, type RecordDetail } from "../api";
import { dateTime, fpsLabel, OUTCOME_LABEL, shortHash, timecode, typeLabel } from "../format";
import { useStoredString } from "../hooks";
import "./Inspector.css";

type Tab = "verdict" | "detection" | "review" | "raw";
const TABS: [Tab, string][] = [["verdict", "Verdict"], ["detection", "Detection"], ["review", "Review"], ["raw", "Raw output"]];

interface TabProps {
  record: RecordDetail;
  onFrame: (frame: number) => void;
  onRecord: (record: RecordDetail) => void;
}

function Waiting({ children }: { children: ReactNode }) {
  return (
    <div className="inspector__block" aria-busy="true">
      <p>{children}</p>
      <div className="skeleton" aria-hidden="true"><i /><i /><i /></div>
    </div>
  );
}

function Limits({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="inspector__block">
      <h3 className="eyebrow">Limits the model stated</h3>
      <ul className="inspector__list">{items.map((item, index) => <li key={index}>{item}</li>)}</ul>
    </div>
  );
}

function VerifyButton({ record, onRecord, label }: { record: RecordDetail; onRecord: (record: RecordDetail) => void; label: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    setBusy(true);
    setError(null);
    try {
      onRecord(await api.verify(record.id));
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="inspector__actions">
      <button type="button" className="btn btn--primary" onClick={run} disabled={busy}>{busy ? "Queuing" : label}</button>
      {error && <p className="error-text" role="alert">{error}</p>}
    </div>
  );
}

function VerdictTab({ record, onFrame, onRecord }: TabProps) {
  if (!record.tier1_event) return <AnalysisView record={record} />;
  const verification = record.verification;
  const frameCount = record.tier1_event.frames.length;
  if (!verification) {
    return (
      <div className="inspector__block">
        <p>This event has not been queued for Tier-2 verification.</p>
        <VerifyButton record={record} onRecord={onRecord} label="Verify with Tier-2" />
      </div>
    );
  }
  switch (verification.status) {
    case "queued":
      return <Waiting>Queued. Events verify one at a time on the GPU, oldest first.</Waiting>;
    case "running":
      return <Waiting>Verifying now. The model is reading {frameCount} frames around the trigger.</Waiting>;
    case "skipped":
      return <div className="inspector__block"><p>Skipped. {verification.error}</p></div>;
    case "failed":
      return (
        <div className="inspector__block">
          <p className="error-text">{verification.error ?? "Verification failed."}</p>
          <p className="muted">The raw model output, if any, is on the Raw output tab.</p>
          <VerifyButton record={record} onRecord={onRecord} label="Retry verification" />
        </div>
      );
  }
  const result = verification.result!;
  const provenance = verification.provenance ?? {};
  return (
    <>
      <div className="inspector__block">
        <p className="inspector__summary">{result.summary}</p>
      </div>
      {result.observations.length > 0 && (
        <div className="inspector__block">
          <h3 className="eyebrow">What Tier-2 saw, frame by frame</h3>
          <ol className="observations">
            {result.observations.map((item, index) => (
              <li key={index}>
                <button type="button" className="frame-chip" onClick={() => onFrame(item.frame_index)}
                  aria-label={`Show frame ${item.frame_index}`}>
                  {item.frame_index}
                </button>
                <span>{item.description}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      <Limits items={result.limitations} />
      <p className="inspector__note">
        {[provenance.model_id, verification.prompt_version, provenance.inference_seconds && `${provenance.inference_seconds} s`].filter(Boolean).join(" · ")}.
        {" "}A verdict is the model's reading of these frames only. It is not a calibrated probability.
      </p>
    </>
  );
}

function AnalysisView({ record }: { record: RecordDetail }) {
  if (record.status === "queued" || record.status === "running") {
    return <Waiting>{record.status === "queued" ? "Queued for analysis." : "Analyzing the image now."} The first job can include loading the model.</Waiting>;
  }
  if (record.status === "failed" || !record.analysis) {
    return <div className="inspector__block"><p className="error-text">{record.error ?? "Analysis failed."}</p></div>;
  }
  const analysis = record.analysis;
  return (
    <>
      <div className="inspector__block">
        <p className="eyebrow">{OUTCOME_LABEL[analysis.outcome]}</p>
        <p className="inspector__summary">{analysis.summary}</p>
      </div>
      {analysis.findings.length > 0 && (
        <div className="inspector__block">
          <h3 className="eyebrow">Findings</h3>
          <ol className="findings">
            {analysis.findings.map((finding, index) => (
              <li key={index}>
                <b>{typeLabel(finding.violation_type)}</b>
                <span>{finding.subject}</span>
                <span className="muted">{finding.evidence}</span>
                {(finding.plate || finding.confidence !== null) && (
                  <span className="mono muted">
                    {[finding.plate && `plate ${finding.plate}`, finding.confidence !== null && `model-reported ${finding.confidence}, uncalibrated`].filter(Boolean).join(" · ")}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
      <Limits items={analysis.limitations} />
      <p className="inspector__note">A single still cannot show direction or signal timing.</p>
    </>
  );
}

function Plate({ rows }: { rows: [string, ReactNode, boolean?][] }) {
  return (
    <dl className="plate">
      {rows.map(([label, value, wide]) => (
        <div key={label} className={wide ? "wide" : undefined}><dt>{label}</dt><dd>{value ?? "None"}</dd></div>
      ))}
    </dl>
  );
}

function DetectionTab({ record }: TabProps) {
  const event = record.tier1_event;
  if (!event) {
    return (
      <div className="inspector__block">
        <Plate rows={[
          ["File", record.filename, true],
          ["Location", record.location],
          ["Captured", record.captured_at],
          ["Original size", `${record.evidence.width} × ${record.evidence.height}`],
          ["Model input", record.evidence.model_width ? `${record.evidence.model_width} × ${record.evidence.model_height}` : null],
          ["Imported", dateTime(record.created_at), true],
        ]} />
      </div>
    );
  }
  const frames = [...event.frames].sort((a, b) => a.frame_index - b.frame_index);
  return (
    <>
      <div className="inspector__block">
        <Plate rows={[
          ["Trigger", event.trigger_type, true],
          ["Track", event.target_id],
          ["Trigger frame", `${event.trigger_frame} · ${timecode(event.trigger_frame, event.fps)}`],
          ["Window", `${frames[0].frame_index} to ${frames[frames.length - 1].frame_index}`],
          ["Detector value", event.heuristic_value ?? "None"],
          ["Camera", event.camera_type],
          ["Frame rate", event.fps ? fpsLabel(event.fps) : "Unknown"],
          ["Frames in video", event.frame_count],
          ["Evidence", event.evidence_origin === "raw_frame" ? "Raw frames" : "Annotated preview"],
          ["Event", event.event_id, true],
          ["Bundle", event.bundle_id, true],
          ["Manifest SHA-256", record.tier1_manifest_sha256 ? shortHash(record.tier1_manifest_sha256) : null],
          ["Imported", dateTime(record.created_at)],
        ]} />
      </div>
      <p className="inspector__note">The detector value is the Tier-1 heuristic's raw number (pixel displacement or overlap). It is not a probability.</p>
    </>
  );
}

const ACTION: Record<string, string> = {
  imported: "Imported",
  verification_queued: "Queued for Tier-2",
  verification_skipped: "Tier-2 skipped",
  verification_started: "Tier-2 started",
  verification_completed: "Tier-2 finished",
  verification_failed: "Tier-2 failed",
  analysis_started: "Analysis started",
  analysis_finished: "Analysis finished",
  approved: "Approved",
  rejected: "Rejected",
};

function uploadCustody(record: RecordDetail): CustodyEntry[] {
  const entries: CustodyEntry[] = [{ at: record.created_at, action: "imported", actor: "Image upload", detail: record.filename }];
  if (record.started_at) entries.push({ at: record.started_at, action: "analysis_started", actor: "VLM", detail: null });
  if (record.finished_at) entries.push({ at: record.finished_at, action: "analysis_finished", actor: "VLM", detail: record.analysis?.outcome ?? record.error });
  for (const review of record.reviews) entries.push({ at: review.created_at, action: review.decision, actor: review.reviewer, detail: review.notes || null });
  return entries;
}

function ReviewTab({ record, onRecord }: TabProps) {
  const [reviewer, setReviewer] = useStoredString("traffic-reviewer", "");
  const [notes, setNotes] = useState("");
  const [correct, setCorrect] = useState(false);
  const [correction, setCorrection] = useState("");
  const [error, setError] = useState<{ field: "reviewer" | "correction" | "form"; text: string } | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [custody, setCustody] = useState<CustodyEntry[] | null>(null);
  const imported = !!record.tier1_event;
  const reviewable = record.status === "completed" || record.status === "awaiting_review";
  const latest = record.reviews[record.reviews.length - 1];
  const custodyKey = `${record.id}:${record.reviews.length}:${record.verification?.status}:${record.status}`;

  useEffect(() => {
    setNotes("");
    setCorrect(false);
    setCorrection(record.analysis ? JSON.stringify(record.analysis, null, 2) : "");
    setError(null);
    setSaved(null);
  }, [record.id]);

  useEffect(() => {
    if (!imported) {
      setCustody(uploadCustody(record));
      return;
    }
    let live = true;
    api.report(record.id).then((report) => live && setCustody(report.custody_log)).catch(() => live && setCustody(null));
    return () => { live = false; };
  }, [custodyKey]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const decision = ((event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null)?.value as Decision;
    if (!reviewer.trim()) {
      setError({ field: "reviewer", text: "Enter your name to record this decision." });
      return;
    }
    let corrected = null;
    if (correct) {
      try {
        corrected = JSON.parse(correction);
      } catch {
        setError({ field: "correction", text: "The corrected analysis is not valid JSON. Fix it, or clear the checkbox." });
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.review(record.id, { decision, reviewer: reviewer.trim(), notes, corrected_analysis: corrected });
      onRecord(updated);
      setNotes("");
      setSaved(decision === "approved" ? "Approved. The model output is unchanged." : "Rejected. The model output is unchanged.");
    } catch (exc) {
      setError({ field: "form", text: (exc as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="inspector__block">
        <p className="inspector__decision">
          {latest
            ? <><b>{latest.decision === "approved" ? "Approved" : "Rejected"}</b> by {latest.reviewer}, {dateTime(latest.created_at)}</>
            : <><b>Unreviewed.</b> No one has recorded a decision.</>}
        </p>
      </div>
      {reviewable ? (
        <form className="inspector__block review-form" onSubmit={submit} noValidate>
          <div className={`field${error?.field === "reviewer" ? " field--error" : ""}`}>
            <label htmlFor="reviewer">Reviewer</label>
            <input id="reviewer" value={reviewer} maxLength={100} autoComplete="name"
              aria-invalid={error?.field === "reviewer"} aria-describedby={error?.field === "reviewer" ? "reviewer-error" : undefined}
              onChange={(event) => setReviewer(event.target.value)} />
            {error?.field === "reviewer" && <span id="reviewer-error" className="error-text">{error.text}</span>}
          </div>
          <div className="field">
            <label htmlFor="notes">Notes <span className="hint">(optional)</span></label>
            <textarea id="notes" rows={2} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </div>
          {!imported && record.analysis && (
            <div className={`field${error?.field === "correction" ? " field--error" : ""}`}>
              <label className="review-form__check">
                <input type="checkbox" checked={correct} onChange={(event) => setCorrect(event.target.checked)} /> Save a corrected analysis
              </label>
              {correct && (
                <textarea rows={10} className="mono" aria-label="Corrected analysis JSON" value={correction}
                  onChange={(event) => setCorrection(event.target.value)} />
              )}
              {error?.field === "correction" && <span className="error-text">{error.text}</span>}
            </div>
          )}
          <div className="inspector__actions">
            <button className="btn btn--primary" name="decision" value="approved" disabled={busy}>Approve</button>
            <button className="btn" name="decision" value="rejected" disabled={busy}>Reject</button>
          </div>
          {error?.field === "form" && <p className="error-text" role="alert">{error.text}</p>}
          {saved && <p className="inspector__saved" role="status">{saved}</p>}
        </form>
      ) : (
        <div className="inspector__block"><p className="muted">Decisions open once the analysis finishes.</p></div>
      )}
      <div className="inspector__block">
        <h3 className="eyebrow">Custody log</h3>
        {custody ? (
          <ol className="custody">
            {custody.map((entry, index) => (
              <li key={index}>
                <time className="mono" dateTime={entry.at}>{dateTime(entry.at)}</time>
                <span><b>{ACTION[entry.action] ?? entry.action}</b> · {entry.actor}</span>
                {entry.detail && <span className="muted">{entry.detail}</span>}
              </li>
            ))}
          </ol>
        ) : <div className="skeleton" aria-label="Loading the custody log"><i /><i /></div>}
      </div>
    </>
  );
}

function RawTab({ record }: TabProps) {
  const verification = record.verification;
  const provenance = (record.tier1_event ? verification?.provenance : record.provenance) ?? {};
  const raw = record.tier1_event ? verification?.raw_response : record.raw_response;
  return (
    <>
      <div className="inspector__block">
        <Plate rows={[
          ["Model", provenance.model_id ?? null, true],
          ["Revision", provenance.resolved_revision ? shortHash(String(provenance.resolved_revision)) : null],
          ["Prompt", (record.tier1_event ? verification?.prompt_version : record.prompt_version) ?? null],
          ["Inference", provenance.inference_seconds !== undefined ? `${provenance.inference_seconds} s` : null],
          ["Input tokens", provenance.input_tokens ?? null],
          ["Peak GPU memory", provenance.peak_allocated_mib !== undefined ? `${provenance.peak_allocated_mib} MiB` : null],
          ["Hit token limit", provenance.generation_limit_reached === undefined ? null : provenance.generation_limit_reached ? "Yes" : "No"],
        ]} />
      </div>
      <div className="inspector__block">
        <h3 className="eyebrow">Model response as received</h3>
        <pre className="inspector__raw">{raw ?? "No model response yet."}</pre>
      </div>
    </>
  );
}

const PANELS: Record<Tab, (props: TabProps) => ReactNode> = {
  verdict: VerdictTab, detection: DetectionTab, review: ReviewTab, raw: RawTab,
};

export function Inspector({ record, loading, onFrame, onRecord }: {
  record: RecordDetail | null; loading: boolean; onFrame: (frame: number) => void; onRecord: (record: RecordDetail) => void;
}) {
  const [tab, setTab] = useStoredString("traffic-inspector-tab", "verdict");
  const current = (TABS.some(([key]) => key === tab) ? tab : "verdict") as Tab;
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKey(event: KeyboardEvent<HTMLDivElement>) {
    const index = TABS.findIndex(([key]) => key === current);
    const next = event.key === "ArrowRight" ? index + 1 : event.key === "ArrowLeft" ? index - 1 : null;
    if (next === null) return;
    event.preventDefault();
    const [key] = TABS[(next + TABS.length) % TABS.length];
    setTab(key);
    refs.current[key]?.focus();
  }

  const Panel = PANELS[current];
  return (
    <aside className="inspector" aria-label="Inspector">
      <div className="panel-tabs" role="tablist" aria-label="Event details" onKeyDown={onKey}>
        {TABS.map(([key, label]) => (
          <button key={key} ref={(node) => { refs.current[key] = node; }} type="button" role="tab" id={`tab-${key}`}
            aria-selected={key === current} aria-controls="inspector-panel" tabIndex={key === current ? 0 : -1}
            onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      <div className="inspector__panel" role="tabpanel" id="inspector-panel" aria-labelledby={`tab-${current}`}>
        {record ? <Panel record={record} onFrame={onFrame} onRecord={onRecord} />
          : loading ? <div className="inspector__block"><div className="skeleton" aria-label="Loading"><i /><i /><i /></div></div>
          : <div className="inspector__block"><p className="muted">Open an event to see how Tier-2 judged it, the detector data, and the review form.</p></div>}
      </div>
      {record && (
        <div className="inspector__downloads">
          {record.tier1_event && <a className="btn btn--small" href={files.report(record.id)}>Download report</a>}
          <a className="btn btn--small" href={files.record(record.id)}>Record JSON</a>
          <a className="btn btn--small" href={files.original(record.id)}>{record.tier1_event ? "Original frame" : "Original image"}</a>
        </div>
      )}
    </aside>
  );
}
