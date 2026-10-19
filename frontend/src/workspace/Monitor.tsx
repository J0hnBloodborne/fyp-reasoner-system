import type { CSSProperties, ReactNode } from "react";
import { files, type Frame, type RecordDetail } from "../api";
import { Sign } from "../components/Sign";
import { duration, fpsLabel, markOf, OUTCOME_LABEL, timecode, typeLabel } from "../format";
import "./Monitor.css";

const ICONS: Record<string, ReactNode> = {
  in: <><path d="M2 3h4v1.6H3.6v6.8H6V13H2z" /><path d="M14 3v10L7.5 8z" /></>,
  back: <><path d="M10.5 3v10L4 8z" /><path d="M11.5 3h2v10h-2z" /></>,
  play: <path d="M4 2.5v11L13.5 8z" />,
  pause: <path d="M4 3h3v10H4zM9 3h3v10H9z" />,
  forward: <><path d="M2.5 3h2v10h-2z" /><path d="M5.5 3v10L12 8z" /></>,
  out: <><path d="M2 3v10l6.5-5z" /><path d="M10 3h4v10h-4v-1.6h2.4V4.6H10z" /></>,
};

function Transport({ label, icon, onClick, disabled, pressed }: {
  label: string; icon: string; onClick: () => void; disabled?: boolean; pressed?: boolean;
}) {
  return (
    <button type="button" className="transport" aria-label={label} title={label} onClick={onClick} disabled={disabled} aria-pressed={pressed}>
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor">{ICONS[icon]}</svg>
    </button>
  );
}

/** Dark surround with a picture box sized to the frame, so overlays sit on the picture itself. */
function Screen({ ratio, children }: { ratio: number; children: ReactNode }) {
  return (
    <div className="monitor__screen">
      <div className="monitor__picture" style={{ "--ratio": ratio } as CSSProperties}>{children}</div>
    </div>
  );
}

export interface MonitorProps {
  record: RecordDetail | null;
  loading: boolean;
  error: string | null;
  frame: number | null;
  onFrame: (frame: number) => void;
  playing: boolean;
  onPlaying: (playing: boolean) => void;
  position: { index: number; total: number } | null;
  onStep: (offset: number) => void;
  emptyText: string;
}

export function sortedFrames(record: RecordDetail | null): Frame[] {
  return [...(record?.tier1_event?.frames ?? [])].sort((a, b) => a.frame_index - b.frame_index);
}

function EventNav({ position, onStep }: Pick<MonitorProps, "position" | "onStep">) {
  if (!position) return null;
  return (
    <div className="monitor__events">
      <span className="mono">Event {position.index + 1} of {position.total}</span>
      <button type="button" className="btn btn--small" onClick={() => onStep(-1)} disabled={position.index === 0} aria-keyshortcuts="ArrowUp">
        Previous
      </button>
      <button type="button" className="btn btn--small" onClick={() => onStep(1)} disabled={position.index === position.total - 1} aria-keyshortcuts="ArrowDown">
        Next
      </button>
    </div>
  );
}

function Filmstrip({ record, frames, current, onFrame }: { record: RecordDetail; frames: Frame[]; current: number; onFrame: (frame: number) => void }) {
  const event = record.tier1_event!;
  const cited = new Set((record.verification?.result?.observations ?? []).map((item) => item.frame_index));
  const first = frames[0].frame_index;
  const last = frames[frames.length - 1].frame_index;
  const spanMs = event.fps ? Math.round(((last - first + 1) / event.fps) * 1000) : null;
  return (
    <div className="filmstrip">
      <div className="filmstrip__head">
        <span>
          <b>Window Tier-2 saw</b>
          <span className="mono"> {timecode(first, event.fps)} to {timecode(last, event.fps)} · {frames.length} frames{spanMs !== null && ` · ${spanMs} ms`}</span>
        </span>
        {cited.size > 0 && <span className="filmstrip__key"><i className="kf" aria-hidden="true" /> cited by Tier-2</span>}
      </div>
      <ol className="filmstrip__frames" style={{ gridTemplateColumns: `repeat(${frames.length}, minmax(0, 120px))` }}>
        {frames.map((frame) => {
          const offset = frame.frame_index - event.trigger_frame;
          const where = offset === 0 ? "trigger" : offset < 0 ? `${-offset} before` : `${offset} after`;
          return (
            <li key={frame.frame_index}>
              <button type="button" aria-pressed={frame.frame_index === current} onClick={() => onFrame(frame.frame_index)}
                aria-label={`Frame ${frame.frame_index}, ${where}${cited.has(frame.frame_index) ? ", cited by Tier-2" : ""}`}>
                <img src={files.frame(record.id, frame.frame_index)} alt="" loading="lazy" />
                <span className="filmstrip__cap">
                  {cited.has(frame.frame_index) && <i className="kf" aria-hidden="true" />}
                  <span className="mono">{frame.frame_index}</span>
                  <span className={offset === 0 ? "filmstrip__trigger" : "muted"}>{offset === 0 ? "trigger" : offset > 0 ? `+${offset}` : `−${-offset}`}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Tier1View(props: MonitorProps & { record: RecordDetail }) {
  const { record, frame, onFrame, playing, onPlaying } = props;
  const event = record.tier1_event!;
  const frames = sortedFrames(record);
  const current = frame ?? event.trigger_frame;
  const index = frames.findIndex((item) => item.frame_index === current);
  const shown = frames[index];
  const observation = record.verification?.result?.observations.find((item) => item.frame_index === current);
  const role = current === event.trigger_frame ? "trigger" : "context";
  const step = (offset: number) => onFrame(frames[Math.min(frames.length - 1, Math.max(0, index + offset))].frame_index);
  const mark = markOf({ verdict: record.verification?.result?.verdict ?? null, verification_status: record.verification?.status ?? null });
  const total = event.fps ? event.frame_count / event.fps : null;

  return (
    <>
      <header className="monitor__head">
        <div className="monitor__title">
          <h1>{event.trigger_type}</h1>
          <p className="mono">{[event.source_video, event.camera_type, `track ${event.target_id}`, event.fps && fpsLabel(event.fps)].filter(Boolean).join(" · ")}</p>
        </div>
        <Sign mark={mark} status={record.verification?.status} large />
        <EventNav position={props.position} onStep={props.onStep} />
      </header>
      <Screen ratio={shown ? shown.width / shown.height : 16 / 9}>
        <img
          key={current}
          src={files.frame(record.id, current)}
          alt={`Frame ${current} of ${event.source_video}, ${role} frame.${observation ? ` Tier-2 noted: ${observation.description}` : ""}`}
        />
        <span className="exit-tab">FRAME {current}{role === "trigger" ? " · TRIGGER" : ""}</span>
        {event.evidence_origin !== "raw_frame" && <span className="monitor__notice">Annotated preview. Not valid evidence for Tier-2.</span>}
      </Screen>
      <div className="monitor__bar">
        <output className="timecode" aria-label="Timecode">{timecode(current, event.fps)}</output>
        <div className="monitor__transport" role="group" aria-label="Frame controls">
          <Transport label="First frame (Home)" icon="in" onClick={() => onFrame(frames[0].frame_index)} disabled={index <= 0} />
          <Transport label="Previous frame (Left arrow)" icon="back" onClick={() => step(-1)} disabled={index <= 0} />
          <Transport label={playing ? "Pause (Space)" : "Play the window in a loop (Space)"} icon={playing ? "pause" : "play"}
            onClick={() => onPlaying(!playing)} pressed={playing} disabled={frames.length < 2} />
          <Transport label="Next frame (Right arrow)" icon="forward" onClick={() => step(1)} disabled={index >= frames.length - 1} />
          <Transport label="Last frame (End)" icon="out" onClick={() => onFrame(frames[frames.length - 1].frame_index)} disabled={index >= frames.length - 1} />
        </div>
        <span className="monitor__where mono">
          F{current} of {event.frame_count}{total !== null && ` · ${duration(total)}`}
          <a className="monitor__save" href={files.frame(record.id, current)} download={`${event.source_video.replace(/\.[^.]+$/, "")}-frame-${current}`}>Save frame</a>
        </span>
      </div>
      <Filmstrip record={record} frames={frames} current={current} onFrame={onFrame} />
    </>
  );
}

function StillView({ record, position, onStep }: MonitorProps & { record: RecordDetail }) {
  const types = (record.analysis?.findings ?? []).map((finding) => typeLabel(finding.violation_type));
  return (
    <>
      <header className="monitor__head">
        <div className="monitor__title">
          <h1>{types.length ? [...new Set(types)].join(", ") : "Uploaded image"}</h1>
          <p className="mono">{[record.filename, record.location, record.captured_at].filter(Boolean).join(" · ")}</p>
        </div>
        <span className="sign sign--pending sign--large">
          {record.analysis ? OUTCOME_LABEL[record.analysis.outcome] : record.status === "failed" ? "Analysis failed" : "Analyzing"}
        </span>
        <EventNav position={position} onStep={onStep} />
      </header>
      <Screen ratio={record.evidence.width / record.evidence.height}>
        <img src={files.image(record.id)} alt={record.analysis ? `Uploaded image ${record.filename}. Model summary: ${record.analysis.summary}` : `Uploaded image ${record.filename}`} />
        <span className="exit-tab">STILL IMAGE</span>
      </Screen>
      <div className="monitor__bar">
        <span className="monitor__where mono">
          {record.evidence.width} × {record.evidence.height} px
          {record.evidence.model_width && ` · model saw ${record.evidence.model_width} × ${record.evidence.model_height}`}
        </span>
      </div>
    </>
  );
}

export function Monitor(props: MonitorProps) {
  const { record, loading, error, emptyText } = props;
  let body: ReactNode;
  if (error) {
    body = (
      <div className="monitor__screen monitor__screen--empty">
        <p className="error-text">{error}</p>
      </div>
    );
  } else if (loading && !record) {
    body = (
      <div className="monitor__screen monitor__screen--empty" aria-busy="true">
        <div className="skeleton monitor__skeleton" aria-label="Loading the event"><i /><i /><i /></div>
      </div>
    );
  } else if (!record) {
    body = (
      <div className="monitor__screen monitor__screen--empty">
        <div className="monitor__slate">
          <p className="eyebrow">No event open</p>
          <p>{emptyText}</p>
        </div>
      </div>
    );
  } else if (record.tier1_event) {
    body = <Tier1View {...props} record={record} />;
  } else {
    body = <StillView {...props} record={record} />;
  }
  return <section className="monitor" aria-label="Evidence monitor">{body}</section>;
}
