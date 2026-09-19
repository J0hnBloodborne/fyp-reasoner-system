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
.\.venv\Scripts\python.exe -m scripts.tier2.download_model
.\.venv\Scripts\python.exe -m traffic_poc --warmup
```

Open <http://127.0.0.1:8000>. The application binds to loopback only. The first model
download is several GB; subsequent runs reuse the project-local `models/` cache.
Without `--warmup`, the model loads when the first job runs. To prevent network
access from the model loader after downloading:

```powershell
$env:TRAFFIC_OFFLINE = "1"
.\.venv\Scripts\python.exe -m traffic_poc --warmup
```

If the Hugging Face Xet transfer stalls, use the documented HTTP fallback before
running the downloader:

```powershell
$env:HF_HUB_DISABLE_XET = "1"
.\.venv\Scripts\python.exe -m scripts.tier2.download_model
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

1. Upload one JPEG, PNG, or WebP still image (at most 12 MiB / 24 MP).
2. Optionally attach a location and capture timestamp. These are supplied metadata,
   not facts inferred or verified by the model.
3. Wait for a candidate, no-visible-violation, or uncertain record.
4. Enter a reviewer name and confirm or reject. Optionally edit the analysis JSON;
   corrections are validated and appended without replacing the original output.
5. Export the complete record, including provenance and review history.

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

The code is grouped by feature, with records shared by both stages:

```text
traffic_poc/
  records/  contracts, evidence validation, SQLite review history
  tier1/    versioned detector bundle contract and importer
  tier2/    VLM adapter, prompt, bounded inference pipeline
  web/      local HTTP transport and plain HTML interface
  config.py shared runtime settings
scripts/
  tier1/    Colab export, local import, notebook-preview adapter
  tier2/    model download and GPU smoke check
```

The web layer calls the workflows; both stages use `records/` for evidence and
persistence. Torch tensors stay inside `tier2/inference.py`. Invalid model output
becomes an inspectable failed record, and reviews append without replacing it.

## Tier-1 handoff

The attached Colab notebook currently prints `violations` and keeps trigger
images in memory; it does not export a durable event/evidence handoff. To create
one, upload `scripts/tier1/export_bundle.py` into the Colab working directory
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
.\.venv\Scripts\python.exe -m scripts.tier1.import_bundle path\to\tier1_events.zip
```

For the **already-executed attached notebook**, the source video and extracted
frames were not attached, but the notebook contains two displayed trigger
previews. To demo the handoff without rerunning Colab:

```powershell
.\.venv\Scripts\python.exe -m scripts.tier1.notebook_preview F:\Downloads\Untitled18.ipynb data\tier1_notebook_preview.zip --source-video v41.mov --camera-type CCTV
.\.venv\Scripts\python.exe -m scripts.tier1.import_bundle data\tier1_notebook_preview.zip
```

These are **540×320 annotated previews**, not original frames or a motion
sequence. Their records are marked `annotated_preview` and must not be used for
VLM verification or a final violation decision.

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
node --check traffic_poc/web/static/app.js
.\.venv\Scripts\python.exe -m scripts.tier2.smoke_model path\to\image.jpg --runs 2
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
