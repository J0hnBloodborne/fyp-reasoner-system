"""Portable Tier-1 bundle exporter; copy this single file into Colab."""

import hashlib
import json
import math
import uuid
import zipfile
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def export_bundle(
    violations: list[dict],
    frame_paths: list[str | Path],
    source_video: str,
    camera_type: str,
    destination: str | Path,
    *,
    fps: float | None = None,
    frame_offsets: tuple[int, ...] = (-2, -1, 0, 1, 2),
) -> Path:
    """Package original source frames and notebook event rows without reinterpreting them."""
    if not violations or len(violations) > 100:
        raise ValueError("Export between 1 and 100 candidate events")
    if not frame_paths:
        raise ValueError("Provide the ordered source frame paths")
    if camera_type not in {"CCTV", "DASHCAM"}:
        raise ValueError("camera_type must be CCTV or DASHCAM")
    if not frame_offsets or 0 not in frame_offsets or len(set(frame_offsets)) > 9:
        raise ValueError("Include the trigger offset 0 and at most 9 unique offsets")
    if fps is not None and (not math.isfinite(fps) or fps <= 0):
        raise ValueError("fps must be positive when supplied")

    manifest = {
        "schema_version": "1.0",
        "bundle_id": uuid.uuid4().hex,
        "source_video": Path(source_video).name,
        "camera_type": camera_type,
        "frame_count": len(frame_paths),
        "fps": fps,
        "evidence_origin": "raw_frame",
        "events": [],
    }
    destination = Path(destination)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for position, row in enumerate(violations, start=1):
            event_id = f"event-{position:04d}"
            trigger_frame = int(row["frame"])
            if not 1 <= trigger_frame <= len(frame_paths):
                raise ValueError(f"Event frame is outside the source: {trigger_frame}")
            value = row.get("confidence")
            if value is not None:
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError("Tier-1 heuristic value must be finite")
            event = {
                "event_id": event_id,
                "trigger_type": str(row["type"]),
                "trigger_frame": trigger_frame,
                "target_id": str(row["target_id"]),
                "heuristic_value": value,
                "frames": [],
            }
            for frame_index in sorted(
                {trigger_frame + offset for offset in frame_offsets}
            ):
                if not 1 <= frame_index <= len(frame_paths):
                    continue
                source = Path(frame_paths[frame_index - 1])
                suffix = source.suffix.lower()
                if suffix not in IMAGE_SUFFIXES:
                    raise ValueError(f"Unsupported frame format: {source}")
                data = source.read_bytes()
                member = f"frames/{event_id}/frame-{frame_index:06d}{suffix}"
                archive.writestr(member, data)
                event["frames"].append(
                    {
                        "frame_index": frame_index,
                        "role": "trigger"
                        if frame_index == trigger_frame
                        else "context",
                        "path": member,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            manifest["events"].append(event)
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        )
    return destination
