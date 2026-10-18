"""Review entries require a named human reviewer."""

import pytest
from pydantic import ValidationError

from traffic_poc.records.reviews import Review


def test_review_requires_human():
    with pytest.raises(ValidationError):
        Review(decision="approved", reviewer=" ")
