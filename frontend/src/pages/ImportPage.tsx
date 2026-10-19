import { useState, type DragEvent, type FormEvent } from "react";
import { api, MAX_BUNDLE_BYTES } from "../api";
import { Link, useTitle } from "../router";
import "./pages.css";

const megabytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export function ImportPage() {
  useTitle("Import a Tier-1 bundle");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ ids: string[]; video: string } | null>(null);

  function choose(next: File | undefined) {
    setError(null);
    if (!next) return;
    if (!next.name.toLowerCase().endsWith(".zip")) {
      setError("Choose the ZIP file the detector wrote. Other file types cannot be imported.");
      return;
    }
    if (next.size > MAX_BUNDLE_BYTES) {
      setError(`This file is ${megabytes(next.size)}. Bundles can be at most 256 MB. Run the detector on a shorter clip.`);
      return;
    }
    setFile(next);
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Choose a bundle first.");
      return;
    }
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
      <main className="page" id="main">
        <div className="page__done">
          <p className="eyebrow">Import finished</p>
          <h1>Imported {done.ids.length} {done.ids.length === 1 ? "event" : "events"} from {done.video}</h1>
          <p>Tier-2 verification is queued. Events verify one at a time on the GPU, and the status bar at the bottom shows progress. You can review each event as soon as it appears.</p>
          <div className="page__actions">
            <Link href={`/incident/${done.ids[0]}`} className="btn btn--primary">Open the first event</Link>
            <button type="button" className="btn" onClick={() => setDone(null)}>Import another bundle</button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="page" id="main">
      <div className="page__grid">
        <div className="page__main">
          <h1>Import a Tier-1 bundle</h1>
          <p className="page__lead">A bundle is the ZIP file the Tier-1 detector writes for one video: a manifest and the frames around each event it flagged. After import, the vision model checks every event.</p>
          <form className="page__form" onSubmit={submit} noValidate>
            <label
              className={`dropzone${dragging ? " dropzone--over" : ""}${error ? " dropzone--error" : ""}`}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={drop}
            >
              <input type="file" accept=".zip,application/zip" className="visually-hidden"
                aria-describedby={error ? "import-error" : "import-hint"} onChange={(event) => choose(event.target.files?.[0])} />
              <span className="dropzone__title">{file ? file.name : "Drop a bundle here, or choose a file"}</span>
              <span id="import-hint" className="dropzone__hint">{file ? megabytes(file.size) : "ZIP, up to 256 MB and 100 events"}</span>
            </label>
            {error && <p id="import-error" className="error-text" role="alert">{error}</p>}
            <div className="page__actions">
              <button className="btn btn--primary" disabled={busy}>{busy ? "Importing" : "Import and verify"}</button>
              {file && !busy && <button type="button" className="link-button" onClick={() => setFile(null)}>Choose another file</button>}
            </div>
            {busy && <div className="skeleton" aria-label="Checking hashes and saving frames"><i /><i /></div>}
          </form>
        </div>
        <aside className="page__aside">
          <h2 className="eyebrow">Make a bundle</h2>
          <p>Run the detector on a video from the project folder:</p>
          <pre className="page__code">python -m traffic_poc detect video.mp4 --camera-type CCTV</pre>
          <p>It writes <code>data/video_tier1.zip</code>. Use <code>--camera-type DASHCAM</code> for dashboard footage, and add <code>--allowed-direction 1</code> when normal traffic moves down the screen.</p>
          <h2 className="eyebrow">What the import checks</h2>
          <ul className="page__list">
            <li>The manifest matches the files in the ZIP.</li>
            <li>Every frame matches its SHA-256 hash.</li>
            <li>Importing the same bundle twice adds nothing new.</li>
          </ul>
          <p className="muted">A bundle holds at most 100 events. A busy clip can produce more, so split it into shorter clips first.</p>
        </aside>
      </div>
    </main>
  );
}
