"""SQLite job records and append-only human reviews."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from traffic_poc.schemas import Review


def now() -> str:
    """Use UTC for application timestamps; capture time remains supplied metadata."""
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "records.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL REFERENCES records(id),
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
            """)

    def connect(self) -> sqlite3.Connection:
        """Open per-operation connections for worker and request threads."""
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create(self, payload: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO records VALUES (?, ?, ?, ?)", (
                payload["id"], payload["created_at"], payload["status"],
                json.dumps(payload),
            ))

    def update(self, record_id: str, **changes) -> None:
        """Atomically update a job without touching its review history."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM records WHERE id=?",
                             (record_id,)).fetchone()
            if row is None:
                raise KeyError(record_id)
            payload = json.loads(row["payload"])
            payload.update(changes)
            db.execute("UPDATE records SET status=?, payload=? WHERE id=?", (
                payload["status"], json.dumps(payload), record_id,
            ))

    def get(self, record_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM records WHERE id=?",
                             (record_id,)).fetchone()
            if row is None:
                raise KeyError(record_id)
            payload = json.loads(row["payload"])
            payload["reviews"] = [
                {"review_id": review["id"], "created_at": review["created_at"],
                 **json.loads(review["payload"])}
                for review in db.execute(
                    "SELECT * FROM reviews WHERE record_id=? ORDER BY id", (record_id,))
            ]
            return payload

    def list_recent(self) -> list[dict]:
        with self.connect() as db:
            return [
                {"id": row["id"], "created_at": row["created_at"],
                 "status": row["status"]}
                for row in db.execute(
                    "SELECT id, created_at, status FROM records "
                    "ORDER BY created_at DESC LIMIT 50")
            ]

    def review(self, record_id: str, review: Review) -> None:
        """Preserve the original model analysis and append validated human corrections."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM records WHERE id=?",
                             (record_id,)).fetchone()
            if row is None:
                raise KeyError(record_id)
            if row["status"] != "completed":
                raise ValueError("Only completed records can be reviewed")
            db.execute(
                "INSERT INTO reviews (record_id, created_at, payload) VALUES (?, ?, ?)",
                (record_id, now(), review.model_dump_json()),
            )

    def recover_interrupted(self) -> None:
        """Mark interrupted jobs failed rather than displaying them as eternally queued."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, payload FROM records WHERE status IN ('queued','running')"
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                payload.update(status="failed", finished_at=now(),
                               error="Application stopped before this job completed")
                db.execute("UPDATE records SET status='failed', payload=? WHERE id=?",
                           (json.dumps(payload), row["id"]))
