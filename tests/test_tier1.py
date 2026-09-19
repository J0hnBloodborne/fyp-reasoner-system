"""Tier-1 export/import contract tests; no detector or VLM is loaded."""

import base64
import io
import json
import zipfile

import pytest
from PIL import Image

from scripts.tier1.export_bundle import export_bundle
from scripts.tier1.notebook_preview import export_preview_bundle
from traffic_poc.config import Settings
from traffic_poc.records.schemas import Review
from traffic_poc.records.storage import Repository
from traffic_poc.tier1.bundle import import_bundle


@pytest.fixture
def frame_paths(tmp_path):
    paths = []
    for index in range(5):
        path = tmp_path / f"frame_{index:04d}.jpg"
        Image.new("RGB", (32, 24), (index * 20, 0, 0)).save(path)
        paths.append(path)
    return paths


@pytest.fixture
def bundle(tmp_path, frame_paths):
    return export_bundle(
        [
            {
                "frame": 3,
                "type": "Wrong-Way Driving",
                "target_id": "ID 8",
                "confidence": 21.52,
            },
            {
                "frame": 5,
                "type": "Multi-Vehicle Collision",
                "target_id": "42 & 43",
                "confidence": 0.84,
            },
        ],
        frame_paths,
        "v41.mov",
        "CCTV",
        tmp_path / "tier1.zip",
    )


def test_bundle_import_is_idempotent_and_unverified(tmp_path, bundle, frame_paths):
    settings = Settings(data_dir=tmp_path / "data")
    repository = Repository(settings.data_dir)
    ids = import_bundle(bundle, settings, repository)
    assert len(ids) == 2
    assert import_bundle(bundle, settings, repository) == ids
    assert len(repository.list_recent()) == 2

    wrong_way = repository.get(ids[0])
    assert wrong_way["status"] == "awaiting_review"
    assert wrong_way["analysis"] is None
    assert wrong_way["provenance"]["vlm_analyzed"] is False
    assert wrong_way["tier1_event"]["heuristic_value"] == 21.52
    assert wrong_way["tier1_event"]["source_video"] == "v41.mov"
    assert wrong_way["notice_issued"] is False
    frames = wrong_way["tier1_event"]["frames"]
    assert len(frames) == 5
    trigger = next(frame for frame in frames if frame["role"] == "trigger")
    assert (settings.data_dir / "evidence" / trigger["file"]).read_bytes() == (
        frame_paths[2].read_bytes()
    )
    repository.review(ids[0], Review(decision="rejected", reviewer="tester"))
    assert repository.get(ids[0])["reviews"][0]["decision"] == "rejected"


def test_bundle_rejects_tampered_frame_before_import(tmp_path, bundle):
    corrupt = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(corrupt, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            target.writestr(name, b"wrong" if name.startswith("frames/") else data)
    settings = Settings(data_dir=tmp_path / "data")
    repository = Repository(settings.data_dir)
    with pytest.raises(ValueError, match="hash mismatch"):
        import_bundle(corrupt, settings, repository)
    assert repository.list_recent() == []


def test_bundle_rejects_undeclared_files(tmp_path, bundle):
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("../outside.txt", "bad")
    settings = Settings(data_dir=tmp_path / "data")
    with pytest.raises(ValueError, match="do not match"):
        import_bundle(bundle, settings, Repository(settings.data_dir))


def test_export_preserves_raw_measurement_name(tmp_path, bundle):
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["events"][0]["heuristic_value"] == 21.52
    assert manifest["events"][0]["trigger_type"] == "Wrong-Way Driving"
    assert manifest["evidence_origin"] == "raw_frame"


def test_notebook_preview_adapter_marks_nonoriginal_evidence(tmp_path):
    buffer = io.BytesIO()
    Image.new("RGB", (24, 16), "red").save(buffer, format="PNG")
    image = base64.b64encode(buffer.getvalue()).decode() + "\n"
    notebook = {
        "cells": [
            {
                "outputs": [
                    {
                        "output_type": "stream",
                        "text": [
                            "Evaluating 50 frames in CCTV mode...\n"
                            "TIER-1 BENCHMARK INCIDENT REPORT\n"
                            " frame                    type target_id  confidence\n"
                            "    39       Wrong-Way Driving      ID 8       21.52\n"
                            "\n[EVIDENCE] Wrong-Way-8:\n"
                        ],
                    },
                    {"output_type": "display_data", "data": {"image/png": image}},
                ]
            }
        ]
    }
    notebook_path = tmp_path / "notebook.ipynb"
    notebook_path.write_text(json.dumps(notebook), encoding="utf-8")
    bundle = export_preview_bundle(
        notebook_path, tmp_path / "preview.zip", "v41.mov", "CCTV"
    )
    settings = Settings(data_dir=tmp_path / "data")
    record_id = import_bundle(bundle, settings, Repository(settings.data_dir))[0]
    record = Repository(settings.data_dir).get(record_id)
    assert record["tier1_event"]["evidence_origin"] == "annotated_preview"
    assert record["tier1_event"]["trigger_frame"] == 39
    assert len(record["tier1_event"]["frames"]) == 1


def test_export_never_overwrites_existing_bundle(tmp_path, bundle, frame_paths):
    with pytest.raises(FileExistsError):
        export_bundle(
            [{"frame": 1, "type": "Collision", "target_id": "1 & 2"}],
            frame_paths,
            "v41.mov",
            "CCTV",
            bundle,
        )
