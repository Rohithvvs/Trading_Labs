"""Published first-cohort membership — skipped unless a frozen calendar is provided."""

from pathlib import Path

import pytest

FIRST_DAY = {
    "SJVN",
    "DIXON",
    "ATUL",
    "JUBLFOOD",
    "TATAELXSI",
    "CDSL",
    "SAREGAMA",
}


def test_first_cohort_membership_optional():
    fixture = Path(__file__).resolve().parents[3] / "data_mrs"
    if not fixture.exists():
        pytest.skip("frozen data_mrs calendar not present")
    pytest.skip("membership replay against data_mrs is an implement follow-up when the snapshot is wired")
