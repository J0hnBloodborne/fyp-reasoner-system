"""Searchable text and list summaries for uploaded images and Tier-1 events."""

import re

STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "by", "did", "do", "does",
    "for", "from", "has", "have", "in", "into", "is", "it", "its", "me", "of",
    "on", "or", "show", "that", "the", "there", "this", "to", "was", "were",
    "where", "which", "while", "with", "find", "all", "some",
}  # fmt: skip


def match_query(text: str) -> str | None:
    """Turn natural language into an FTS5 OR query; BM25 ranks the matches."""
    terms = [t for t in re.findall(r"\w+", text.lower()) if t not in STOPWORDS]
    return " OR ".join(f'"{term}"' for term in dict.fromkeys(terms)) or None


def search_text(record: dict, reviews: list[dict]) -> str:
    """Flatten every human-readable field; underscores tokenize as separators."""
    parts = [record.get("filename"), record.get("location"), record.get("captured_at")]
    if analysis := record.get("analysis"):
        parts += [analysis["outcome"], analysis["summary"], *analysis["limitations"]]
        for finding in analysis["findings"]:
            parts += [
                finding["violation_type"],
                finding["subject"],
                finding["evidence"],
                finding["plate"],
            ]
    if event := record.get("tier1_event"):
        parts += [
            event["trigger_type"],
            event["source_video"],
            event["camera_type"],
            event["target_id"],
        ]
    if result := (record.get("verification") or {}).get("result"):
        parts += [result["verdict"], result["summary"], *result["limitations"]]
        parts += [item["description"] for item in result["observations"]]
    for review in reviews:
        parts += [review["decision"], review["reviewer"], review["notes"]]
    return "\n".join(str(part) for part in parts if part)


def summarize(record: dict, reviews: list[dict]) -> dict:
    """List row fields shared by both record kinds."""
    event = record.get("tier1_event") or {}
    analysis = record.get("analysis") or {}
    verification = record.get("verification") or {}
    if event:
        types = [event["trigger_type"]]
    else:
        types = sorted(
            {item["violation_type"] for item in analysis.get("findings", [])}
        )
    return {
        "id": record["id"],
        "created_at": record["created_at"],
        "status": record["status"],
        "source": record.get("source"),
        "types": types,
        "source_video": event.get("source_video"),
        "camera_type": event.get("camera_type"),
        "trigger_frame": event.get("trigger_frame"),
        "outcome": analysis.get("outcome"),
        "verification_status": verification.get("status"),
        "verdict": (verification.get("result") or {}).get("verdict"),
        "decision": reviews[-1]["decision"] if reviews else None,
    }
