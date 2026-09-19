"use strict";

const $ = id => document.getElementById(id);
let currentId = null;
let polling = null;
let selection = 0;
const asJSON = value => JSON.stringify(value, null, 2);
const message = text => { $("message").textContent = text; };

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  };
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}

async function health() {
  try {
    const result = await api("/api/health");
    $("health").textContent = `${result.model_id} · ${result.model_state} · ${result.offline ? "offline" : "downloads allowed"}`;
  } catch (error) { $("health").textContent = error.message; }
}

async function recent() {
  const records = await api("/api/records");
  $("recent").replaceChildren();
  for (const record of records) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.textContent = `${record.id.slice(0, 8)} · ${record.status} · ${record.created_at}`;
    button.addEventListener("click", () => selectRecord(record.id).catch(error => message(error.message)));
    li.append(button);
    $("recent").append(li);
  }
}

function render(record) {
  $("record").hidden = false;
  $("status").textContent = `${record.filename} · ${record.status}${record.error ? " · " + record.error : ""}`;
  $("analysis").textContent = record.analysis ? asJSON(record.analysis) : "Waiting for a validated analysis…";
  const e = record.evidence;
  $("dimensions").textContent = `Original: ${e.width}×${e.height}; model input: ${e.model_width}×${e.model_height}.`;
  $("raw").textContent = record.raw_response || "No model response yet.";
  $("provenance").textContent = asJSON(record.provenance);
  $("reviews").textContent = record.reviews.length ? asJSON(record.reviews) : "Not reviewed.";
  $("review").hidden = record.status !== "completed";
  $("timing").textContent = record.provenance
    ? `Inference: ${record.provenance.inference_seconds}s · peak torch allocation: ${record.provenance.peak_allocated_mib} MiB`
    : "First analysis may include model loading or downloading.";
  if (record.status === "completed" && !$("correct").checked) $("correction").value = asJSON(record.analysis);
}

async function selectRecord(id) {
  clearTimeout(polling);
  const token = ++selection;
  currentId = id;
  $("correct").checked = false;
  $("correction").hidden = true;
  $("notes").value = "";
  $("evidence").src = `/api/records/${id}/image`;
  $("export").href = `/api/records/${id}/export`;
  $("original").href = `/api/records/${id}/original`;
  async function poll() {
    const record = await api(`/api/records/${id}`);
    if (token !== selection) return;
    render(record);
    await health();
    if (["queued", "running"].includes(record.status)) {
      polling = setTimeout(() => poll().catch(error => message(error.message)), 1200);
    } else { await recent(); }
  }
  await poll();
}

$("upload").addEventListener("submit", async event => {
  event.preventDefault();
  const file = $("image").files[0];
  if (!file) return;
  if (file.size > 12 * 1024 * 1024) { message("Image must be under 12 MiB."); return; }
  $("analyze").disabled = true;
  message("Uploading…");
  try {
    const image_base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    const result = await api("/api/records", {
      image_base64, filename: file.name,
      location: $("location").value || null, captured_at: $("captured").value || null
    });
    message("Job accepted. Analysis runs locally; no notice is issued.");
    await selectRecord(result.id);
    await recent();
  } catch (error) { message(error.message); }
  finally { $("analyze").disabled = false; }
});

$("correct").addEventListener("change", () => { $("correction").hidden = !$("correct").checked; });
$("review").addEventListener("submit", async event => {
  event.preventDefault();
  const id = currentId;
  const token = selection;
  const buttons = $("review").querySelectorAll("button");
  buttons.forEach(button => { button.disabled = true; });
  try {
    const record = await api(`/api/records/${id}/review`, {
      decision: event.submitter.value, reviewer: $("reviewer").value,
      notes: $("notes").value,
      corrected_analysis: $("correct").checked ? JSON.parse($("correction").value) : null
    });
    if (token === selection) { render(record); message("Review saved. Original model output is unchanged."); }
  } catch (error) { message(error.message); }
  finally { buttons.forEach(button => { button.disabled = false; }); }
});
$("refresh").addEventListener("click", () => recent().catch(error => message(error.message)));
health();
recent().catch(error => message(error.message));
