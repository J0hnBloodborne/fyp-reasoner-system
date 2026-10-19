"""Video upload runs Tier-1 detection, imports events and streams the footage."""

import json
import time
import urllib.error
import urllib.request

import pytest
from PIL import Image

from traffic_poc import pipeline as pipeline_module


@pytest.fixture
def fake_detection(monkeypatch):
    """Replace frame decoding, YOLO and ffmpeg with small deterministic stand-ins."""

    def extract_frames(video, directory, progress=None):
        directory.mkdir(parents=True)
        paths = []
        for index in range(6):
            path = directory / f"frame_{index:06d}.jpg"
            Image.new("RGB", (32, 24), (index * 30, 0, 0)).save(path)
            paths.append(path)
        progress(6, 6)
        return paths, 10.0

    def detect(frames, detector, weights, progress=None):
        progress(len(frames), len(frames))
        return [{"frame": 3, "type": "Wrong-Way Driving", "target_id": "ID 4"}]

    monkeypatch.setattr(pipeline_module, "extract_frames", extract_frames)
    monkeypatch.setattr(pipeline_module, "detect", detect)
    monkeypatch.setattr(pipeline_module, "make_preview", lambda video, out: False)


def upload(server, body, filename="clip.mp4", query="camera_type=CCTV"):
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/api/videos?{query}",
        data=body,
        headers={"Content-Type": "video/mp4", "X-Filename": filename},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def wait_video(server, video_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        video = server.pipeline.repository.get_video(video_id)
        if video["status"] in {"completed", "failed"}:
            return video
        time.sleep(0.05)
    raise TimeoutError(video_id)


def test_upload_detects_and_imports_events(server, fake_detection):
    video = upload(server, b"0123456789" * 100)
    assert video["status"] == "queued"
    video = wait_video(server, video["id"])
    assert video["status"] == "completed", video["error"]
    assert (video["frame_count"], video["fps"], video["event_count"]) == (6, 10.0, 1)
    [record_id] = video["record_ids"]
    record = server.pipeline.repository.get(record_id)
    assert record["tier1_event"]["video_id"] == video["id"]
    assert record["tier1_event"]["source_video"] == "clip.mp4"
    [summary] = server.pipeline.repository.search(source_video="clip.mp4")
    assert summary["video_id"] == video["id"]


def test_stream_supports_ranges(server, fake_detection):
    body = bytes(range(256)) * 8
    video = wait_video(server, upload(server, body)["id"])
    url = f"http://127.0.0.1:{server.server_port}/api/videos/{video['id']}/stream"
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.headers["Accept-Ranges"] == "bytes"
        assert response.read() == body
    request = urllib.request.Request(url, headers={"Range": "bytes=10-19"})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 206
        assert response.headers["Content-Range"] == f"bytes 10-19/{len(body)}"
        assert response.read() == body[10:20]


def test_rejects_unknown_formats(server, fake_detection):
    with pytest.raises(urllib.error.HTTPError) as exc:
        upload(server, b"data", filename="notes.txt")
    assert exc.value.code == 400
    assert server.pipeline.repository.list_videos() == []


def test_interrupted_videos_fail_on_restart(server, fake_detection):
    repository = server.pipeline.repository
    repository.create_video(
        {
            "id": "a" * 32,
            "created_at": "2026-10-19T00:00:00+00:00",
            "status": "detecting",
        }
    )
    repository.recover_interrupted()
    assert repository.get_video("a" * 32)["status"] == "failed"
