# Status

## Workspace decisions

- Deep-learning framework: pytorch. Explicitly selected by the user on 2026-09-18.
- Environment: pip + project-local venv. Explicitly requested by the user.
- Tabular dataframe: deferred; no dataframe operations in the current application.
- Model serving / registry: deferred; no trained-model registry or joblib serving.
- UI: plain HTML, CSS, JavaScript; localhost only.
- Initial model: Qwen/Qwen3-VL-2B-Instruct, BF16 with SDPA, no fine-tuning yet.

## Progress

- Local Git repository initialized on main.
- Project-local .venv created with Python 3.11; pip upgraded.
- Initial config, schemas, evidence ingestion, torch model adapter, SQLite repository,
  and bounded asynchronous pipeline drafted. Not yet tested or runnable end-to-end.
- UI, web transport, tests, and run documentation remain to be implemented.
- Unsloth requested as an additional consideration; evaluate for later fine-tuning
  separately from the inference runtime.

## Paused: downloads

The user requested stopping all package/model downloads until their connection is
better. Both pip installation processes were interrupted. No model was downloaded.
Do not restart installs, fetch model weights, or invoke the lazy model loader until
the user explicitly resumes. Dependency installation is incomplete; only pip and
setuptools are present in the virtual environment at this checkpoint.

Resume steps:

1. Install CUDA torch + torchvision from the cu128 index, then requirements-dev.txt.
   Run these sequentially so accelerate cannot pull a different torch build.
2. Verify CUDA, the RTX 3070, and model class availability.
3. Finish the UI, web transport, tests, and documentation.
4. Download and run the small VLM; record actual VRAM and latency.
5. Lint and test, then create a short initial commit using existing user identity.
