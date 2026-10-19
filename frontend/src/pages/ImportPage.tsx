import { useEffect, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import { api, MAX_BUNDLE_BYTES, MAX_VIDEO_BYTES, uploadVideo, type Video } from "../api";
import { dateTime } from "../format";
import { useInterval } from "../hooks";
import { Link, useTitle } from "../router";
import "./pages.css";

const megabytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const VIDEO_SUFFIXES = [".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm"];
const ACTIVE = new Set(["queued", "preview", "extracting", "detecting", "importing"]);

const STAGE: Record<string, string> = {
  queued: "Waiting for the GPU",
  preview: "Making a preview copy",
  extracting: "Extracting frames",
  detecting: "Running the Tier-1 detector",
  importing: "Importing events",
};

function Dropzone({ accept, hint, file, error, onFile }: {
  accept: string; hint: string; file: File | null; error: boolean; onFile: (file: File | undefined) => void;
}) {
  const [over, setOver] = useState(false);
  function drop(event: DragEvent) {
    event.preventDefault();
    setOver(false);
    onFile(event.dataTransfer.files[0]);
  }
  return (
    <label className={`dropzone${over ? " dropzone--over" : ""}${error ? " dropzone--error" : ""}`}
      onDragOver={(event) => { event.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}>
      <input type="file" accept={accept} className="visually-hidden" onChange={(event) => onFile(event.target.files?.[0])} />
      <span className="dropzone__title">{file ? file.name : "Drop a file here, or choose one"}</span>
      <span className="dropzone__hint">{file ? megabytes(file.size) : hint}</span>
    </label>
  );
}

function VideoStatus({ video }: { video: Video }) {
  if (video.status === "failed") return <p className="error-text">{video.error ?? "Processing failed."}</p>;
  if (video.status === "completed") {
    if (!video.event_count) return <p>No Tier-1 thresholds were crossed, so there are no events to review.</p>;
    return (
      <div className="page__actions">
        <span>Found {video.event_count} {video.event_count === 1 ? "event" : "events"} and sent each to Tier-2 for verification.</span>
        <Link href={`/incident/${video.record_ids[0]}`} className="btn btn--primary">Open the first event</Link>
      </div>
    );
  }
  const progress = video.progress;
  const fraction = progress && progress.stage === video.status && progress.total ? progress.done / progress.total : null;
  return (
    <div className="job__progress" aria-live="polite">
      <span className="mono">
        {STAGE[video.status]}
        {fraction !== null && ` · ${progress!.done} / ${progress!.total} frames`}
      </span>
      <div className="meter" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={fraction === null ? undefined : Math.round(fraction * 100)}>
        <i style={{ width: `${fraction === null ? 4 : Math.max(4, fraction * 100)}%` }} />
      </div>
    </div>
  );
}

function VideoForm({ onUploaded }: { onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [camera, setCamera] = useState("CCTV");
  const [direction, setDirection] = useState("-1");
  const [sent, setSent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  function choose(next: File | undefined) {
    setError(null);
    if (!next) return;
    if (!VIDEO_SUFFIXES.some((suffix) => next.name.toLowerCase().endsWith(suffix))) {
      setError("Choose an MP4, MOV, AVI, MKV or WebM video.");
      return;
    }
    if (next.size > MAX_VIDEO_BYTES) {
      setError(`This file is ${megabytes(next.size)}. Videos can be at most 2 GB. Trim it first.`);
      return;
    }
    setFile(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return setError("Choose a video first.");
    setError(null);
    setSent(0);
    try {
      await uploadVideo(file, { camera_type: camera, allowed_direction: direction }, setSent);
      setFile(null);
      onUploaded();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSent(null);
    }
  }

  return (
    <form className="page__form" onSubmit={submit} noValidate>
      <Dropzone accept={VIDEO_SUFFIXES.join(",")} hint="MP4, MOV, AVI, MKV or WebM, up to 2 GB" file={file} error={!!error} onFile={choose} />
      <div className="page__fields">
        <div className="field">
          <label htmlFor="camera">Camera</label>
          <select id="camera" value={camera} onChange={(event) => setCamera(event.target.value)}>
            <option value="CCTV">Fixed CCTV</option>
            <option value="DASHCAM">Dashcam</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="direction">Normal traffic moves</label>
          <select id="direction" value={direction} onChange={(event) => setDirection(event.target.value)}>
            <option value="-1">Up the screen</option>
            <option value="1">Down the screen</option>
          </select>
          <span className="hint">The wrong-way check flags movement against this.</span>
        </div>
      </div>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="page__actions">
        <button className="btn btn--primary" disabled={sent !== null}>{sent !== null ? `Uploading ${Math.round(sent * 100)}%` : "Upload and detect"}</button>
      </div>
      {sent !== null && <div className="meter"><i style={{ width: `${sent * 100}%` }} /></div>}
    </form>
  );
}

function BundleForm() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ ids: string[]; video: string } | null>(null);

  function choose(next: File | undefined) {
    setError(null);
    if (!next) return;
    if (!next.name.toLowerCase().endsWith(".zip")) return setError("Choose the ZIP file the detector wrote.");
    if (next.size > MAX_BUNDLE_BYTES) return setError(`This file is ${megabytes(next.size)}. Bundles can be at most 256 MB.`);
    setFile(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return setError("Choose a bundle first.");
    setBusy(true);
    setError(null);
    try {
      const { record_ids } = await api.importBundle(file);
      const first = await api.record(record_ids[0]);
      setDone({ ids: record_ids, video: first.tier1_event?.source_video ?? file.name });
      setFile(null);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="page__actions">
        <span>Imported {done.ids.length} {done.ids.length === 1 ? "event" : "events"} from {done.video}. Verification is queued.</span>
        <Link href={`/incident/${done.ids[0]}`} className="btn btn--primary">Open the first event</Link>
        <button type="button" className="link-button" onClick={() => setDone(null)}>Import another</button>
      </div>
    );
  }
  return (
    <form className="page__form" onSubmit={submit} noValidate>
      <Dropzone accept=".zip,application/zip" hint="ZIP, up to 256 MB and 100 events" file={file} error={!!error} onFile={choose} />
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="page__actions">
        <button className="btn" disabled={busy}>{busy ? "Importing" : "Import and verify"}</button>
      </div>
    </form>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="page__section">
      <h2 className="eyebrow">{title}</h2>
      {children}
    </section>
  );
}

export function ImportPage() {
  useTitle("Add footage");
  const [videos, setVideos] = useState<Video[] | null>(null);
  const load = () => api.videos().then(setVideos).catch(() => setVideos([]));
  useEffect(() => { load(); }, []);
  useInterval(load, 1000, !!videos?.some((video) => ACTIVE.has(video.status)));
  const active = videos?.find((video) => ACTIVE.has(video.status));

  return (
    <main className="page" id="main">
      <div className="page__grid">
        <div className="page__main">
          <h1>Add footage</h1>
          <p className="page__lead">Upload a video and TrafficSeek runs the Tier-1 detector on it, imports every event it flags, and has the vision model check each one. You can watch the footage around each event afterwards.</p>
          <Section title="Upload a video">
            {active ? <p className="muted">{active.filename} is being processed. The next upload can start when it finishes.</p> : <VideoForm onUploaded={load} />}
          </Section>
          {videos && videos.length > 0 && (
            <Section title="Videos">
              <ul className="jobs">
                {videos.map((video) => (
                  <li key={video.id} className="job">
                    <div className="job__head">
                      <b>{video.filename}</b>
                      <span className="mono muted">{video.camera_type} · {dateTime(video.created_at)}{video.frame_count ? ` · ${video.frame_count} frames` : ""}</span>
                    </div>
                    <VideoStatus video={video} />
                  </li>
                ))}
              </ul>
            </Section>
          )}
          <Section title="Or import a Tier-1 bundle">
            <p className="muted">For bundles made elsewhere, for example by the detector notebook in Colab.</p>
            <BundleForm />
          </Section>
        </div>
        <aside className="page__aside">
          <h2 className="eyebrow">What happens</h2>
          <ol className="page__list">
            <li>A 720p preview copy is made for playback.</li>
            <li>Every frame is decoded, and YOLO with ByteTrack tracks vehicles and people.</li>
            <li>The Tier-1 heuristics flag wrong-way driving, collisions, unsafe following and red-light running.</li>
            <li>Each event is imported with the frames around it and queued for Tier-2.</li>
          </ol>
          <h2 className="eyebrow">Time and limits</h2>
          <p>Detection and Tier-2 share the GPU, so one video is processed at a time. A 35-second, 60 fps clip takes about two minutes on an RTX 3070. Busy footage can produce hundreds of triggers; they are imported in bundles of 100.</p>
          <h2 className="eyebrow">From the command line</h2>
          <pre className="page__code">python -m traffic_poc detect video.mp4</pre>
          <p>This writes <code>data/video_tier1.zip</code> for the bundle import.</p>
        </aside>
      </div>
    </main>
  );
}
