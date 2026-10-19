# Traffic evidence proof of concept

Manually upload a traffic image for local PyTorch VLM analysis, or import a
Tier-1 detector event bundle for human review. The VLM currently checks only
**no helmet** and **triple riding** on still images. Imported detector events
are **not** passed through the VLM yet. No training, live camera feed, or
automatic notice issuance is included.

## Setup

Python 3.11 and an NVIDIA CUDA GPU are required. The default model is
`Qwen/Qwen3-VL-2B-Instruct`, using BF16 (FP16 fallback) and PyTorch SDPA.

From PowerShell in this directory:

Run `.\scripts\setup.ps1` for the full setup, or use the individual commands below.
Do not run another setup/install process against this venv while one is active.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m traffic_poc download-model
.\.venv\Scripts\python.exe -m traffic_poc serve --warmup
```

Open <http://127.0.0.1:8000>. The application binds to loopback only. The first model
download is several GB; subsequent runs reuse the project-local `models/` cache.
Without `--warmup`, the model loads when the first job runs. To prevent network
access from the model loader after downloading:

```powershell
$env:TRAFFIC_OFFLINE = "1"
.\.venv\Scripts\python.exe -m traffic_poc serve --warmup
```

If the Hugging Face Xet transfer stalls, use the documented HTTP fallback before
running the downloader:

```powershell
$env:HF_HUB_DISABLE_XET = "1"
.\.venv\Scripts\python.exe -m traffic_poc download-model
```

The downloader resumes partial artifacts through the Hugging Face cache.

After setup, `.\scripts\verify_and_run.ps1` checks an actual CUDA operation, runs
the application tests, optionally runs the real-model smoke check if
`data/samples/bus.jpg` is present, and starts the app with offline model loading.
It stops on a failed check. The development sample used here is Ultralytics'
[public bus image](https://github.com/ultralytics/assets/blob/main/im/bus.jpg), a
negative scene without motorcycle riders; it does not test helmet-detection accuracy.

Only one pipeline instance can hold the OS lock for a given data directory. `Ctrl+C` stops
the HTTP server and drains accepted jobs. After a crash, interrupted jobs are
marked failed on restart rather than silently reprocessed.

## Use

Open `http://127.0.0.1:8000` after `serve` to use TrafficSeek. The app has three screens.

**Search** is the home screen. Describe an event in plain words, for example
"car driving against traffic at night", and narrow the results with the
filters. Results show in two views:

- **Timeline**: one clip ruler per recording, with a block at each event. The
  block's tally colour gives the Tier-2 verdict: green for supported, red for
  not supported, an amber outline for insufficient evidence, and a grey outline
  for not verified yet.
- **Register**: a sortable table with the matching text from each record. It
  downloads as CSV.

Select an event to open it in the monitor. For videos uploaded to the app,
the monitor plays the footage, paused on the trigger, with burned-in timecode
and a clip ruler that marks the in and out points of the window Tier-2 saw.
Switch to "Frames Tier-2 saw" to step through the exact evidence frames. The
arrow keys step one frame, Home and End jump to the in and out points, and
Space plays or pauses. The inspector shows the
verdict and the frame-by-frame observations, the Tier-1 detector data, the raw
model output and the custody log. Record a named decision on the Review tab.
Each event has its own link, `/incident/<record id>`. Press `?` for all keys.

**Add footage** takes a video (MP4, MOV, AVI, MKV or WebM, up to 2 GB). The
GPU worker makes a 720p preview copy (when `ffmpeg` is on PATH), runs the
Tier-1 detector on every frame, imports the events in bundles of at most 100,
and queues each for Tier-2. One video is processed at a time; a 35-second,
60 fps clip takes about two minutes on an RTX 3070. The same screen still
imports Tier-1 bundles made elsewhere (see below). Uploaded videos stay in
`data/videos/`.

**Analyze an image** checks one JPEG, PNG or WebP still (at most 12 MiB /
24 MP) for riders without helmets and triple riding. Location and capture time
are supplied metadata, not facts inferred or verified by the model. A reviewer
can save a corrected analysis; it is validated and appended without replacing
the original output.

Downloads: the incident report for Tier-1 events (JSON, report version 1.1,
with a custody log and exhibit labels E1, E2, ... for the evidence frames), the
complete record with provenance and review history, and the original evidence.

The original upload bytes and their SHA-256 are retained. Review uses a full-size,
EXIF-oriented RGB image; inference uses a separate image capped at a 768 px long
edge. Downscaling can hide small plates or helmets. The model processor can perform
additional resizing; its actual vision grid is recorded in provenance.

All evidence and records stay under `data/` and are excluded from Git. No cloud
inference service is called. Model acquisition contacts Hugging Face. Review names
are self-reported, not authenticated identities; this is a single-operator local
prototype, not a production enforcement or audit system.

## Design

```text
manual upload → evidence ingestion → bounded job worker → Reasoner adapter
                                                           ↓
human review ← SQLite record ← schema validation ← raw output + provenance

Tier-1 ZIP bundle → verified event/evidence importer → unverified review record
```

The code is grouped by what it does. Every command runs through
`python -m traffic_poc <command>`:

```text
traffic_poc/
  cli.py        serve | detect | import | download-model | smoke
  config.py     runtime settings from environment variables
  contract.py   strict Pydantic base for every validated contract
  pipeline.py   job queue for image uploads and Tier-1 verification
  lease.py      one pipeline per data directory
  detection/    Tier-1: YOLO heuristics, video loop, bundle format
  vlm/          Tier-2: model adapter, prompts, output contracts
  records/      SQLite store, evidence files, reviews, search, reports
  web/          local HTTP server; static/ holds the built browser app
frontend/       browser app source (React, TypeScript, Vite)
scripts/        PowerShell setup and verify-and-run helpers
```

Dependencies point one way: `cli` and `web` call `pipeline`, which uses
`detection`, `vlm` and `records`, which use `config` and `contract`. Torch
tensors stay inside `vlm/model.py`. Invalid model output becomes an
inspectable failed record, and reviews append without replacing it.

## Tier-1 handoff

The attached Colab notebook currently prints `violations` and keeps trigger
images in memory; it does not export a durable event/evidence handoff. To create
one, upload `traffic_poc/detection/export_bundle.py` into the Colab working directory
and run this **after** its final detection cell (which defines `violations`,
`test_frames`, `video_path` and `CAMERA_TYPE`):

```python
from export_bundle import export_bundle
from google.colab import files

bundle = export_bundle(
    violations,
    test_frames,
    source_video=video_path,
    camera_type=CAMERA_TYPE,
    destination="tier1_events.zip",
)
files.download(str(bundle))
```

The exporter copies source frames, not annotated/resized notebook previews. By
default it includes two preceding and two following frames around each trigger;
pass `frame_offsets=(-15, -10, -5, -2, -1, 0, 1, 2, 5)` when longer motion
context is needed. The bundle contains a versioned `manifest.json` with source
video name, camera type, event type, trigger frame, track ID, frame hashes and
the notebook's original `confidence` value. That last value is stored as a
**raw heuristic measurement**, not a calibrated probability: the notebook uses
pixel displacement for wrong-way events and IoU for collision events.

Transfer the ZIP to the local machine and run:

```powershell
.\.venv\Scripts\python.exe -m traffic_poc import path\to\tier1_events.zip
```

The command prints stable record IDs and can be rerun on the same ZIP without
duplicating records. Open <http://127.0.0.1:8000> and select an imported record
to see the trigger, context frames and review controls. Import does not load
the GPU model. A wrong-way or collision trigger remains an **unverified Tier-1
candidate**; approval/rejection is a human review entry, not an automatic
finding or notice. The current notebook's final detection cell does not emit
no-helmet or triple-riding events, despite the earlier summary mentioning
triple riding. Multi-frame VLM verification needs a later reasoner and output
contract extension; a single frame cannot establish travel direction.

The record retains model/checkpoint revision, prompt version, package versions,
GPU, precision, generation settings, timing, peak torch allocation, raw response,
and evidence hash. Prompt/schema changes should increment the prompt/schema version.
The requested `main` revision can change; set `TRAFFIC_MODEL_REVISION` to the recorded
commit hash for a repeatable checkpoint.

The baseline uses a **dense**, instruction-tuned pretrained model, not a new MoE
architecture. Future detector triggers can call the same pipeline after extending
the evidence input contract to carry frame sequences and detector grounding. A
different reasoner can implement the same protocol without changing review/storage.

## Frontend

The browser app is React and TypeScript in `frontend/`, built with Vite into
`traffic_poc/web/static/`. The build is committed, so `serve` needs no Node
toolchain. After a change under `frontend/src`, rebuild and commit the output:

```powershell
cd frontend
npm ci
npm run build    # typecheck, then write traffic_poc/web/static
```

For live reload, start the Python server on port 8000, then run `npm run dev`
in `frontend/`. Vite forwards `/api` to the Python server.

```text
frontend/src/
  api.ts         typed calls; shapes mirror records/store.py, search.py, report.py
  format.ts      timecode, labels, verdict marks
  router.tsx     history routing for /, /incident/<id>, /import, /analyze, /privacy
  components/    header, status bar, verdict sign, shortcut list
  workspace/     search screen: search bar, monitor, inspector, timeline, register
  pages/         import, analyze, privacy and terms, not found
  styles/        colour tokens (light default, dark) and shared controls
```

The server sends the app shell for each app route and for unknown paths, with
a 404 status for the latter, so the app shows its own not-found page. It
serves built files only by flat file name and known extension.

## Fine-tuning and custom kernels

Unsloth is reserved for the training environment, not imported by the application.
Its official [Qwen3-VL guide](https://unsloth.ai/docs/models/tutorials/qwen3-how-to-run-and-fine-tune/qwen3-vl-how-to-run-and-fine-tune)
and [Windows installation guide](https://unsloth.ai/docs/get-started/install/windows-installation)
are the starting points. Verify the selected Unsloth / torch / Transformers / Triton
combination in a separate training venv before installing it into this inference
environment. Training is not implemented or benchmarked here.

Curate human-corrected image/response examples and keep a scene-split holdout. Review
approval alone does not establish a complete or correct training label. Later,
export a merged checkpoint and point `TRAFFIC_MODEL_ID` at its local directory.
The inference adapter also needs extension if loading unmerged PEFT adapters.
8 GB inference success does not guarantee fine-tuning fits; test a small QLoRA run
with constrained resolution and batch size before choosing a training budget.

PyTorch supports [custom C++/CUDA operators](https://docs.pytorch.org/tutorials/advanced/cpp_custom_ops.html),
so later routing/kernel work can coexist with the training framework. Kernel
optimization and model architecture changes are separate from this application.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
cd frontend; npm ci; npm run build; cd ..
.\.venv\Scripts\python.exe -m traffic_poc smoke path\to\image.jpg --runs 2
```

Unit/integration tests use stub inference and never download a model. The separate
smoke script uses the real GPU model and persists records tagged by the
`smoke_test` reviewer; these are technical checks, not confirmed traffic findings.
Real accuracy requires labeled local traffic images, including difficult negatives
and uncertain scenes. The prototype neither constrains decoding to a JSON grammar
nor silently repairs malformed output; invalid records fail visibly.

Model confidence is subjective and uncalibrated. Single frames cannot establish
wrong-way driving or red-light crossing history. Plates may be null. There is no
face recognition, identity lookup, legal-rule inference, or automatic fine.

## Configuration

| Variable | Default |
| --- | --- |
| `TRAFFIC_MODEL_ID` | `Qwen/Qwen3-VL-2B-Instruct` or a local checkpoint directory |
| `TRAFFIC_MODEL_REVISION` | `main` |
| `TRAFFIC_MODEL_CACHE` | project `models/` |
| `TRAFFIC_DATA_DIR` | project `data/` |
| `TRAFFIC_MAX_IMAGE_EDGE` | `768` |
| `TRAFFIC_MAX_NEW_TOKENS` | `640` |
| `TRAFFIC_OFFLINE` | `0`; use `1` to disable model-loader downloads |

Use `--port 8001` to change the HTTP port.
