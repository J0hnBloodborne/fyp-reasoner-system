"""Small image and model fixtures; tests never download weights."""

import base64
import io
import json

import pytest
from PIL import Image

from traffic_poc.config import Settings
from traffic_poc.records.storage import Repository
from traffic_poc.tier2.inference import ModelResponse
from traffic_poc.tier2.pipeline import Pipeline


@pytest.fixture
def image_base64():
    image = Image.new("RGB", (1200, 800), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture
def candidate():
    return {
        "outcome": "candidate_violation",
        "findings": [
            {
                "violation_type": "no_helmet",
                "subject": "Rider at left",
                "evidence": "The visible head has no helmet",
                "plate": None,
                "confidence": 0.8,
            }
        ],
        "summary": "One candidate requires review",
        "limitations": ["Single still image"],
    }


class StubReasoner:
    def __init__(self, raw, error=None, provenance=None):
        self.raw = raw
        self.error = error
        self.provenance = provenance or {}

    def analyze(self, evidence):
        assert evidence.image_path.exists()
        if self.error:
            raise self.error
        return ModelResponse(self.raw, self.provenance)


@pytest.fixture
def pipeline(tmp_path, candidate):
    settings = Settings(data_dir=tmp_path / "data")
    result = Pipeline(
        settings, StubReasoner(json.dumps(candidate)), Repository(settings.data_dir)
    )
    yield result
    result.close()
