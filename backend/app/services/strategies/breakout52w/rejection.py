"""Aggregate first-failure counts. Assignment lives in signal.first_failure."""

from __future__ import annotations

from .identity import FAILURE_CODES, FAILURE_LABELS


def breakdown(codes: list[str], evaluated: int) -> list[dict]:
    counts = {code: 0 for code in FAILURE_CODES}
    for code in codes:
        key = code if code in counts else "other"
        counts[key] += 1
    denom = evaluated if evaluated > 0 else 1
    rows = []
    for code in FAILURE_CODES:
        n = counts[code]
        rows.append(
            {
                "code": code,
                "label": FAILURE_LABELS[code],
                "count": n,
                "pct": round(100.0 * n / denom, 1),
                "caption": "First failure",
            }
        )
    return rows
