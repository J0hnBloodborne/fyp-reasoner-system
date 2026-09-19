"""Validate resource limits before creating the GPU runtime."""

import pytest

from traffic_poc.config import Settings


def test_explicit_environment_overrides(monkeypatch):
    monkeypatch.setenv("TRAFFIC_OFFLINE", "1")
    monkeypatch.setenv("TRAFFIC_MAX_IMAGE_EDGE", "512")
    monkeypatch.setenv("TRAFFIC_MODEL_ID", "local-model")
    settings = Settings.from_env()
    assert settings.offline is True
    assert settings.max_image_edge == 512
    assert settings.model_id == "local-model"


@pytest.mark.parametrize(
    "options",
    [
        {"max_image_edge": 0},
        {"max_image_edge": 4096},
        {"max_new_tokens": 1},
        {"max_new_tokens": 4096},
        {"max_pending": 0},
    ],
)
def test_invalid_limits(options):
    with pytest.raises(ValueError):
        Settings(**options)
