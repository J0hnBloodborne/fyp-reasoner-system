import { useEffect, useRef, useState, type CSSProperties, type MutableRefObject, type ReactNode } from "react";
import { files, type Frame, type RecordDetail, type RecordSummary } from "../api";
import { Tally } from "../components/Tally";
import { duration, fpsLabel, markOf, OUTCOME_LABEL, timecode, typeLabel } from "../format";
import { milepostStep } from "./recordings";
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

/** Keyboard control of whichever view the monitor shows. */
export interface Deck {
  step: (frames: number) => void;
  toggle: () => void;
  toIn: () => void;
  toOut: () => void;
  toTrigger: () => void;
  goTo: (frame: number) => void;
}

export type MonitorMode = "footage" | "frames";

export interface MonitorProps {
  record: RecordDetail | null;
  loading: boolean;
  error: string | null;
  siblings: RecordSummary[];
  mode: MonitorMode;
  onMode: (mode: MonitorMode) => void;
  deck: MutableRefObject<Deck | null>;
  position: { index: number; total: number } | null;
  onStep: (offset: number) => void;
  onOpen: (id: string) => void;
  emptyText: string;
}

export function sortedFrames(record: RecordDetail | null): Frame[] {
  return [...(record?.tier1_event?.frames ?? [])].sort((a, b) => a.frame_index - b.frame_index);
}

/** Dark surround with a picture box sized to the frame, so overlays sit on the picture. */
function Screen({ ratio, label, tc, children }: { ratio: number; label: string; tc: string; children: ReactNode }) {
  return (
    <div className="monitor__screen">
      <div className="monitor__picture" style={{ "--ratio": ratio } as CSSProperties}>
        {children}
        <span className="monitor__safe" aria-hidden="true" />
        <span className="burn monitor__label">{label}</span>
        <span className="burn monitor__tc" aria-hidden="true">{tc}</span>
      </div>
    </div>
  );
}

function EventNav({ position, onStep }: Pick<MonitorProps, "position" | "onStep">) {
  if (!position) return null;
  return (
    <div className="monitor__events">
      <span className="mono">Event {position.index + 1} of {position.total}</span>
      <button type="button" className="btn btn--small" onClick={() => onStep(-1)} disabled={position.index === 0} aria-keyshortcuts="ArrowUp">Previous</button>
      <button type="button" className="btn btn--small" onClick={() => onStep(1)} disabled={position.index === position.total - 1} aria-keyshortcuts="ArrowDown">Next</button>
    </div>
  );
}

function Bar({ left, right, children }: { left: ReactNode; right: ReactNode; children: ReactNode }) {
  return (
    <div className="monitor__bar">
      <span className="monitor__inout mono">{left}</span>
      <div className="monitor__transport" role="group" aria-label="Playback">{children}</div>
      <span className="monitor__where mono">{right}</span>
    </div>
  );
}

/** The uploaded video, paused on the trigger, with a clip ruler and in/out points. */
function Footage({ record, siblings, deck, onOpen }: { record: RecordDetail; siblings: RecordSummary[]; deck: MutableRefObject<Deck | null>; onOpen: (id: string) => void }) {
  const event = record.tier1_event!;
  const fps = event.fps ?? 30;
  const frames = sortedFrames(record);
  const first = frames[0].frame_index;
  const last = frames[frames.length - 1].frame_index;
  const video = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState((event.trigger_frame - 0.5) / fps);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(false);
  const total = event.frame_count;
  const frame = Math.min(total, Math.floor(time * fps + 1e-6) + 1);

  // Seek to the middle of a frame so rounding never lands on its neighbour.
  const seek = (target: number) => {
    const element = video.current;
    if (!element) return;
    element.currentTime = (Math.max(1, Math.min(total, target)) - 0.5) / fps;
    setTime(element.currentTime);
  };
  const toggle = () => {
    const element = video.current;
    if (!element) return;
    if (element.paused) element.play().catch(() => setError(true));
    else element.pause();
  };
  const stepBy = (count: number) => { video.current?.pause(); seek(frame + count); };

  useEffect(() => {
    deck.current = { step: stepBy, toggle, toIn: () => seek(first), toOut: () => seek(last), toTrigger: () => seek(event.trigger_frame), goTo: seek };
    return () => { deck.current = null; };
  });

  useEffect(() => {
    setError(false);
    setTime((event.trigger_frame - 0.5) / fps);
    const element = video.current;
    if (!element) return;
    let handle = 0;
    const tick = () => {
      setTime(element.currentTime);
      handle = element.requestVideoFrameCallback(tick);
    };
    if ("requestVideoFrameCallback" in element) handle = element.requestVideoFrameCallback(tick);
    const onTime = () => setTime(element.currentTime);
    element.addEventListener("timeupdate", onTime);
    element.addEventListener("seeked", onTime);
    return () => {
      if ("cancelVideoFrameCallback" in element) element.cancelVideoFrameCallback(handle);
      element.removeEventListener("timeupdate", onTime);
      element.removeEventListener("seeked", onTime);
    };
  }, [record.id]);

  const spacing = milepostStep(total / fps);
  const ticks = Array.from({ length: Math.floor(total / fps / spacing) + 1 }, (_, i) => i * spacing);
  const at = (f: number) => `${((f - 1) / total) * 100}%`;
  function seekRuler(clientX: number, element: HTMLElement) {
    const box = element.getBoundingClientRect();
    video.current?.pause();
    seek(Math.round(((clientX - box.left) / box.width) * total) + 1);
  }

  return (
    <>
      <Screen ratio={frames[0].width / frames[0].height} label={`${event.source_video}${frame >= first && frame <= last ? " · IN" : ""}`} tc={timecode(frame, fps)}>
        <video
          key={record.id}
          ref={video}
          src={files.video(event.video_id!)}
          muted
          playsInline
          preload="auto"
          onLoadedMetadata={() => seek(event.trigger_frame)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onError={() => setError(true)}
          aria-label={`Footage of ${event.source_video}, paused at trigger frame ${event.trigger_frame}`}
        />
        {error && <span className="monitor__notice">This browser cannot play the file. Install ffmpeg so the server can make a preview copy, then upload the video again.</span>}
      </Screen>
      <Bar left={<>IN {timecode(first, fps)} · OUT {timecode(last, fps)}</>} right={<>F{frame} / {total} · {duration(total / fps)}</>}>
        <Transport label="Go to in point (Home)" icon="in" onClick={() => seek(first)} />
        <Transport label="Previous frame (Left arrow)" icon="back" onClick={() => stepBy(-1)} />
        <Transport label={playing ? "Pause (Space)" : "Play (Space)"} icon={playing ? "pause" : "play"} onClick={toggle} pressed={playing} />
        <Transport label="Next frame (Right arrow)" icon="forward" onClick={() => stepBy(1)} />
        <Transport label="Go to out point (End)" icon="out" onClick={() => seek(last)} />
      </Bar>
      <div className="clip-ruler">
        <div className="clip-ruler__track" onPointerDown={(e) => seekRuler(e.clientX, e.currentTarget)} aria-label="Clip ruler. Click to move the playhead.">
          {ticks.map((second) => (
            <span key={second} className="clip-ruler__tick" style={{ left: `${((second * fps) / total) * 100}%` }}>
              <i>{timecode(Math.round(second * fps) + 1, fps).slice(3, 8)}</i>
            </span>
          ))}
          <span className="clip-ruler__inout" style={{ left: at(first), width: `${((last - first + 1) / total) * 100}%` }} />
          {siblings.map((item) => (
            <button key={item.id} type="button" className={`clip-ruler__ev mk--${markOf(item)}`} aria-pressed={item.id === record.id}
              style={{ left: at(item.trigger_frame ?? 1) }} aria-label={`Open event at frame ${item.trigger_frame}`}
              onPointerDown={(e) => e.stopPropagation()} onClick={() => onOpen(item.id)} />
          ))}
          <span className="clip-ruler__head" style={{ left: at(frame) }} />
        </div>
      </div>
    </>
  );
}

/** The frames Tier-2 saw, stepped or looped, as a filmstrip between in and out brackets. */
function Frames({ record, deck }: { record: RecordDetail; deck: MutableRefObject<Deck | null> }) {
  const event = record.tier1_event!;
  const frames = sortedFrames(record);
  const [current, setCurrent] = useState(event.trigger_frame);
  const [playing, setPlaying] = useState(false);
  const index = Math.max(0, frames.findIndex((item) => item.frame_index === current));
  const shown = frames[index];
  const cited = new Set((record.verification?.result?.observations ?? []).map((item) => item.frame_index));
  const observation = record.verification?.result?.observations.find((item) => item.frame_index === current);
  const go = (next: number) => setCurrent(frames[Math.min(frames.length - 1, Math.max(0, next))].frame_index);

  useEffect(() => { setCurrent(event.trigger_frame); setPlaying(false); }, [record.id]);
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setCurrent((value) => {
      const at = frames.findIndex((item) => item.frame_index === value);
      return frames[(at + 1) % frames.length].frame_index;
    }), 250);
    return () => window.clearInterval(timer);
  }, [playing, record.id]);
  useEffect(() => {
    deck.current = {
      step: (count) => { setPlaying(false); go(index + count); },
      toggle: () => { if (frames.length > 1) setPlaying((value) => !value); },
      toIn: () => go(0),
      toOut: () => go(frames.length - 1),
      toTrigger: () => { setPlaying(false); setCurrent(event.trigger_frame); },
      goTo: (frame) => { setPlaying(false); setCurrent(frame); },
    };
    return () => { deck.current = null; };
  });

  const role = current === event.trigger_frame ? "trigger" : "context";
  const first = frames[0].frame_index;
  const last = frames[frames.length - 1].frame_index;
  const spanMs = event.fps ? Math.round(((last - first + 1) / event.fps) * 1000) : null;
  return (
    <>
      <Screen ratio={shown.width / shown.height} label={`F${current}${role === "trigger" ? " · TRIGGER" : ""}`} tc={timecode(current, event.fps)}>
        <img key={current} src={files.frame(record.id, current)}
          alt={`Frame ${current} of ${event.source_video}, ${role} frame.${observation ? ` Tier-2 noted: ${observation.description}` : ""}`} />
        {event.evidence_origin !== "raw_frame" && <span className="monitor__notice">Annotated preview. Not valid evidence for Tier-2.</span>}
      </Screen>
      <Bar
        left={<>{frames.length} frames{spanMs !== null && ` · ${spanMs} ms`}</>}
        right={<a className="monitor__save" href={files.frame(record.id, current)} download={`${event.source_video.replace(/\.[^.]+$/, "")}-frame-${current}`}>Save frame</a>}
      >
        <Transport label="First frame (Home)" icon="in" onClick={() => go(0)} disabled={index === 0} />
        <Transport label="Previous frame (Left arrow)" icon="back" onClick={() => { setPlaying(false); go(index - 1); }} disabled={index === 0} />
        <Transport label={playing ? "Pause (Space)" : "Loop the window (Space)"} icon={playing ? "pause" : "play"} onClick={() => setPlaying(!playing)} pressed={playing} disabled={frames.length < 2} />
        <Transport label="Next frame (Right arrow)" icon="forward" onClick={() => { setPlaying(false); go(index + 1); }} disabled={index === frames.length - 1} />
        <Transport label="Last frame (End)" icon="out" onClick={() => go(frames.length - 1)} disabled={index === frames.length - 1} />
      </Bar>
      <ol className="filmstrip" style={{ gridTemplateColumns: `repeat(${frames.length}, minmax(0, 120px))` }}>
        {frames.map((frame) => {
          const offset = frame.frame_index - event.trigger_frame;
          return (
            <li key={frame.frame_index}>
              <button type="button" aria-pressed={frame.frame_index === current} onClick={() => { setPlaying(false); setCurrent(frame.frame_index); }}
                aria-label={`Frame ${frame.frame_index}${offset === 0 ? ", trigger" : ""}${cited.has(frame.frame_index) ? ", cited by Tier-2" : ""}`}>
                <img src={files.frame(record.id, frame.frame_index)} alt="" loading="lazy" />
                <span className="filmstrip__cap">
                  {cited.has(frame.frame_index) && <i className="kf" title="Cited by Tier-2" aria-hidden="true" />}
                  <span>{frame.frame_index}</span>
                  <span className="filmstrip__offset">{offset === 0 ? "TRG" : offset > 0 ? `+${offset}` : `−${-offset}`}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </>
  );
}

function StillView({ record }: { record: RecordDetail }) {
  return (
    <>
      <Screen ratio={record.evidence.width / record.evidence.height} label="STILL" tc={record.filename}>
        <img src={files.image(record.id)} alt={record.analysis ? `Uploaded image ${record.filename}. Model summary: ${record.analysis.summary}` : `Uploaded image ${record.filename}`} />
      </Screen>
      <Bar left={`${record.evidence.width} × ${record.evidence.height} px`} right={record.evidence.model_width ? `model saw ${record.evidence.model_width} × ${record.evidence.model_height}` : ""}>{null}</Bar>
    </>
  );
}

function Head({ record, position, onStep }: { record: RecordDetail } & Pick<MonitorProps, "position" | "onStep">) {
  const event = record.tier1_event;
  if (!event) {
    const types = (record.analysis?.findings ?? []).map((finding) => typeLabel(finding.violation_type));
    return (
      <header className="monitor__head">
        <div className="monitor__title">
          <h1>{types.length ? [...new Set(types)].join(", ") : "Uploaded image"}</h1>
          <p className="mono">{[record.filename, record.location, record.captured_at].filter(Boolean).join(" · ")}</p>
        </div>
        <span className="tally tally--large tally--unverified">{record.analysis ? OUTCOME_LABEL[record.analysis.outcome] : record.status === "failed" ? "Analysis failed" : "Analyzing"}</span>
        <EventNav position={position} onStep={onStep} />
      </header>
    );
  }
  const mark = markOf({ verdict: record.verification?.result?.verdict ?? null, verification_status: record.verification?.status ?? null });
  return (
    <header className="monitor__head">
      <div className="monitor__title">
        <h1>{event.trigger_type}</h1>
        <p className="mono">{[event.source_video, event.camera_type, `track ${event.target_id}`, `trigger ${timecode(event.trigger_frame, event.fps)}`, event.fps && fpsLabel(event.fps)].filter(Boolean).join(" · ")}</p>
      </div>
      <Tally mark={mark} status={record.verification?.status} large />
      <EventNav position={position} onStep={onStep} />
    </header>
  );
}

export function Monitor(props: MonitorProps) {
  const { record, loading, error, emptyText, mode, onMode } = props;
  let body: ReactNode;
  if (error) {
    body = <div className="viewer"><div className="monitor__screen monitor__screen--empty"><p className="error-text">{error}</p></div></div>;
  } else if (loading && !record) {
    body = <div className="viewer" aria-busy="true"><div className="monitor__screen monitor__screen--empty"><div className="skeleton monitor__skeleton" aria-label="Loading the event"><i /><i /><i /></div></div></div>;
  } else if (!record) {
    body = (
      <div className="viewer">
        <div className="monitor__screen monitor__screen--empty">
          <div className="monitor__slate"><span className="burn">--:--:--:--</span><p>{emptyText}</p></div>
        </div>
      </div>
    );
  } else {
    const hasVideo = !!record.tier1_event?.video_id;
    const view = !record.tier1_event ? "still" : hasVideo && mode === "footage" ? "footage" : "frames";
    body = (
      <>
        <Head record={record} position={props.position} onStep={props.onStep} />
        <div className="viewer">
          {record.tier1_event && (
            <div className="viewer__modes" role="group" aria-label="Monitor source">
              <button type="button" aria-pressed={view === "footage"} disabled={!hasVideo} onClick={() => onMode("footage")}
                title={hasVideo ? undefined : "Only videos uploaded to TrafficSeek have footage. Bundles carry frames only."}>Footage</button>
              <button type="button" aria-pressed={view === "frames"} onClick={() => onMode("frames")}>Frames Tier-2 saw</button>
            </div>
          )}
          {view === "footage" && <Footage record={record} siblings={props.siblings} deck={props.deck} onOpen={props.onOpen} />}
          {view === "frames" && <Frames record={record} deck={props.deck} />}
          {view === "still" && <StillView record={record} />}
        </div>
      </>
    );
  }
  return <section className="monitor" aria-label="Monitor">{body}</section>;
}
