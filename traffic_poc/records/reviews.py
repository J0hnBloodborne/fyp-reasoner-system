"""Human review entries appended to a record."""

from typing import Literal

from pydantic import Field

from traffic_poc.contract import Contract
from traffic_poc.vlm.outputs import Analysis


class Review(Contract):
    decision: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=2000)
    corrected_analysis: Analysis | None = None
