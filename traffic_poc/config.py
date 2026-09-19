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
    offline: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        """Read explicit overrides without loading secrets from files."""
        return cls(
            data_dir=Path(os.getenv("TRAFFIC_DATA_DIR", str(ROOT / "data"))),
            model_cache=Path(os.getenv("TRAFFIC_MODEL_CACHE", str(ROOT / "models"))),
            model_id=os.getenv("TRAFFIC_MODEL_ID", "Qwen/Qwen3-VL-2B-Instruct"),
            revision=os.getenv("TRAFFIC_MODEL_REVISION", "main"),
            max_image_edge=int(os.getenv("TRAFFIC_MAX_IMAGE_EDGE", "768")),
            max_new_tokens=int(os.getenv("TRAFFIC_MAX_NEW_TOKENS", "640")),
            offline=os.getenv("TRAFFIC_OFFLINE", "0") == "1",
        )

    def __post_init__(self) -> None:
        if not 64 <= self.max_image_edge <= 1536:
            raise ValueError("TRAFFIC_MAX_IMAGE_EDGE must be between 64 and 1536")
        if not 64 <= self.max_new_tokens <= 2048:
            raise ValueError("TRAFFIC_MAX_NEW_TOKENS must be between 64 and 2048")
        if self.max_pending < 1:
            raise ValueError("max_pending must be positive")
