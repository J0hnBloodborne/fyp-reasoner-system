"""Replaceable model boundary; application logic does not depend on torch tensors."""

import gc
import time
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from PIL import Image

from traffic_poc.config import Settings
from traffic_poc.evidence import Evidence
from traffic_poc.prompts import SYSTEM_PROMPT, user_prompt


@dataclass(frozen=True)
class ModelResponse:
    raw: str
    provenance: dict


class Reasoner(Protocol):
    def analyze(self, evidence: Evidence) -> ModelResponse:
        """Analyze validated evidence and return raw output with runtime provenance."""
        ...


class TorchVLM:
    """Lazy, single-GPU VLM inference using native torch SDPA."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.processor = None
        self.lock = Lock()
        self.load_seconds = None
        self.resolved_revision = None

    def _load(self) -> None:
        """Fail explicitly without CUDA rather than silently running a CPU demo."""
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        if self.model is not None:
            return
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable. Install the CUDA torch wheel first.")
        started = time.perf_counter()
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        options = {
            "cache_dir": str(self.settings.model_cache),
            "revision": self.settings.revision,
            "trust_remote_code": False,
        }
        processor = AutoProcessor.from_pretrained(self.settings.model_id, **options)
        model = AutoModelForImageTextToText.from_pretrained(
            self.settings.model_id,
            dtype=dtype,
            device_map="cuda:0",
            attn_implementation="sdpa",
            **options,
        ).eval()
        self.processor, self.model = processor, model
        self.resolved_revision = getattr(model.config, "_commit_hash", None)
        self.load_seconds = round(time.perf_counter() - started, 3)

    def warmup(self) -> None:
        """Download and load the checkpoint before accepting the first real job."""
        with self.lock:
            self._load()

    def analyze(self, evidence: Evidence) -> ModelResponse:
        """Bound visual input and generation; serialize access to the GPU model."""
        import torch
        import transformers

        with self.lock:
            self._load()
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "image", "image": Image.open(evidence.image_path).copy()},
                    {"type": "text", "text": user_prompt()},
                ]},
            ]
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            try:
                with torch.inference_mode():
                    inputs = self.processor.apply_chat_template(
                        messages, tokenize=True, add_generation_prompt=True,
                        return_dict=True, return_tensors="pt",
                    ).to(self.model.device)
                    inputs.pop("token_type_ids", None)
                    input_tokens = inputs.input_ids.shape[1]
                    output = self.model.generate(
                        **inputs, max_new_tokens=self.settings.max_new_tokens,
                        do_sample=False, use_cache=True,
                    )
                    generated = output[:, input_tokens:]
                    raw = self.processor.batch_decode(
                        generated, skip_special_tokens=True,
                        clean_up_tokenization_spaces=False,
                    )[0]
                    output_tokens = generated.shape[1]
                    torch.cuda.synchronize()
                    provenance = {
                        "model_id": self.settings.model_id,
                        "requested_revision": self.settings.revision,
                        "resolved_revision": self.resolved_revision,
                        "torch_version": torch.__version__,
                        "transformers_version": transformers.__version__,
                        "device": torch.cuda.get_device_name(0),
                        "dtype": str(self.model.dtype),
                        "attention": "sdpa",
                        "load_seconds": self.load_seconds,
                        "inference_seconds": round(time.perf_counter() - started, 3),
                        "peak_allocated_mib": round(
                            torch.cuda.max_memory_allocated() / 1024**2, 1),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "generation_limit_reached": (
                            output_tokens >= self.settings.max_new_tokens),
                        "max_new_tokens": self.settings.max_new_tokens,
                        "do_sample": False,
                    }
                return ModelResponse(raw, provenance)
            except torch.cuda.OutOfMemoryError as exc:
                gc.collect()
                torch.cuda.empty_cache()
                raise RuntimeError(
                    "GPU out of memory. Close other GPU applications or reduce "
                    "max_image_edge/max_new_tokens in Settings."
                ) from exc
