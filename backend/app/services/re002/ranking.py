"""Rank candidates primarily by Relative Strength quality."""

from __future__ import annotations

from typing import Any

from .strategy_config import REGIME_PRIMARY_PRIORITY


def rank_primaries(
    qualified: list[str],
    *,
    regime: str,
    rs: float | None,
) -> list[str]:
    """Order qualified primary strategies: regime priority, then RS strength bias."""
    order = REGIME_PRIMARY_PRIORITY.get(regime, REGIME_PRIMARY_PRIORITY["Sideways"])
    sorted_q = [f for f in order if f in qualified]
    # If RS is strong, prefer pure RS leadership families first
    if rs is not None and rs >= 5.0:
        prefer = [
            "Relative Strength Leadership",
            "Relative Strength Momentum Continuation",
            "Sector Leadership Alignment",
            "Strong RS + Trend Alignment",
        ]
        prefer_sorted = [f for f in prefer if f in sorted_q]
        rest = [f for f in sorted_q if f not in prefer_sorted]
        return prefer_sorted + rest
    return sorted_q


def select_primary(ranked: list[str]) -> str | None:
    return ranked[0] if ranked else None
