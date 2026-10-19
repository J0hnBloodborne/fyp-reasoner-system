"""Exercise real HTTP routes with a stub model, never a remote inference service."""

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from tests.conftest import wait_verified
from traffic_poc.detection.bundle import import_bundle
from traffic_poc.detection.export_bundle import export_bundle
from traffic_poc.web.server import LocalServer


@pytest.fixture
def server(pipeline):
    server = LocalServer(0)
    server.pipeline = pipeline
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def request(server, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{path}",
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    return urllib.request.urlopen(req, timeout=5)


def test_ui_and_health(server):
    with request(server, "/") as response:
        assert b"<title>Traffic Search</title>" in response.read()
        assert response.headers["Content-Security-Policy"]
    with request(server, "/api/health") as response:
        assert json.load(response)["model_id"] == "Qwen/Qwen3-VL-2B-Instruct"


@pytest.mark.parametrize(
    "path", ["/import", "/analyze", "/privacy", "/incident/" + "a" * 32]
)
def test_app_routes_serve_the_shell(server, path):
    with request(server, path) as response:
        assert response.headers["Content-Type"].startswith("text/html")
        assert b'<div id="root">' in response.read()


def test_built_assets(server):
    with request(server, "/assets/app.js") as response:
        assert response.headers["Content-Type"].startswith("text/javascript")
    with request(server, "/favicon.svg") as response:
        assert response.headers["Content-Type"] == "image/svg+xml"


@pytest.mark.parametrize(
    "path", ["/no-such-page", "/assets/../server.py", "/index.html", "/incident/1"]
)
def test_unknown_pages_get_the_app_not_found(server, path):
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(server, path)
    assert exc.value.code == 404
    assert exc.value.headers["Content-Type"].startswith("text/html")


def test_unknown_api_route_is_json(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(server, "/api/nothing")
    assert exc.value.code == 404
    assert json.load(exc.value) == {"error": "Not found"}


def test_http_lifecycle(server, image_base64):
    with request(server, "/api/records", {"image_base64": image_base64}) as response:
        assert response.status == 202
        record_id = json.load(response)["id"]
    server.pipeline.wait(record_id)
    with request(server, f"/api/records/{record_id}/image") as response:
        assert response.headers["Content-Type"] == "image/png"
        assert response.read().startswith(b"\x89PNG")
    with request(
        server,
        f"/api/records/{record_id}/review",
        {"decision": "approved", "reviewer": "tester"},
    ) as response:
        assert len(json.load(response)["reviews"]) == 1
    with request(server, f"/api/records/{record_id}/export") as response:
        assert "attachment" in response.headers["Content-Disposition"]
        assert json.load(response)["notice_issued"] is False


@pytest.mark.parametrize(
    "headers", [{"Origin": "https://evil.test"}, {"Host": "evil.test"}]
)
def test_cross_origin_denied(server, headers):
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(server, "/api/records", {}, headers)
    assert exc.value.code == 403


def test_bad_json_contract(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(server, "/api/records", {"unknown": True})
    assert exc.value.code == 400


def test_unknown_record_and_traversal(server):
    for path in ["/api/records/" + "a" * 32, "/../../requirements.txt"]:
        with pytest.raises(urllib.error.HTTPError) as exc:
            request(server, path)
        assert exc.value.code == 404


def test_imported_event_frame_and_review(server, tmp_path, image_base64):
    source = tmp_path / "frame_0000.png"
    source.write_bytes(base64.b64decode(image_base64))
    bundle = export_bundle(
        [{"frame": 1, "type": "Wrong-Way Driving", "target_id": "ID 8"}],
        [source],
        "v41.mov",
        "CCTV",
        tmp_path / "bundle.zip",
    )
    record_id = import_bundle(
        bundle, server.pipeline.settings, server.pipeline.repository
    )[0]
    with request(server, f"/api/records/{record_id}/frames/1") as response:
        assert response.headers["Content-Type"] == "image/png"
        assert response.read() == source.read_bytes()
    with request(server, f"/api/records/{record_id}") as response:
        record = json.load(response)
        assert record["status"] == "awaiting_review"
        assert record["analysis"] is None
    with request(
        server,
        f"/api/records/{record_id}/review",
        {"decision": "rejected", "reviewer": "tester"},
    ) as response:
        assert json.load(response)["reviews"][0]["decision"] == "rejected"


def post_zip(server, path, data):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{path}",
        data=data,
        headers={"Content-Type": "application/zip"},
    )
    return urllib.request.urlopen(req, timeout=5)


def test_bundle_upload_queues_verification_and_retry(server, tmp_path, image_base64):
    source = tmp_path / "frame_0000.png"
    source.write_bytes(base64.b64decode(image_base64))
    bundle = export_bundle(
        [{"frame": 1, "type": "Wrong-Way Driving", "target_id": "ID 8"}],
        [source],
        "v41.mov",
        "CCTV",
        tmp_path / "bundle.zip",
    )
    with post_zip(server, "/api/bundles", bundle.read_bytes()) as response:
        assert response.status == 201
        [record_id] = json.load(response)["record_ids"]
    repository = server.pipeline.repository
    # The stub returns an Analysis, not a Verification, so the first run fails.
    verification = wait_verified(server.pipeline, record_id)
    assert verification["status"] == "failed"
    server.pipeline.reasoner.raw = json.dumps(
        {
            "observations": [{"frame_index": 1, "description": "Car faces traffic"}],
            "verdict": "supported",
            "summary": "Wrong-way travel is visible",
            "limitations": [],
        }
    )
    with request(server, f"/api/records/{record_id}/verify", {}) as response:
        assert response.status == 202
    assert wait_verified(server.pipeline, record_id)["status"] == "completed"
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(server, f"/api/records/{record_id}/verify", {})
    assert exc.value.code == 400
    assert repository.get(record_id)["verification"]["status"] == "completed"


def test_bundle_upload_rejects_non_zip(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post_zip(server, "/api/bundles", b"not a zip")
    assert exc.value.code == 400
    assert server.pipeline.repository.search() == []


def test_report_download_and_upload_rejection(server, tmp_path, image_base64):
    source = tmp_path / "frame_0000.png"
    source.write_bytes(base64.b64decode(image_base64))
    bundle = export_bundle(
        [{"frame": 1, "type": "Wrong-Way Driving", "target_id": "ID 8"}],
        [source],
        "v41.mov",
        "CCTV",
        tmp_path / "bundle.zip",
    )
    [record_id] = import_bundle(
        bundle, server.pipeline.settings, server.pipeline.repository
    )
    with request(server, f"/api/records/{record_id}/report") as response:
        assert "attachment" in response.headers["Content-Disposition"]
        assert json.load(response)["incident"]["type"] == "Wrong-Way Driving"
    with request(server, "/api/records", {"image_base64": image_base64}) as response:
        upload_id = json.load(response)["id"]
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(server, f"/api/records/{upload_id}/report")
    assert exc.value.code == 400


def test_search_route_filters_and_rejects_bad_parameters(server, image_base64):
    with request(server, "/api/records", {"image_base64": image_base64}) as response:
        record_id = json.load(response)["id"]
    server.pipeline.wait(record_id)
    with request(
        server, "/api/records?q=rider+helmet&source=manual_upload"
    ) as response:
        [result] = json.load(response)
        assert result["id"] == record_id
        assert result["types"] == ["no_helmet"]
        assert "[helmet]" in result["snippet"]
    with request(server, "/api/records?source=tier1_bundle") as response:
        assert json.load(response) == []
    for query in ["plate=ABC", "imported_from=yesterday"]:
        with pytest.raises(urllib.error.HTTPError) as exc:
            request(server, f"/api/records?{query}")
        assert exc.value.code == 400
