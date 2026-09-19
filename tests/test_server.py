"""Exercise real HTTP routes with a stub model, never a remote inference service."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from traffic_poc.server import LocalServer


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
        assert b"Traffic evidence review" in response.read()
        assert response.headers["Content-Security-Policy"]
    with request(server, "/api/health") as response:
        assert json.load(response)["model_id"] == "Qwen/Qwen3-VL-2B-Instruct"


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
