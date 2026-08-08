"""Canonical recommendation-engine identifiers for paper-trading attribution.

Used across paper positions, orders, trade history, auto paper trading, and analytics.
Values are stable product labels — do not invent aliases at call sites.
"""

from __future__ import annotations

from typing import Final, Literal

RecommendationEngineId = Literal["Production", "RE-001", "RE-002"]

PRODUCTION: Final[str] = "Production"
RE_001: Final[str] = "RE-001"
RE_002: Final[str] = "RE-002"

ALL_ENGINES: Final[tuple[str, ...]] = (PRODUCTION, RE_001, RE_002)

# Map common variants → canonical label
_ALIASES: Final[dict[str, str]] = {
    "PRODUCTION": PRODUCTION,
    "PROD": PRODUCTION,
    "BASELINE": PRODUCTION,
    "SYSTEM": PRODUCTION,
    "RE-001": RE_001,
    "RE001": RE_001,
    "RE_001": RE_001,
    "RE-002": RE_002,
    "RE002": RE_002,
    "RE_002": RE_002,
}


def normalize_recommendation_engine(value: str | None) -> str:
    """Normalize to Production | RE-001 | RE-002. Empty/None → Production."""
    if value is None:
        return PRODUCTION
    raw = str(value).strip()
    if not raw:
        return PRODUCTION
    mapped = _ALIASES.get(raw.upper())
    if mapped:
        return mapped
    # Already-canonical casing for known engines
    for eng in ALL_ENGINES:
        if raw == eng:
            return eng
    # Unknown non-empty values default to Production for paper uniqueness safety
    return PRODUCTION


def is_known_engine(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().upper() in _ALIASES or str(value).strip() in ALL_ENGINES
