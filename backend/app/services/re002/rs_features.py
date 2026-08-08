"""RS feature assembly from shared sector overlay / TA inputs.

Honesty rules (FR-024 / FR-011):
- Never invent RS ranks or RS scores when inputs are missing.
- Proxies are labeled incomplete and must not be treated as real RS.
"""

from __future__ import annotations

from typing import Any

from .context import LabExecutionContext


def _tech_score(technical_results: list[Any]) -> float:
    if not technical_results:
        return 0.0
    t0 = technical_results[0]
    try:
        return float(getattr(t0, "score", None) or t0.get("score") or 0.0)  # type: ignore[union-attr]
    except Exception:
        return 0.0


def extract_sector_rs(sector_overlay: Any | None) -> float | None:
    """Extract relative-strength 20d value from sector overlay.

    Prefers ``sector_rs_20``. If null but both ROC legs are present, recompute
    the difference so a partially filled overlay still reaches RE-002.
    Does not invent values from technical scores.
    """
    if sector_overlay is None:
        return None
    try:
        def _get(name: str):
            if isinstance(sector_overlay, dict):
                return sector_overlay.get(name)
            return getattr(sector_overlay, name, None)

        v = _get("sector_rs_20")
        if v is not None:
            return float(v)
        sector_roc = _get("sector_roc20")
        nifty_roc = _get("nifty50_roc20")
        if sector_roc is not None and nifty_roc is not None:
            return float(sector_roc) - float(nifty_roc)
        return None
    except (TypeError, ValueError):
        return None


def build_rs_features(ctx: LabExecutionContext) -> dict[str, Any]:
    """Assemble RS-related evidence from shared services (no private market-data stack)."""
    rs = extract_sector_rs(ctx.sector_overlay)
    tech = _tech_score(ctx.technical_results)

    # Real RS only — never fabricate rs_vs_market or leadership_rank from tech score.
    rs_vs_market = rs  # may be None
    rs_vs_sector = rs
    leadership_rank = None
    if rs is not None:
        if rs >= 10:
            leadership_rank = 1
        elif rs >= 5:
            leadership_rank = 2
        elif rs >= 0:
            leadership_rank = 3
        else:
            leadership_rank = 5

    multi_tf: dict[str, Any] = {
        "available": False,
        "status": "incomplete",
        "note": "Multi-timeframe RS not assembled from a dedicated RS service in MVP",
    }
    # Technical score is supporting context only — not an RS substitute.
    multi_tf["supporting_technical_score"] = tech

    return {
        "rs_vs_market": rs_vs_market,
        "rs_vs_sector": rs_vs_sector,
        "multi_timeframe_rs": multi_tf,
        "rs_persistence": "unknown",
        "rs_persistence_status": "incomplete",
        "leadership_rank": leadership_rank,
        "technical_score": tech,
        "sector_rs_20": rs,
        "rs_available": rs is not None,
        "evidence_completeness": "complete" if rs is not None else "incomplete_missing_rs",
    }
