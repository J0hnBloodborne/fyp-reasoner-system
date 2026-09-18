"""Project-local runtime configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data"
    model_cache: Path = ROOT / "models"
    model_id: str = "Qwen/Qwen3-VL-2B-Instruct"
    revision: str = "main"
    max_image_edge: int = 768
    max_new_tokens: int = 640
    max_upload_bytes: int = 12 * 1024 * 1024
    max_image_pixels: int = 24_000_000
    max_pending: int = 4

    @classmethod
    def from_env(cls) -> "Settings":
        """Read explicit overrides without loading secrets from files."""
        return cls(
            data_dir=Path(os.getenv("TRAFFIC_DATA_DIR", str(ROOT / "data"))),
            model_cache=Path(os.getenv("TRAFFIC_MODEL_CACHE", str(ROOT / "models"))),
            model_id=os.getenv("TRAFFIC_MODEL_ID", "Qwen/Qwen3-VL-2B-Instruct"),
            revision=os.getenv("TRAFFIC_MODEL_REVISION", "main"),
        )
