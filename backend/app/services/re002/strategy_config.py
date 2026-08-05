"""Regime strategy priority tables (RE-002 Doc 02)."""

from __future__ import annotations

PRIMARY_FAMILIES = (
    "Relative Strength Leadership",
    "Relative Strength Momentum Continuation",
    "Sector Leadership Alignment",
    "Strong RS + Trend Alignment",
)

REGIME_PRIMARY_PRIORITY: dict[str, list[str]] = {
    "Bull": [
        "Relative Strength Momentum Continuation",
        "Relative Strength Leadership",
        "Strong RS + Trend Alignment",
        "Sector Leadership Alignment",
    ],
    "Sideways": [
        "Relative Strength Leadership",
        "Sector Leadership Alignment",
        "Strong RS + Trend Alignment",
        "Relative Strength Momentum Continuation",
    ],
    "Bear": [
        "Relative Strength Leadership",
        "Sector Leadership Alignment",
        "Strong RS + Trend Alignment",
        "Relative Strength Momentum Continuation",
    ],
}

SIDEWAYS_STRICT = True
BEAR_MINIMAL_PARTICIPATION = True

# RS thresholds (see rs_defaults.md)
WEAK_RS_THRESHOLD = 0.0
STRONG_RS_THRESHOLD = 5.0
EXCEPTIONAL_RS_THRESHOLD = 8.0
