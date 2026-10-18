"""Incident reports combine detection, verification, evidence and reviews."""

import json

import pytest
from PIL import Image

from tests.conftest import StubReasoner, wait_verified
from traffic_poc.config import Settings
from traffic_poc.detection.bundle import import_bundle
from traffic_poc.detection.export_bundle import export_bundle
from traffic_poc.pipeline import Pipeline
from traffic_poc.records.report import build_report
from traffic_poc.records.schemas import Review
from traffic_poc.records.storage import Repository

VERIFICATION = {
    "observations": [{"frame_index": 3, "description": "Car faces oncoming traffic"}],
    "verdict": "supported",
    "summary": "The car travels against the flow",
    "limitations": ["Night footage"],
}


@pytest.fixture
def record_id(tmp_path):
    paths = []
    for index in range(5):
        path = tmp_path / f"frame_{index:04d}.jpg"
        Image.new("RGB", (32, 24), (index * 20, 0, 0)).save(path)
        paths.append(path)
    bundle = export_bundle(
        [
            {
                "frame": 3,
                "type": "Wrong-Way Driving",
                "target_id": "ID 8",
                "confidence": 21.5,
            }
        ],
        paths,
        "v41.mov",
        "CCTV",
        tmp_path / "tier1.zip",
        fps=10.0,
    )
    settings = Settings(data_dir=tmp_path / "data")
    pipeline = Pipeline(
        settings, StubReasoner(json.dumps(VERIFICATION)), Repository(settings.data_dir)
    )
    try:
        [record_id] = import_bundle(bundle, settings, pipeline.repository)
        pipeline.verify(record_id)
        wait_verified(pipeline, record_id)
    finally:
        pipeline.close()
    return record_id


def test_report_combines_all_stages(tmp_path, record_id):
    repository = Repository(tmp_path / "data")
    report = build_report(repository.get(record_id))
    assert report["incident"]["type"] == "Wrong-Way Driving"
    assert report["incident"]["trigger_time_seconds"] == 0.2
    assert report["tier1"]["heuristic_value"] == 21.5
    assert report["tier2"]["status"] == "completed"
    assert report["tier2"]["verdict"] == "supported"
    assert report["tier2"]["observations"][0]["frame_index"] == 3
    assert [item["frame_index"] for item in report["evidence"]] == [1, 2, 3, 4, 5]
    assert report["evidence"][2]["role"] == "trigger"
    assert report["evidence"][2]["url"] == f"/api/records/{record_id}/frames/3"
    assert report["current_decision"] is None
    assert report["notice_issued"] is False


def test_report_reflects_latest_review(tmp_path, record_id):
    repository = Repository(tmp_path / "data")
    repository.review(record_id, Review(decision="approved", reviewer="a"))
    repository.review(record_id, Review(decision="rejected", reviewer="b"))
    report = build_report(repository.get(record_id))
    assert [review["reviewer"] for review in report["reviews"]] == ["a", "b"]
    assert report["current_decision"] == "rejected"


def test_report_without_fps_or_verification(tmp_path, record_id):
    repository = Repository(tmp_path / "data")
    record = repository.get(record_id)
    record["tier1_event"]["fps"] = None
    record.pop("verification")
    report = build_report(record)
    assert report["incident"]["trigger_time_seconds"] is None
    assert report["tier2"]["status"] == "not_queued"
    assert report["tier2"]["verdict"] is None


def test_uploads_have_no_incident_report(pipeline, image_base64):
    from traffic_poc.records.schemas import Submission

    record = pipeline.wait(pipeline.submit(Submission(image_base64=image_base64)))
    with pytest.raises(ValueError, match="Tier-1"):
        build_report(record)
