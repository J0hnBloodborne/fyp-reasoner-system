"""Tier-2 verification of imported Tier-1 events with stub inference."""

import json

import pytest
from PIL import Image

from tests.conftest import StubReasoner, wait_verified
from traffic_poc.config import Settings
from traffic_poc.detection.bundle import import_bundle
from traffic_poc.detection.export_bundle import export_bundle
from traffic_poc.records.schemas import Submission
from traffic_poc.records.storage import Repository
from traffic_poc.tier2.pipeline import Pipeline

SUPPORTED = {
    "observations": [{"frame_index": 3, "description": "Car faces oncoming traffic"}],
    "verdict": "supported",
    "summary": "The car travels against the flow",
    "limitations": [],
}


@pytest.fixture
def bundle(tmp_path):
    paths = []
    for index in range(5):
        path = tmp_path / f"frame_{index:04d}.jpg"
        Image.new("RGB", (32, 24), (index * 20, 0, 0)).save(path)
        paths.append(path)
    rows = [{"frame": 3, "type": "Wrong-Way Driving", "target_id": "ID 8"}]
    return export_bundle(rows, paths, "v41.mov", "CCTV", tmp_path / "tier1.zip")


def start(tmp_path, raw=SUPPORTED, **options):
    settings = Settings(data_dir=tmp_path / "data")
    raw = raw if isinstance(raw, str) else json.dumps(raw)
    return Pipeline(
        settings, StubReasoner(raw, **options), Repository(settings.data_dir)
    )


def test_verification_cites_ordered_frames(tmp_path, bundle):
    pipeline = start(tmp_path)
    try:
        [record_id] = import_bundle(bundle, pipeline.settings, pipeline.repository)
        pipeline.verify(record_id)
        verification = wait_verified(pipeline, record_id)
        assert verification["status"] == "completed"
        assert verification["result"]["verdict"] == "supported"
        assert verification["prompt_version"] == "tier1-verification-v2"
        assert pipeline.reasoner.verified == [("Wrong-Way Driving", [1, 2, 3, 4, 5])]
        record = pipeline.repository.get(record_id)
        assert record["status"] == "awaiting_review"
        assert record["analysis"] is None
    finally:
        pipeline.close()


def test_citation_of_unseen_frame_fails_but_keeps_raw(tmp_path, bundle):
    raw = {**SUPPORTED, "observations": [{"frame_index": 9, "description": "x"}]}
    pipeline = start(tmp_path, raw)
    try:
        [record_id] = import_bundle(bundle, pipeline.settings, pipeline.repository)
        pipeline.verify(record_id)
        verification = wait_verified(pipeline, record_id)
        assert verification["status"] == "failed"
        assert "not shown" in verification["error"]
        assert json.loads(verification["raw_response"]) == raw
    finally:
        pipeline.close()


def test_changed_evidence_is_not_sent_to_model(tmp_path, bundle):
    pipeline = start(tmp_path)
    try:
        [record_id] = import_bundle(bundle, pipeline.settings, pipeline.repository)
        frame = pipeline.repository.get(record_id)["tier1_event"]["frames"][0]
        (pipeline.settings.data_dir / "evidence" / frame["file"]).write_bytes(b"x")
        pipeline.verify(record_id)
        verification = wait_verified(pipeline, record_id)
        assert verification["status"] == "failed"
        assert "Evidence frame changed" in verification["error"]
        assert pipeline.reasoner.verified == []
    finally:
        pipeline.close()


def test_annotated_preview_is_skipped(tmp_path, bundle):
    pipeline = start(tmp_path)
    try:
        [record_id] = import_bundle(bundle, pipeline.settings, pipeline.repository)
        record = pipeline.repository.get(record_id)
        event = {**record["tier1_event"], "evidence_origin": "annotated_preview"}
        pipeline.repository.update(record_id, tier1_event=event)
        pipeline.verify(record_id)
        assert wait_verified(pipeline, record_id)["status"] == "skipped"
        assert pipeline.reasoner.verified == []
    finally:
        pipeline.close()


def test_startup_resumes_unverified_events(tmp_path, bundle):
    settings = Settings(data_dir=tmp_path / "data")
    [record_id] = import_bundle(bundle, settings, Repository(settings.data_dir))
    pipeline = start(tmp_path)
    try:
        assert wait_verified(pipeline, record_id)["status"] == "completed"
    finally:
        pipeline.close()
    pipeline = start(tmp_path)
    try:
        assert pipeline.reasoner.verified == []
    finally:
        pipeline.close()


def test_uploads_cannot_be_verified(tmp_path, image_base64):
    pipeline = start(tmp_path)
    try:
        record_id = pipeline.submit(Submission(image_base64=image_base64))
        with pytest.raises(ValueError, match="Tier-1"):
            pipeline.verify(record_id)
    finally:
        pipeline.close()
