"""GPU-independent integration tests for job and review lifecycle."""

import json
import threading

import pytest

from tests.conftest import StubReasoner
from traffic_poc.config import Settings
from traffic_poc.records.schemas import Review, Submission
from traffic_poc.records.storage import Repository, now
from traffic_poc.tier2.inference import ModelResponse
from traffic_poc.tier2.pipeline import Pipeline, PipelineBusy


def test_inference_and_append_only_review(pipeline, image_base64, candidate):
    record_id = pipeline.submit(Submission(image_base64=image_base64))
    record = pipeline.wait(record_id)
    assert record["status"] == "completed"
    assert record["notice_issued"] is False
    assert record["confidence_calibrated"] is False
    corrected = {
        "outcome": "uncertain",
        "findings": [],
        "summary": "Head is occluded",
        "limitations": ["Occlusion"],
    }
    pipeline.repository.review(
        record_id,
        Review(decision="rejected", reviewer="tester", corrected_analysis=corrected),
    )
    pipeline.repository.review(
        record_id, Review(decision="rejected", reviewer="tester")
    )
    saved = pipeline.repository.get(record_id)
    assert saved["analysis"] == candidate
    assert saved["raw_response"] == json.dumps(candidate)
    assert len(saved["reviews"]) == 2
    assert saved["reviews"][0]["corrected_analysis"] == corrected


@pytest.mark.parametrize(
    "raw,error", [("invalid JSON", None), (None, RuntimeError("OOM"))]
)
def test_failures_are_terminal_and_inspectable(tmp_path, image_base64, raw, error):
    settings = Settings(data_dir=tmp_path)
    pipeline = Pipeline(settings, StubReasoner(raw, error), Repository(tmp_path))
    try:
        record_id = pipeline.submit(Submission(image_base64=image_base64))
        record = pipeline.wait(record_id)
        assert record["status"] == "failed"
        assert record["raw_response"] == raw
        assert record["analysis"] is None
        with pytest.raises(ValueError):
            pipeline.repository.review(
                record_id, Review(decision="approved", reviewer="tester")
            )
    finally:
        pipeline.close()


def test_generation_limit_is_not_a_valid_result(tmp_path, candidate, image_base64):
    settings = Settings(data_dir=tmp_path)
    pipeline = Pipeline(
        settings,
        StubReasoner(
            json.dumps(candidate), provenance={"generation_limit_reached": True}
        ),
        Repository(tmp_path),
    )
    try:
        record = pipeline.wait(pipeline.submit(Submission(image_base64=image_base64)))
        assert record["status"] == "failed"
        assert "generation limit" in record["error"]
    finally:
        pipeline.close()


def test_bounded_queue_releases_capacity(tmp_path, image_base64, candidate):
    started, release = threading.Event(), threading.Event()

    class BlockingReasoner:
        def analyze(self, evidence):
            started.set()
            assert release.wait(10)
            return ModelResponse(json.dumps(candidate), {})

    settings = Settings(data_dir=tmp_path, max_pending=1)
    pipeline = Pipeline(settings, BlockingReasoner(), Repository(tmp_path))
    try:
        first = pipeline.submit(Submission(image_base64=image_base64))
        assert started.wait(5)
        with pytest.raises(PipelineBusy):
            pipeline.submit(Submission(image_base64=image_base64))
        release.set()
        assert pipeline.wait(first)["status"] == "completed"
        pipeline.close()
        assert pipeline.capacity.acquire(blocking=False)
        pipeline.capacity.release()
    finally:
        release.set()
        pipeline.close()


def test_invalid_upload_releases_capacity(pipeline, image_base64):
    for _ in range(pipeline.settings.max_pending + 1):
        with pytest.raises(ValueError):
            pipeline.submit(Submission(image_base64="bad"))
    assert (
        pipeline.wait(pipeline.submit(Submission(image_base64=image_base64)))["status"]
        == "completed"
    )


def test_interrupted_jobs_recovered(tmp_path):
    repository = Repository(tmp_path)
    repository.create({"id": "test", "created_at": now(), "status": "running"})
    repository.recover_interrupted()
    assert repository.get("test")["status"] == "failed"


def test_closed_pipeline_rejects_new_jobs(pipeline, image_base64):
    pipeline.close()
    with pytest.raises(PipelineBusy):
        pipeline.submit(Submission(image_base64=image_base64))
    assert pipeline.repository.list_recent() == []


def test_second_pipeline_cannot_recover_live_jobs(pipeline, image_base64):
    with pytest.raises(RuntimeError, match="Another pipeline"):
        Pipeline(pipeline.settings, pipeline.reasoner, pipeline.repository)
    assert (
        pipeline.wait(pipeline.submit(Submission(image_base64=image_base64)))["status"]
        == "completed"
    )
