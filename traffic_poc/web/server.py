"""Local-only HTTP transport for the evidence pipeline."""

import json
import logging
import re
import tempfile
import uuid
import zipfile
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import ValidationError

from traffic_poc.detection.bundle import MAX_BUNDLE_BYTES, import_bundle
from traffic_poc.pipeline import Pipeline, PipelineBusy, Submission, VideoUpload
from traffic_poc.records.report import build_report
from traffic_poc.records.reviews import Review

STATIC = Path(__file__).parent / "static"
# Client-side routes of the single-page app; each serves index.html.
APP_ROUTE = re.compile(r"/(?:import|analyze|privacy|incident/[a-f0-9]{32})?")
# Built assets: a flat name in static/ or static/assets/, never a nested path.
STATIC_FILE = re.compile(r"/((?:assets/)?[A-Za-z0-9][A-Za-z0-9._-]*)")
CONTENT_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}
RECORD_ROUTE = re.compile(
    r"/api/records/([a-f0-9]{32})(?:/(image|original|export|report|review|verify))?"
)
VIDEO_ROUTE = re.compile(r"/api/videos/([a-f0-9]{32})(/stream)?")
VIDEO_SUFFIXES = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm"}
VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/mp4",
    ".webm": "video/webm",
}
MAX_VIDEO_BYTES = 2 * 1024**3
RANGE = re.compile(r"bytes=(\d*)-(\d*)")
FRAME_ROUTE = re.compile(r"/api/records/([a-f0-9]{32})/frames/([1-9][0-9]{0,8})")
SEARCH_FILTERS = {
    "type",
    "source",
    "camera_type",
    "source_video",
    "verification_status",
    "verdict",
    "outcome",
    "decision",
}
logger = logging.getLogger(__name__)


def search_options(query: str) -> dict:
    """Map query parameters to Repository.search arguments; reject unknown ones."""
    params = {key: values[-1] for key, values in parse_qs(query).items()}
    unknown = set(params) - SEARCH_FILTERS - {"q", "imported_from", "imported_to"}
    if unknown:
        raise ValueError(f"Unknown search parameters: {', '.join(sorted(unknown))}")
    options = {key: params[key] for key in SEARCH_FILTERS & set(params)}
    options["query"] = params.get("q")
    for key in ("imported_from", "imported_to"):
        if key in params:
            options[key] = date.fromisoformat(params[key])
    return options


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

    def _page(self, status: int) -> None:
        """Serve the app shell; the app renders the route, including not found."""
        self._send(
            status, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8"
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

    def _bundle(self) -> list[str]:
        """Stream a ZIP body to disk, import it, and queue each event's verification."""
        if self.headers.get("Content-Type", "").split(";")[0] != "application/zip":
            raise ValueError("Content-Type must be application/zip")
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Chunked requests are not supported")
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > MAX_BUNDLE_BYTES:
            raise ValueError("Bundle is empty or too large")
        pipeline = self.server.pipeline
        with tempfile.NamedTemporaryFile(
            dir=pipeline.settings.data_dir, suffix=".zip", delete=False
        ) as upload:
            path = Path(upload.name)
            remaining = size
            while remaining:
                chunk = self.rfile.read(min(remaining, 1024 * 1024))
                if not chunk:
                    break
                upload.write(chunk)
                remaining -= len(chunk)
        try:
            if remaining:
                raise ValueError("Incomplete request body")
            ids = import_bundle(path, pipeline.settings, pipeline.repository)
        except zipfile.BadZipFile as exc:
            raise ValueError("Upload is not a valid ZIP bundle") from exc
        finally:
            path.unlink()
        for record_id in ids:
            if (pipeline.repository.get(record_id).get("verification") or {}).get(
                "status"
            ) is None:
                pipeline.verify(record_id)
        return ids

    def _video(self, query: str) -> str:
        """Stream a video body to data/videos and queue Tier-1 detection."""
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Chunked requests are not supported")
        params = {key: values[-1] for key, values in parse_qs(query).items()}
        upload = VideoUpload(
            filename=unquote(self.headers.get("X-Filename", "")),
            camera_type=params.get("camera_type", "CCTV"),
            allowed_direction=int(params.get("allowed_direction", "-1")),
        )
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in VIDEO_SUFFIXES:
            raise ValueError("Upload an MP4, MOV, AVI, MKV or WebM video")
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > MAX_VIDEO_BYTES:
            raise ValueError("Video is empty or larger than 2 GB")
        directory = self.server.pipeline.settings.data_dir / "videos"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{uuid.uuid4().hex}{suffix}"
        remaining = size
        with path.open("wb") as file:
            while remaining:
                chunk = self.rfile.read(min(remaining, 1024 * 1024))
                if not chunk:
                    break
                file.write(chunk)
                remaining -= len(chunk)
        try:
            if remaining:
                raise ValueError("Incomplete request body")
            return self.server.pipeline.submit_video(path, upload)
        except Exception:
            path.unlink()
            raise

    def _stream(self, file: Path, content_type: str) -> None:
        """Send a file in 1 MB chunks, honouring one byte range for seeking."""
        size = file.stat().st_size
        start, end = 0, size - 1
        match = RANGE.fullmatch(self.headers.get("Range", ""))
        if match and (match.group(1) or match.group(2)):
            if match.group(1):
                start = int(match.group(1))
                end = min(int(match.group(2) or end), end)
            else:
                start = max(0, size - int(match.group(2)))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with file.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = source.read(min(remaining, 1024 * 1024))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self) -> None:
        if not self._trusted_request():
            self._json(HTTPStatus.FORBIDDEN, {"error": "Local same-origin access only"})
            return
        url = urlsplit(self.path)
        path = url.path
        pipeline = self.server.pipeline
        try:
            if APP_ROUTE.fullmatch(path):
                self._page(200)
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
                self._json(200, pipeline.repository.search(**search_options(url.query)))
            elif path == "/api/videos":
                self._json(200, pipeline.repository.list_videos())
            elif match := VIDEO_ROUTE.fullmatch(path):
                video = pipeline.repository.get_video(match.group(1))
                if match.group(2):
                    name = video["preview"] or video["file"]
                    file = pipeline.settings.data_dir / "videos" / name
                    kind = VIDEO_TYPES.get(file.suffix, "application/octet-stream")
                    self._stream(file, kind)
                else:
                    self._json(200, video)
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
                    file = pipeline.settings.data_dir / "evidence" / frame["file"]
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
                elif action == "report":
                    self._send(
                        200,
                        json.dumps(build_report(record), indent=2).encode(),
                        "application/json",
                        f"{record_id}-report.json",
                    )
                elif action is None:
                    self._json(200, record)
                else:
                    self._json(404, {"error": "Not found"})
            elif path.startswith("/api/"):
                self._json(404, {"error": "Not found"})
            elif (
                (match := STATIC_FILE.fullmatch(path))
                and (file := STATIC / match.group(1)).suffix in CONTENT_TYPES
                and file.is_file()
            ):
                self._send(200, file.read_bytes(), CONTENT_TYPES[file.suffix])
            else:
                self._page(404)
        except (KeyError, FileNotFoundError):
            self._json(404, {"error": "Record or evidence not found"})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except ConnectionError:  # The client left before the response.
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
            elif path == "/api/bundles":
                self._json(201, {"record_ids": self._bundle()})
            elif path == "/api/videos":
                video_id = self._video(urlsplit(self.path).query)
                self._json(202, pipeline.repository.get_video(video_id))
            elif (match := RECORD_ROUTE.fullmatch(path)) and match.group(2) == "review":
                review = Review.model_validate(self._body())
                pipeline.repository.review(match.group(1), review)
                self._json(200, pipeline.repository.get(match.group(1)))
            elif match and match.group(2) == "verify":
                pipeline.verify(match.group(1))
                self._json(202, pipeline.repository.get(match.group(1)))
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
        except ConnectionError:  # The client left; the work itself is done.
            return
        except Exception:
            logger.exception("Request failed")
            self._json(500, {"error": "Internal error; see application log"})

    def log_message(self, format: str, *args) -> None:
        logger.info("%s %s", self.address_string(), format % args)
