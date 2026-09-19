"""Versioned, file-based handoff from a detector to the local review application."""

import hashlib
import io
import uuid
import zipfile
from pathlib import Path
from typing import Literal, Self

from PIL import Image
from pydantic import Field, model_validator

from traffic_poc.config import Settings
from traffic_poc.records.evidence import decode_image, ingest_bytes
from traffic_poc.records.schemas import Contract
from traffic_poc.records.storage import Repository, now

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_BUNDLE_BYTES = 256 * 1024 * 1024
MAX_BUNDLE_FILES = 901
MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class Tier1Frame(Contract):
    frame_index: int = Field(ge=1)
    role: Literal["trigger", "context"]
    path: str = Field(
        pattern=r"^frames/[A-Za-z0-9_-]+/frame-[0-9]{6,}\.(jpg|jpeg|png|webp)$"
    )
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Tier1Event(Contract):
    event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    trigger_type: str = Field(min_length=1, max_length=100)
    trigger_frame: int = Field(ge=1)
    target_id: str = Field(min_length=1, max_length=100)
    heuristic_value: float | None = Field(default=None, allow_inf_nan=False)
    frames: list[Tier1Frame] = Field(min_length=1, max_length=9)

    @model_validator(mode="after")
    def valid_frames(self) -> Self:
        if len({frame.path for frame in self.frames}) != len(self.frames):
            raise ValueError("Event frame paths must be unique")
        if len({frame.frame_index for frame in self.frames}) != len(self.frames):
            raise ValueError("Event frame indices must be unique")
        triggers = [frame for frame in self.frames if frame.role == "trigger"]
        if len(triggers) != 1 or triggers[0].frame_index != self.trigger_frame:
            raise ValueError("Exactly one frame must match the trigger frame")
        if any(frame.path.split("/")[1] != self.event_id for frame in self.frames):
            raise ValueError("Frame paths must belong to their event")
        if any(
            int(Path(frame.path).stem.removeprefix("frame-")) != frame.frame_index
            for frame in self.frames
        ):
            raise ValueError("Frame filenames must match their frame indices")
        return self


class Tier1Manifest(Contract):
    schema_version: Literal["1.0"]
    bundle_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    source_video: str = Field(min_length=1, max_length=200)
    camera_type: Literal["CCTV", "DASHCAM"]
    frame_count: int = Field(ge=1)
    fps: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    evidence_origin: Literal["raw_frame", "annotated_preview"] = "raw_frame"
    events: list[Tier1Event] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_events(self) -> Self:
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError("Event IDs must be unique within a bundle")
        if any(event.trigger_frame > self.frame_count for event in self.events):
            raise ValueError("Trigger frame exceeds frame count")
        if any(
            frame.frame_index > self.frame_count
            for event in self.events
            for frame in event.frames
        ):
            raise ValueError("Evidence frame exceeds frame count")
        paths = [frame.path for event in self.events for frame in event.frames]
        if len(set(paths)) != len(paths):
            raise ValueError("Frame paths must be unique across the bundle")
        return self


def _read_bundle(path: Path, settings: Settings) -> tuple[Tier1Manifest, bytes, dict]:
    """Validate ZIP inventory, manifest, hashes, and every image before writing."""
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Bundle exceeds the compressed size limit")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) > MAX_BUNDLE_FILES or len(names) != len(set(names)):
            raise ValueError("Bundle has too many files or duplicate names")
        if "manifest.json" not in names:
            raise ValueError("Bundle is missing manifest.json")
        if any(info.is_dir() for info in infos):
            raise ValueError("Bundle may contain only declared files")
        if sum(info.file_size for info in infos) > MAX_BUNDLE_BYTES:
            raise ValueError("Bundle exceeds the uncompressed size limit")
        manifest_info = archive.getinfo("manifest.json")
        if manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise ValueError("Bundle manifest is too large")
        manifest_bytes = archive.read("manifest.json")
        manifest = Tier1Manifest.model_validate_json(manifest_bytes)
        frames = [frame for event in manifest.events for frame in event.frames]
        declared = {"manifest.json", *(frame.path for frame in frames)}
        if set(names) != declared:
            raise ValueError("Bundle files do not match its manifest")
        images = {}
        for frame in frames:
            info = archive.getinfo(frame.path)
            if info.file_size > settings.max_upload_bytes:
                raise ValueError(f"Frame exceeds image size limit: {frame.path}")
            data = archive.read(frame.path)
            if hashlib.sha256(data).hexdigest() != frame.sha256:
                raise ValueError(f"Frame hash mismatch: {frame.path}")
            image = decode_image(data, settings)
            with Image.open(io.BytesIO(data)) as source:
                if source.get_format_mimetype() != MEDIA_TYPES[Path(frame.path).suffix]:
                    raise ValueError(
                        f"Frame extension does not match image: {frame.path}"
                    )
            images[frame.path] = (data, image.size)
    return manifest, manifest_bytes, images


def import_bundle(path: Path, settings: Settings, repository: Repository) -> list[str]:
    """Import unverified Tier-1 candidates without running or claiming VLM analysis."""
    manifest, manifest_bytes, images = _read_bundle(path, settings)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    ids = []
    directory = settings.data_dir / "evidence"
    for event in manifest.events:
        record_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"traffic-tier1:{manifest.bundle_id}:{event.event_id}"
        ).hex
        try:
            existing = repository.get(record_id)
        except KeyError:
            existing = None
        if existing:
            if existing.get("tier1_manifest_sha256") != manifest_hash:
                raise ValueError(
                    "Bundle ID was already imported with different content"
                )
            for frame in existing["tier1_event"]["frames"]:
                filename = (
                    f"{record_id}.original"
                    if frame["role"] == "trigger"
                    else f"{record_id}.frame-{frame['frame_index']:06d}.original"
                )
                saved = directory / filename
                if (
                    not saved.is_file()
                    or hashlib.sha256(saved.read_bytes()).hexdigest() != frame["sha256"]
                ):
                    raise ValueError(
                        "Previously imported evidence is missing or changed"
                    )
            ids.append(record_id)
            continue

        trigger = next(frame for frame in event.frames if frame.role == "trigger")
        evidence = ingest_bytes(images[trigger.path][0], record_id, settings)
        saved_frames = []
        for frame in event.frames:
            data, (width, height) = images[frame.path]
            filename = (
                evidence.original_path.name
                if frame.role == "trigger"
                else f"{record_id}.frame-{frame.frame_index:06d}.original"
            )
            if frame.role != "trigger":
                (directory / filename).write_bytes(data)
            saved_frames.append(
                {
                    "frame_index": frame.frame_index,
                    "role": frame.role,
                    "file": filename,
                    "sha256": frame.sha256,
                    "width": width,
                    "height": height,
                    "media_type": MEDIA_TYPES[Path(frame.path).suffix],
                }
            )

        repository.create(
            {
                "schema_version": "1.0",
                "id": record_id,
                "created_at": now(),
                "status": "awaiting_review",
                "source": "tier1_bundle",
                "filename": Path(trigger.path).name,
                "location": None,
                "captured_at": None,
                "prompt_version": None,
                "prompt_sha256": None,
                "evidence": evidence.metadata(),
                "tier1_manifest_sha256": manifest_hash,
                "tier1_event": {
                    "bundle_id": manifest.bundle_id,
                    "event_id": event.event_id,
                    "source_video": manifest.source_video,
                    "camera_type": manifest.camera_type,
                    "frame_count": manifest.frame_count,
                    "fps": manifest.fps,
                    "evidence_origin": manifest.evidence_origin,
                    "trigger_type": event.trigger_type,
                    "trigger_frame": event.trigger_frame,
                    "target_id": event.target_id,
                    "heuristic_value": event.heuristic_value,
                    "heuristic_value_kind": "Tier-1 raw confidence column; not a probability",
                    "frames": saved_frames,
                },
                "analysis": None,
                "raw_response": None,
                "provenance": {"import_type": "tier1_bundle", "vlm_analyzed": False},
                "error": None,
                "confidence_calibrated": False,
                "notice_issued": False,
            }
        )
        ids.append(record_id)
    return ids
