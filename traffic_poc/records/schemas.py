"""Versioned contracts shared by inference, storage, and review."""

import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


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
            raise ValueError(
                "Limitations must be nonempty strings under 1000 characters"
            )
        return self


class Observation(Contract):
    frame_index: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=500)


class Verification(Contract):
    # Evidence precedes the verdict so the model writes observations first.
    observations: list[Observation] = Field(
        max_length=12,
        description="What is visible in specific frames, including absent contact",
    )
    verdict: Literal["supported", "not_supported", "insufficient_evidence"]
    summary: str = Field(min_length=1, max_length=1500)
    limitations: list[str] = Field(max_length=12)

    @model_validator(mode="after")
    def grounded_verdict(self) -> Self:
        """A decided verdict must cite at least one frame."""
        if self.verdict != "insufficient_evidence" and not self.observations:
            raise ValueError("A decided verdict must cite frame observations")
        if any(not text.strip() or len(text) > 1000 for text in self.limitations):
            raise ValueError(
                "Limitations must be nonempty strings under 1000 characters"
            )
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


def _json_object(raw: str):
    """Accept JSON or a single fenced JSON object, never partial prose extraction."""
    candidate = raw.strip()
    if candidate.startswith("```json\n") and candidate.endswith("```"):
        candidate = candidate[8:-3].strip()
    elif candidate.startswith("```\n") and candidate.endswith("```"):
        candidate = candidate[4:-3].strip()
    return json.loads(candidate)


def parse_analysis(raw: str) -> Analysis:
    return Analysis.model_validate(_json_object(raw))


def parse_verification(raw: str, frame_indices: set[int]) -> Verification:
    """Reject observations that cite frames the model was not shown."""
    verification = Verification.model_validate(_json_object(raw))
    unknown = {item.frame_index for item in verification.observations} - frame_indices
    if unknown:
        raise ValueError(f"Observations cite frames not shown: {sorted(unknown)}")
    return verification
