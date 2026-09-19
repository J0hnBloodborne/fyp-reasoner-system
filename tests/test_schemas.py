"""Record validation rejects invented fields and contradictory conclusions."""

import json

import pytest
from pydantic import ValidationError

from traffic_poc.prompts import SYSTEM_PROMPT, user_prompt
from traffic_poc.schemas import Analysis, Review, parse_analysis


def test_plain_and_fenced_json(candidate):
    raw = json.dumps(candidate)
    assert parse_analysis(raw).findings[0].plate is None
    assert parse_analysis(f"```json\n{raw}\n```") == parse_analysis(raw)


@pytest.mark.parametrize("raw", ["not JSON", '{"outcome":', "{}", "[]"])
def test_malformed_response(raw):
    with pytest.raises((ValueError, ValidationError)):
        parse_analysis(raw)


def test_no_prose_extraction(candidate):
    with pytest.raises(ValueError):
        parse_analysis("Here is my answer: " + json.dumps(candidate))


def test_outcome_contradiction(candidate):
    candidate["outcome"] = "no_visible_violation"
    with pytest.raises(ValidationError):
        Analysis.model_validate(candidate)


def test_candidate_requires_findings(candidate):
    candidate["findings"] = []
    with pytest.raises(ValidationError):
        Analysis.model_validate(candidate)


@pytest.mark.parametrize("confidence", [-0.1, 1.01, float("nan"), float("inf")])
def test_confidence_bounds(candidate, confidence):
    candidate["findings"][0]["confidence"] = confidence
    with pytest.raises(ValidationError):
        Analysis.model_validate(candidate)


def test_unsupported_violation(candidate):
    candidate["findings"][0]["violation_type"] = "red_light"
    with pytest.raises(ValidationError):
        Analysis.model_validate(candidate)


def test_unknown_fields(candidate):
    candidate["automatic_fine"] = True
    with pytest.raises(ValidationError):
        Analysis.model_validate(candidate)


def test_review_requires_human():
    with pytest.raises(ValidationError):
        Review(decision="approved", reviewer=" ")


def test_prompt_schema_is_json():
    assert json.loads(user_prompt().split("\n", 1)[1])["title"] == "Analysis"


def test_absent_motorcycle_is_not_uncertainty():
    assert "If no motorcycle or rider is visible, return no_visible_violation" in (
        SYSTEM_PROMPT
    )
