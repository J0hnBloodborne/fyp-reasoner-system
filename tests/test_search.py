"""Full-text search and filters over uploaded images and Tier-1 events."""

from datetime import date

import pytest

from traffic_poc.records.schemas import Review
from traffic_poc.records.search import match_query
from traffic_poc.records.storage import Repository


def tier1(record_id, created_at, trigger, camera, verdict, observation):
    return {
        "id": record_id,
        "created_at": created_at,
        "status": "awaiting_review",
        "source": "tier1_bundle",
        "tier1_event": {
            "trigger_type": trigger,
            "source_video": "v41.mov",
            "camera_type": camera,
            "target_id": "ID 8",
            "trigger_frame": 120,
        },
        "verification": {
            "status": "completed",
            "result": {
                "observations": [{"frame_index": 120, "description": observation}],
                "verdict": verdict,
                "summary": observation,
                "limitations": [],
            },
        },
    }


@pytest.fixture
def repository(tmp_path):
    repository = Repository(tmp_path)
    repository.create(
        tier1(
            "wrongway",
            "2026-10-01T10:00:00+00:00",
            "Wrong-Way Driving",
            "CCTV",
            "supported",
            "A white car travels against oncoming traffic",
        )
    )
    repository.create(
        tier1(
            "crash",
            "2026-10-05T10:00:00+00:00",
            "Multi-Vehicle Collision",
            "DASHCAM",
            "not_supported",
            "Two cars pass close but never touch",
        )
    )
    repository.create(
        {
            "id": "upload",
            "created_at": "2026-10-03T10:00:00+00:00",
            "status": "completed",
            "source": "manual_upload",
            "filename": "market.jpg",
            "location": "Mall Road",
            "analysis": {
                "outcome": "candidate_violation",
                "findings": [
                    {
                        "violation_type": "no_helmet",
                        "subject": "Motorcycle rider at left",
                        "evidence": "Bare head visible",
                        "plate": None,
                        "confidence": None,
                    }
                ],
                "summary": "One rider without a helmet",
                "limitations": [],
            },
        }
    )
    return repository


def ids(results):
    return [item["id"] for item in results]


def test_no_query_lists_newest_first_with_summaries(repository):
    results = repository.search()
    assert ids(results) == ["crash", "upload", "wrongway"]
    assert results[2]["types"] == ["Wrong-Way Driving"]
    assert results[2]["verdict"] == "supported"
    assert results[1]["types"] == ["no_helmet"]
    assert results[1]["outcome"] == "candidate_violation"


def test_natural_language_query_stems_and_ranks(repository):
    results = repository.search("a car travelling against traffic")
    assert ids(results)[0] == "wrongway"
    assert "[travels]" in results[0]["snippet"]


def test_underscored_values_match_plain_words(repository):
    assert ids(repository.search("rider with no helmet")) == ["upload"]


def test_query_punctuation_is_not_fts_syntax(repository):
    assert repository.search('"AND (NOT* car') != []
    assert match_query("the of a") is None


def test_filters(repository):
    assert ids(repository.search(camera_type="DASHCAM")) == ["crash"]
    assert ids(repository.search(type="no_helmet")) == ["upload"]
    assert ids(repository.search(verdict="supported")) == ["wrongway"]
    assert ids(
        repository.search("car", source="tier1_bundle", verdict="not_supported")
    ) == ["crash"]


def test_import_date_range_is_inclusive(repository):
    results = repository.search(
        imported_from=date(2026, 10, 3), imported_to=date(2026, 10, 5)
    )
    assert ids(results) == ["crash", "upload"]


def test_reviews_update_index_and_decision(repository):
    repository.review(
        "wrongway",
        Review(
            decision="approved", reviewer="Rohaan", notes="Confirmed on night shift"
        ),
    )
    assert ids(repository.search("night shift")) == ["wrongway"]
    assert ids(repository.search(decision="approved")) == ["wrongway"]
    assert ids(repository.search(decision="unreviewed")) == ["crash", "upload"]


def test_existing_database_is_backfilled(tmp_path, repository):
    with repository.connect() as db:
        db.execute("DELETE FROM record_search")
    assert repository.search("helmet") == []
    assert ids(Repository(tmp_path).search("helmet")) == ["upload"]
