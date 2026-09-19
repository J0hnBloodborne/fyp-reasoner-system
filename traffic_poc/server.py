"""Local-only HTTP transport for the evidence pipeline."""

import json
import logging
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from traffic_poc.pipeline import Pipeline, PipelineBusy
from traffic_poc.schemas import Review, Submission

STATIC = Path(__file__).parent / "static"
RECORD_ROUTE = re.compile(
    r"/api/records/([a-f0-9]{32})(?:/(image|original|export|review))?"
)
FRAME_ROUTE = re.compile(r"/api/records/([a-f0-9]{32})/frames/([1-9][0-9]{0,8})")
logger = logging.getLogger(__name__)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int):
        super().__init__(("127.0.0.1", port), Handler)
        self.pipeline: Pipeline | None = None


class Handler(BaseHTTPRequestHandler):
    """Serve only enumerated assets and record routes, never arbitrary local paths."""

    server: LocalServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def _trusted_request(self) -> bool:
        allowed = {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return host in allowed and (not origin or origin == f"http://{host}")

    def _send(
        self, status: int, data: bytes, content_type: str, download: str | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' blob:; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        if download:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{download}"'
            )
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, data: dict | list) -> None:
        self._send(
            status,
            json.dumps(data, allow_nan=False).encode(),
            "application/json; charset=utf-8",
        )

    def _body(self) -> dict:
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("Content-Type must be application/json")
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Chunked requests are not supported")
        size = int(self.headers.get("Content-Length", "0"))
        limit = (self.server.pipeline.settings.max_upload_bytes * 4 // 3) + 8192
        if size < 1 or size > limit:
            raise ValueError("Request is empty or too large")
        data = self.rfile.read(size)
        if len(data) != size:
            raise ValueError("Incomplete request body")
        return json.loads(data)

    def do_GET(self) -> None:
        if not self._trusted_request():
            self._json(HTTPStatus.FORBIDDEN, {"error": "Local same-origin access only"})
            return
        path = urlsplit(self.path).path
        pipeline = self.server.pipeline
        try:
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if path in assets:
                filename, content_type = assets[path]
                self._send(200, (STATIC / filename).read_bytes(), content_type)
            elif path == "/api/health":
                self._json(
                    200,
                    {
                        "model_id": pipeline.settings.model_id,
                        "model_state": getattr(pipeline.reasoner, "state", "external"),
                        "offline": pipeline.settings.offline,
                    },
                )
            elif path == "/api/records":
                self._json(200, pipeline.repository.list_recent())
            elif match := FRAME_ROUTE.fullmatch(path):
                record_id, frame_index = match.groups()
                record = pipeline.repository.get(record_id)
                event = record.get("tier1_event") or {}
                frame = next(
                    (
                        item
                        for item in event.get("frames", [])
                        if item["frame_index"] == int(frame_index)
                    ),
                    None,
                )
                if frame is None:
                    self._json(404, {"error": "Evidence frame not found"})
                else:
                    filename = (
                        f"{record_id}.original"
                        if frame["role"] == "trigger"
                        else f"{record_id}.frame-{frame['frame_index']:06d}.original"
                    )
                    file = pipeline.settings.data_dir / "evidence" / filename
                    self._send(200, file.read_bytes(), frame["media_type"])
            elif match := RECORD_ROUTE.fullmatch(path):
                record_id, action = match.groups()
                record = pipeline.repository.get(record_id)
                if action in {"image", "original"}:
                    suffix = ".review.png" if action == "image" else ".original"
                    file = (
                        pipeline.settings.data_dir / "evidence" / f"{record_id}{suffix}"
                    )
                    self._send(
                        200,
                        file.read_bytes(),
                        "image/png"
                        if action == "image"
                        else "application/octet-stream",
                        f"{record_id}.original" if action == "original" else None,
                    )
                elif action == "export":
                    self._send(
                        200,
                        json.dumps(record, indent=2).encode(),
                        "application/json",
                        f"{record_id}.json",
                    )
                elif action is None:
                    self._json(200, record)
                else:
                    self._json(404, {"error": "Not found"})
            else:
                self._json(404, {"error": "Not found"})
        except (KeyError, FileNotFoundError):
            self._json(404, {"error": "Record or evidence not found"})
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self) -> None:
        if not self._trusted_request():
            self._json(403, {"error": "Local same-origin access only"})
            return
        path = urlsplit(self.path).path
        pipeline = self.server.pipeline
        try:
            if path == "/api/records":
                submission = Submission.model_validate(self._body())
                record_id = pipeline.submit(submission)
                self._json(202, {"id": record_id})
            elif (match := RECORD_ROUTE.fullmatch(path)) and match.group(2) == "review":
                review = Review.model_validate(self._body())
                pipeline.repository.review(match.group(1), review)
                self._json(200, pipeline.repository.get(match.group(1)))
            else:
                self._json(404, {"error": "Not found"})
        except PipelineBusy as exc:
            self._json(429, {"error": str(exc)})
        except ValidationError as exc:
            self._json(
                400,
                {
                    "error": "; ".join(
                        f"{'.'.join(map(str, err['loc']))}: {err['msg']}"
                        for err in exc.errors()
                    )
                },
            )
        except (ValueError, UnicodeError, TimeoutError) as exc:
            self._json(400, {"error": str(exc)})
        except KeyError:
            self._json(404, {"error": "Record not found"})
        except Exception:
            logger.exception("Request failed")
            self._json(500, {"error": "Internal error; see application log"})

    def log_message(self, format: str, *args) -> None:
        logger.info("%s %s", self.address_string(), format % args)
