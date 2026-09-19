# Status

## Workspace decisions

- Deep-learning framework: pytorch. Explicitly selected on 2026-09-18.
- Environment: pip + project-local venv. Explicitly requested.
- CUDA wheels: cu130. Explicitly selected on 2026-09-19.
- Tabular dataframe: deferred; no dataframe operations in this application.
- Model serving / registry: deferred; no trained-model registry or joblib serving.
- UI: plain HTML, CSS, JavaScript on localhost.
- Initial model: Qwen/Qwen3-VL-2B-Instruct, BF16 with SDPA, no fine-tuning yet.
- Unsloth: consider for a separate future fine-tuning environment.

## Baseline verification

- Python 3.11 venv installed with torch 2.14.0+cu130, Transformers 5.17.0,
  pytest 9.1.1, and Ruff 0.16.8.
- CUDA detected an RTX 3070. Model snapshot revision:
  `89644892e4d85e24eaac8bacfd4f463576704203`.
- Two real-model runs on a public bus image completed on 2026-09-19.
  Inference was 3.471 s and 2.711 s, with peak allocated VRAM of
  4265.6 MiB and 4266.8 MiB. Both records passed schema validation.
- Both bus runs returned `uncertain` despite no motorcycle in the image.
  The prompt has since been clarified in v2; this change still needs a
  real-model check after restarting the application.
- The bus image is only a negative technical smoke sample. No traffic
  violation accuracy claim is supported without labeled local images.
- 46 tests passed after the v2 prompt change; Ruff lint/format and JavaScript
  syntax checks passed.

## Next work

- Re-run real-model check on the v2 prompt and inspect the record.
- Collect consent-appropriate local traffic images, labeled negatives,
  uncertain cases, and a scene-split holdout before making accuracy claims.
- Evaluate Unsloth/QLoRA separately for fine-tuning on 8 GB VRAM.
