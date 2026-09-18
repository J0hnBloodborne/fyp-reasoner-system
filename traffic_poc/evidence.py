"""Validate uploads and retain original evidence separately from model inputs."""

import base64
import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from traffic_poc.config import Settings


@dataclass(frozen=True)
class Evidence:
    original_path: Path
    image_path: Path
    sha256: str
    width: int
    height: int
    model_width: int
    model_height: int

    def metadata(self) -> dict:
        """Expose evidence provenance without absolute filesystem paths."""
        return {
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "model_width": self.model_width,
            "model_height": self.model_height,
            "original_file": self.original_path.name,
            "model_image_file": self.image_path.name,
        }


def ingest_image(encoded: str, record_id: str, settings: Settings) -> Evidence:
    """Decode one still image, preserve its bytes, and create an EXIF-oriented RGB PNG."""
    if len(encoded) > ((settings.max_upload_bytes + 2) // 3) * 4:
        raise ValueError("Image exceeds the 12 MiB upload limit")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Invalid base64 image") from exc
    if not data or len(data) > settings.max_upload_bytes:
        raise ValueError("Image is empty or exceeds the upload limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Only JPEG, PNG and WebP are supported")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("Upload a single still image, not an animation")
                if source.width * source.height > settings.max_image_pixels:
                    raise ValueError("Image exceeds the 24 megapixel limit")
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("Image is invalid or too large to decode safely") from exc
    width, height = image.size
    image.thumbnail((settings.max_image_edge, settings.max_image_edge))
    directory = settings.data_dir / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    original_path = directory / f"{record_id}.original"
    image_path = directory / f"{record_id}.png"
    original_path.write_bytes(data)
    image.save(image_path, format="PNG")
    return Evidence(
        original_path, image_path, hashlib.sha256(data).hexdigest(),
        width, height, image.width, image.height,
    )
