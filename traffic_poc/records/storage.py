"""SQLite job records, append-only human reviews and a full-text index."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from traffic_poc.records.schemas import Review
from traffic_poc.records.search import match_query, search_text, summarize


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
                CREATE VIRTUAL TABLE IF NOT EXISTS record_search USING fts5(
                    id UNINDEXED, body, tokenize='porter unicode61'
                );
            """)
            for row in db.execute(
                "SELECT id FROM records WHERE id NOT IN (SELECT id FROM record_search)"
            ).fetchall():
                self._index(db, row["id"])

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open per-operation connections for worker and request threads."""
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _reviews(db: sqlite3.Connection, record_id: str) -> list[dict]:
        return [
            {
                "review_id": review["id"],
                "created_at": review["created_at"],
                **json.loads(review["payload"]),
            }
            for review in db.execute(
                "SELECT * FROM reviews WHERE record_id=? ORDER BY id", (record_id,)
            )
        ]

    def _index(self, db: sqlite3.Connection, record_id: str) -> None:
        """Refresh one record's searchable text inside the caller's transaction."""
        row = db.execute(
            "SELECT payload FROM records WHERE id=?", (record_id,)
        ).fetchone()
        text = search_text(json.loads(row["payload"]), self._reviews(db, record_id))
        db.execute("DELETE FROM record_search WHERE id=?", (record_id,))
        db.execute(
            "INSERT INTO record_search (id, body) VALUES (?, ?)", (record_id, text)
        )

    def create(self, payload: dict) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO records VALUES (?, ?, ?, ?)",
                (
                    payload["id"],
                    payload["created_at"],
                    payload["status"],
                    json.dumps(payload),
                ),
            )
            self._index(db, payload["id"])

    def update(self, record_id: str, **changes) -> None:
        """Atomically update a job without touching its review history."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM records WHERE id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(record_id)
            payload = json.loads(row["payload"])
            payload.update(changes)
            db.execute(
                "UPDATE records SET status=?, payload=? WHERE id=?",
                (
                    payload["status"],
                    json.dumps(payload),
                    record_id,
                ),
            )
            self._index(db, record_id)

    def get(self, record_id: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM records WHERE id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(record_id)
            payload = json.loads(row["payload"])
            payload["reviews"] = self._reviews(db, record_id)
            return payload

    def search(
        self,
        query: str | None = None,
        imported_from: date | None = None,
        imported_to: date | None = None,
        limit: int = 100,
        **filters: str,
    ) -> list[dict]:
        """Rank text matches by BM25, or list newest first without a query.

        Filters compare against list summary fields; "type" matches any of a
        record's types and decision "unreviewed" matches records without
        reviews. Filtering runs in Python, which suits a local record store.
        """
        match = match_query(query) if query else None
        conditions, params = [], []
        if match:
            sql = (
                "SELECT r.id, r.payload, "
                "snippet(record_search, 1, '[', ']', '…', 12) AS snippet "
                "FROM records r JOIN record_search ON record_search.id = r.id"
            )
            conditions.append("record_search MATCH ?")
            params.append(match)
            order = "bm25(record_search)"
        else:
            sql = "SELECT r.id, r.payload, NULL AS snippet FROM records r"
            order = "r.created_at DESC"
        if imported_from:
            conditions.append("r.created_at >= ?")
            params.append(imported_from.isoformat())
        if imported_to:
            conditions.append("r.created_at < ?")
            params.append((imported_to + timedelta(days=1)).isoformat())
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        results = []
        with self.connect() as db:
            for row in db.execute(f"{sql} ORDER BY {order}", params).fetchall():
                summary = summarize(
                    json.loads(row["payload"]), self._reviews(db, row["id"])
                )
                if all(_matches(summary, key, value) for key, value in filters.items()):
                    results.append({**summary, "snippet": row["snippet"]})
                    if len(results) == limit:
                        break
        return results

    def review(self, record_id: str, review: Review) -> None:
        """Preserve the original model analysis and append validated human corrections."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status FROM records WHERE id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(record_id)
            if row["status"] not in {"completed", "awaiting_review"}:
                raise ValueError("Only completed or imported records can be reviewed")
            if row["status"] == "awaiting_review" and review.corrected_analysis:
                raise ValueError("Tier-1 candidates have no VLM analysis to correct")
            db.execute(
                "INSERT INTO reviews (record_id, created_at, payload) VALUES (?, ?, ?)",
                (record_id, now(), review.model_dump_json()),
            )
            self._index(db, record_id)

    def unverified_tier1(self) -> list[str]:
        """Tier-1 events never verified, or interrupted while queued or running."""
        with self.connect() as db:
            return [
                row["id"]
                for row in db.execute(
                    "SELECT id FROM records "
                    "WHERE json_extract(payload, '$.source') = 'tier1_bundle' "
                    "AND coalesce(json_extract(payload, '$.verification.status'), "
                    "'queued') IN ('queued', 'running') ORDER BY created_at"
                )
            ]

    def recover_interrupted(self) -> None:
        """Mark interrupted jobs failed rather than displaying them as eternally queued."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, payload FROM records WHERE status IN ('queued','running')"
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                payload.update(
                    status="failed",
                    finished_at=now(),
                    error="Application stopped before this job completed",
                )
                db.execute(
                    "UPDATE records SET status='failed', payload=? WHERE id=?",
                    (json.dumps(payload), row["id"]),
                )


def _matches(summary: dict, key: str, value: str) -> bool:
    if key == "type":
        return value in summary["types"]
    if key == "decision" and value == "unreviewed":
        return summary["decision"] is None
    return summary[key] == value
