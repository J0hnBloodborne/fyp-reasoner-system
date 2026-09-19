"""Original evidence and downscaled model input have separate provenance."""

import base64
import hashlib
import io

import pytest
from PIL import Image

from traffic_poc.config import Settings
from traffic_poc.records.evidence import ingest_image


def test_preserves_original_and_bounds_model_image(tmp_path, image_base64):
    evidence = ingest_image(image_base64, "test", Settings(data_dir=tmp_path))
    assert evidence.original_path.read_bytes() == base64.b64decode(image_base64)
    assert (
        evidence.sha256
        == hashlib.sha256(evidence.original_path.read_bytes()).hexdigest()
    )
    with Image.open(evidence.image_path) as image:
        assert image.size == (768, 512)
    with Image.open(evidence.review_path) as image:
        assert image.size == (1200, 800)


@pytest.mark.parametrize("encoded", ["", "!!", base64.b64encode(b"text").decode()])
def test_invalid_image(tmp_path, encoded):
    with pytest.raises(ValueError):
        ingest_image(encoded, "test", Settings(data_dir=tmp_path))
    assert not (tmp_path / "evidence").exists()


def test_limit_before_decode(tmp_path):
    with pytest.raises(ValueError):
        ingest_image("a" * 100, "test", Settings(data_dir=tmp_path, max_upload_bytes=8))


def test_pixel_limit(tmp_path, image_base64):
    with pytest.raises(ValueError):
        ingest_image(
            image_base64, "test", Settings(data_dir=tmp_path, max_image_pixels=100)
        )


def test_unsupported_image_format(tmp_path):
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buffer, format="BMP")
    with pytest.raises(ValueError):
        ingest_image(
            base64.b64encode(buffer.getvalue()).decode(),
            "test",
            Settings(data_dir=tmp_path),
        )


def test_exif_rotation_is_applied_to_review_and_model(tmp_path):
    source = Image.new("RGB", (1200, 800), "white")
    exif = source.getexif()
    exif[274] = 6
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", exif=exif)
    evidence = ingest_image(
        base64.b64encode(buffer.getvalue()).decode(),
        "test",
        Settings(data_dir=tmp_path),
    )
    assert (evidence.width, evidence.height) == (800, 1200)
    assert (evidence.model_width, evidence.model_height) == (512, 768)
    assert evidence.original_path.read_bytes() == buffer.getvalue()
