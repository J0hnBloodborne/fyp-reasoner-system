"""Versioned contracts shared by inference, storage, and review."""

import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Finding(Contract):
    violation_type: Literal["no_helmet", "triple_riding"]
    subject: str = Field(min_length=1, max_length=300)
    evidence: str = Field(min_length=1, max_length=1000)
    plate: str | None = Field(default=None, min_length=1, max_length=40)
    confidence: float | None = Field(default=None, ge=0, le=1)


class Analysis(Contract):
    outcome: Literal["candidate_violation", "no_visible_violation", "uncertain"]
    findings: list[Finding] = Field(max_length=12)
    summary: str = Field(min_length=1, max_length=1500)
    limitations: list[str] = Field(max_length=12)

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        """Reject contradictions instead of repairing model claims silently."""
        if (self.outcome == "candidate_violation") != bool(self.findings):
            raise ValueError("Only candidate_violation may contain nonempty findings")
        if any(not text.strip() or len(text) > 1000 for text in self.limitations):
            raise ValueError("Limitations must be nonempty strings under 1000 characters")
        return self


class Submission(Contract):
    image_base64: str
    filename: str = Field(default="image", min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    captured_at: str | None = Field(default=None, max_length=100)


class Review(Contract):
    decision: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=2000)
    corrected_analysis: Analysis | None = None


def parse_analysis(raw: str) -> Analysis:
    """Accept JSON or a single fenced JSON object, never partial prose extraction."""
    candidate = raw.strip()
    if candidate.startswith("```json\n") and candidate.endswith("```"):
        candidate = candidate[8:-3].strip()
    elif candidate.startswith("```\n") and candidate.endswith("```"):
        candidate = candidate[4:-3].strip()
    return Analysis.model_validate(json.loads(candidate))
