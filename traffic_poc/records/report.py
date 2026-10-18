"""Incident report combining Tier-1 detection, Tier-2 verification and reviews."""

from traffic_poc.records.store import now

REPORT_VERSION = "1.0"


def _seconds(frame_index: int, fps: float | None) -> float | None:
    """Frame 1 is the first decoded frame, at 0 s."""
    return None if fps is None else round((frame_index - 1) / fps, 3)


def build_report(record: dict) -> dict:
    """Build on demand so the report always reflects the latest review."""
    if record.get("source") != "tier1_bundle":
        raise ValueError("Incident reports cover imported Tier-1 events only")
    event = record["tier1_event"]
    fps = event["fps"]
    verification = record.get("verification") or {}
    result = verification.get("result") or {}
    provenance = verification.get("provenance") or {}
    reviews = record["reviews"]
    return {
        "report_version": REPORT_VERSION,
        "generated_at": now(),
        "record_id": record["id"],
        "incident": {
            "type": event["trigger_type"],
            "source_video": event["source_video"],
            "camera_type": event["camera_type"],
            "trigger_frame": event["trigger_frame"],
            "trigger_time_seconds": _seconds(event["trigger_frame"], fps),
            "fps": fps,
            "target_id": event["target_id"],
        },
        "tier1": {
            "bundle_id": event["bundle_id"],
            "event_id": event["event_id"],
            "manifest_sha256": record["tier1_manifest_sha256"],
            "evidence_origin": event["evidence_origin"],
            "heuristic_value": event["heuristic_value"],
            "heuristic_value_kind": event["heuristic_value_kind"],
        },
        "tier2": {
            "status": verification.get("status", "not_queued"),
            "verdict": result.get("verdict"),
            "observations": result.get("observations", []),
            "summary": result.get("summary"),
            "limitations": result.get("limitations", []),
            "error": verification.get("error"),
            "prompt_version": verification.get("prompt_version"),
            "prompt_sha256": verification.get("prompt_sha256"),
            "model_id": provenance.get("model_id"),
            "resolved_revision": provenance.get("resolved_revision"),
        },
        "evidence": [
            {
                "frame_index": frame["frame_index"],
                "role": frame["role"],
                "time_seconds": _seconds(frame["frame_index"], fps),
                "sha256": frame["sha256"],
                "media_type": frame["media_type"],
                "width": frame["width"],
                "height": frame["height"],
                "url": f"/api/records/{record['id']}/frames/{frame['frame_index']}",
            }
            for frame in sorted(event["frames"], key=lambda item: item["frame_index"])
        ],
        "reviews": reviews,
        "current_decision": reviews[-1]["decision"] if reviews else None,
        "confidence_calibrated": False,
        "notice_issued": False,
    }
