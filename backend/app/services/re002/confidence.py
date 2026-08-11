"""Confidence scoring for RE-002."""

from __future__ import annotations



def score_confidence(
    *,
    tech_score: float,
    rs: float | None,
    support_pass: int,
    regime: str,
    validation_ok: bool,
) -> float:
    base = tech_score / 100.0 * 0.45
    rs_comp = 0.0
    if rs is not None:
        # Map RS roughly into 0..0.35
        rs_comp = max(0.0, min(0.35, (rs + 5.0) / 40.0))
    support = min(0.25, support_pass * 0.08)
    regime_boost = 0.05 if regime == "Bull" else (0.0 if regime == "Sideways" else -0.05)
    conf = base + rs_comp + support + regime_boost
    if not validation_ok:
        conf = min(conf, 0.55)
    return max(0.0, min(0.95, conf))
