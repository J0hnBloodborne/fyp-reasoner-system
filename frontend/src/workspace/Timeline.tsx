import { files, type RecordSummary } from "../api";
import { duration, eventTitle, fpsLabel, markOf, OUTCOME_LABEL, STATUS_LABEL, timecode, VERDICT_LABEL } from "../format";
import { countMarks, milepostStep, type Recording } from "./recordings";
import "./Timeline.css";

function markerLabel(event: RecordSummary) {
  const state = event.verdict
    ? VERDICT_LABEL[event.verdict]
    : event.verification_status ? STATUS_LABEL[event.verification_status] : "not verified";
  return `${eventTitle(event)}, frame ${event.trigger_frame}, ${state}`;
}

function Track({ recording, selectedId, onSelect }: {
  recording: Recording; selectedId: string | null; onSelect: (id: string) => void;
}) {
  const { frameCount, fps, events } = recording;
  const seconds = fps ? frameCount / fps : null;
  const step = seconds ? milepostStep(seconds) : null;
  const posts = seconds && step ? Array.from({ length: Math.floor(seconds / step) + 1 }, (_, i) => i * step) : [];
  const at = (frame: number) => `${((frame - 1) / Math.max(frameCount, 1)) * 100}%`;
  const counts = countMarks(events);
  const unverified = counts.pending + counts.failed + counts.skipped + counts.unverified;
  const selected = events.find((event) => event.id === selectedId);
  const tally = [
    counts.supported && `${counts.supported} supported`,
    counts.not_supported && `${counts.not_supported} not supported`,
    counts.insufficient_evidence && `${counts.insufficient_evidence} insufficient`,
    unverified && `${unverified} not verified`,
  ].filter(Boolean).join(" · ");

  return (
    <div className={`track${selected ? " track--active" : ""}`} role="group" aria-label={`${recording.name}, ${events.length} events`}>
      <div className="track__head">
        <b title={recording.name}>{recording.name}</b>
        <span className="mono">
          {[recording.camera, seconds && duration(seconds), fps && fpsLabel(fps)].filter(Boolean).join(" · ")}
          {recording.sharedName && recording.bundleId && ` · bundle ${recording.bundleId.slice(0, 6)}`}
        </span>
        <span className="track__tally">{events.length} {events.length === 1 ? "event" : "events"}{tally && ` · ${tally}`}</span>
      </div>
      <div className="track__lane">
        <span className="track__road" />
        {posts.map((second) => (
          <span key={second} className="track__post" style={{ left: `${(second / seconds!) * 100}%` }}>
            {second === 0 ? "0 s" : second}
          </span>
        ))}
        {selected?.trigger_frame && (
          <span className="playhead" style={{ left: at(selected.trigger_frame) }}>
            <span className="playhead__flag">{timecode(selected.trigger_frame, fps)}</span>
          </span>
        )}
        {events.map((event) => (
          <button
            key={event.id}
            type="button"
            className={`mk mk--${markOf(event)}`}
            style={{ left: at(event.trigger_frame ?? 1) }}
            aria-label={markerLabel(event)}
            aria-pressed={event.id === selectedId}
            title={markerLabel(event)}
            onClick={() => onSelect(event.id)}
          />
        ))}
      </div>
    </div>
  );
}

function Stills({ stills, selectedId, onSelect }: { stills: RecordSummary[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="track track--stills" role="group" aria-label={`Uploaded images, ${stills.length}`}>
      <div className="track__head">
        <b>Uploaded images</b>
        <span className="track__tally">{stills.length} {stills.length === 1 ? "image" : "images"} · single-frame checks</span>
      </div>
      <div className="stills">
        {stills.map((still) => {
          const label = still.outcome ? OUTCOME_LABEL[still.outcome] : still.status === "failed" ? "Analysis failed" : "Analyzing";
          return (
            <button key={still.id} type="button" className="still" aria-pressed={still.id === selectedId}
              onClick={() => onSelect(still.id)} title={`${eventTitle(still)}: ${label}`}>
              <img src={files.image(still.id)} alt="" loading="lazy" />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function Legend() {
  return (
    <span className="legend" aria-label="Marker shapes">
      <span><i className="mk mk--supported" />Supported</span>
      <span><i className="mk mk--not_supported" />Not supported</span>
      <span><i className="mk mk--insufficient_evidence" />Insufficient</span>
      <span><i className="mk mk--unverified" />Not verified</span>
    </span>
  );
}

export function Timeline({ recordings, stills, selectedId, onSelect }: {
  recordings: Recording[]; stills: RecordSummary[]; selectedId: string | null; onSelect: (id: string) => void;
}) {
  return (
    <div className="timeline">
      {recordings.map((recording) => (
        <Track key={recording.key} recording={recording} selectedId={selectedId} onSelect={onSelect} />
      ))}
      {stills.length > 0 && <Stills stills={stills} selectedId={selectedId} onSelect={onSelect} />}
    </div>
  );
}
