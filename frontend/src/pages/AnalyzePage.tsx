import { useState, type FormEvent } from "react";
import { api, MAX_IMAGE_BYTES } from "../api";
import { navigate, useTitle } from "../router";
import "./pages.css";

const TYPES = ["image/jpeg", "image/png", "image/webp"];

function readBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("The browser could not read this file. Choose it again."));
    reader.readAsDataURL(file);
  });
}

export function AnalyzePage() {
  useTitle("Analyze an image");
  const [file, setFile] = useState<File | null>(null);
  const [location, setLocation] = useState("");
  const [captured, setCaptured] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ field: "file" | "form"; text: string } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return setError({ field: "file", text: "Choose an image to analyze." });
    if (!TYPES.includes(file.type)) return setError({ field: "file", text: "Choose a JPEG, PNG or WebP image." });
    if (file.size > MAX_IMAGE_BYTES) return setError({ field: "file", text: "This image is larger than 12 MB. Export a smaller copy and try again." });
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.submitImage({
        image_base64: await readBase64(file), filename: file.name,
        location: location.trim() || null, captured_at: captured.trim() || null,
      });
      navigate(`/incident/${id}`);
    } catch (exc) {
      setError({ field: "form", text: (exc as Error).message });
      setBusy(false);
    }
  }

  return (
    <main className="page" id="main">
      <div className="page__grid">
        <div className="page__main">
          <h1>Analyze an image</h1>
          <p className="page__lead">Checks one still for riders without helmets and for triple riding. The result opens on the Search screen, where you can review it.</p>
          <form className="page__form" onSubmit={submit} noValidate>
            <div className={`field${error?.field === "file" ? " field--error" : ""}`}>
              <label htmlFor="image">Image</label>
              <input id="image" type="file" accept={TYPES.join(",")} aria-describedby="image-hint"
                onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(null); }} />
              <span id="image-hint" className="hint">JPEG, PNG or WebP, up to 12 MB.</span>
              {error?.field === "file" && <span className="error-text" role="alert">{error.text}</span>}
            </div>
            <div className="field">
              <label htmlFor="location">Location <span className="hint">(optional)</span></label>
              <input id="location" value={location} maxLength={200} placeholder="Mall Road, Lahore" onChange={(event) => setLocation(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="captured">Capture time <span className="hint">(optional, include the time zone)</span></label>
              <input id="captured" value={captured} maxLength={100} placeholder="2026-09-19T10:00:00+05:00" onChange={(event) => setCaptured(event.target.value)} />
            </div>
            {error?.field === "form" && <p className="error-text" role="alert">{error.text}</p>}
            <div className="page__actions">
              <button className="btn btn--primary" disabled={busy}>{busy ? "Uploading" : "Analyze image"}</button>
            </div>
          </form>
        </div>
        <aside className="page__aside">
          <h2 className="eyebrow">What a still can show</h2>
          <p>One frame cannot show direction of travel or signal timing. For wrong-way, red-light and collision events, run the Tier-1 detector on the video and import its bundle.</p>
          <h2 className="eyebrow">Where it runs</h2>
          <p>The model runs on this computer. The first analysis after starting the server also loads the model, which takes longer.</p>
        </aside>
      </div>
    </main>
  );
}
