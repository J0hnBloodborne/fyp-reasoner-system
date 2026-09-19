"""Convert an executed Tier-1 notebook's displayed evidence to a preview bundle."""

import argparse
import base64
import hashlib
import json
import re
import uuid
import zipfile
from pathlib import Path

from traffic_poc.tier1.bundle import Tier1Manifest


def export_preview_bundle(
    notebook_path: Path,
    destination: Path,
    source_video: str,
    camera_type: str,
) -> Path:
    """Pair final incident-report rows with displayed images in notebook order."""
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    candidates = [
        cell
        for cell in notebook.get("cells", [])
        if any(
            "TIER-1 BENCHMARK INCIDENT REPORT" in "".join(output.get("text", []))
            for output in cell.get("outputs", [])
        )
    ]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one executed Tier-1 report cell")
    outputs = candidates[0]["outputs"]
    report = "".join("".join(output.get("text", [])) for output in outputs)
    match = re.search(r"Evaluating (\d+) frames", report)
    if not match:
        raise ValueError("Notebook output does not contain the frame count")
    frame_count = int(match.group(1))
    lines = report.splitlines()
    headers = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(r"\s*frame\s+type\s+target_id\s+confidence\s*", line)
    ]
    if len(headers) != 1:
        raise ValueError("Expected one Tier-1 incident table")
    rows = []
    for line in lines[headers[0] + 1 :]:
        if not line.strip():
            break
        parts = re.fullmatch(
            r"\s*(\d+)\s+(.+?)\s{2,}(.+?)\s{2,}(-?\d+(?:\.\d+)?)\s*",
            line,
        )
        if parts is None:
            raise ValueError("Could not parse a Tier-1 incident row")
        rows.append(parts.groups())
    previews = [
        "".join(output["data"]["image/png"])
        for output in outputs
        if "image/png" in output.get("data", {})
    ]
    if not rows or len(rows) != len(previews):
        raise ValueError("Incident rows and displayed evidence images do not match")

    manifest = {
        "schema_version": "1.0",
        "bundle_id": uuid.uuid4().hex,
        "source_video": Path(source_video).name,
        "camera_type": camera_type,
        "frame_count": frame_count,
        "fps": None,
        "evidence_origin": "annotated_preview",
        "events": [],
    }
    images = {}
    for position, (row, encoded) in enumerate(
        zip(rows, previews, strict=True), start=1
    ):
        frame_index, trigger_type, target_id, heuristic_value = row
        event_id = f"event-{position:04d}"
        member = f"frames/{event_id}/frame-{int(frame_index):06d}.png"
        data = base64.b64decode(encoded.strip(), validate=True)
        images[member] = data
        manifest["events"].append(
            {
                "event_id": event_id,
                "trigger_type": trigger_type,
                "trigger_frame": int(frame_index),
                "target_id": target_id,
                "heuristic_value": float(heuristic_value),
                "frames": [
                    {
                        "frame_index": int(frame_index),
                        "role": "trigger",
                        "path": member,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                ],
            }
        )
    Tier1Manifest.model_validate(manifest)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for member, data in images.items():
            bundle.writestr(member, data)
        bundle.writestr("manifest.json", json.dumps(manifest, separators=(",", ":")))
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Bundle notebook previews for review")
    parser.add_argument("notebook", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source-video", required=True)
    parser.add_argument("--camera-type", choices=["CCTV", "DASHCAM"], required=True)
    args = parser.parse_args()
    print(
        export_preview_bundle(
            args.notebook, args.destination, args.source_video, args.camera_type
        )
    )


if __name__ == "__main__":
    main()
