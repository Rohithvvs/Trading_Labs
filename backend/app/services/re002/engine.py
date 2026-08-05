"""RE-002 Relative Strength Momentum strategy orchestration."""

from __future__ import annotations

from typing import Any

from .context import LabExecutionContext
from .confidence import score_confidence
from .eligibility import bull_stock_and_rs_prefilter, exceptional_rs_leader, _tech_score
from .portfolio_context import portfolio_blocks_buy, resolve_portfolio_snapshot
from .ranking import rank_primaries, select_primary
from .regime import is_regime_usable, map_market_regime
from .rs_features import build_rs_features, extract_sector_rs
from .strategy_config import (
    BEAR_MINIMAL_PARTICIPATION,
    REGIME_PRIMARY_PRIORITY,
    SIDEWAYS_STRICT,
    STRONG_RS_THRESHOLD,
)


def _signal_bullish(technical_results: list[Any]) -> bool:
    if not technical_results:
        return False
    t0 = technical_results[0]
    sig = str(getattr(t0, "signal", None) or (t0.get("signal") if isinstance(t0, dict) else "") or "").lower()
    return sig in {"bullish", "buy", "strong_buy"}


def _volume_expanding(candles: list[Any]) -> bool:
    if not candles or len(candles) < 25:
        return False
    try:
        vols = [float(getattr(c, "volume", None) or c["volume"]) for c in candles[-25:]]  # type: ignore[index]
    except Exception:
        return False
    recent = sum(vols[-5:]) / 5.0
    base = sum(vols[-25:-5]) / 20.0 if len(vols) >= 25 else sum(vols[:-5]) / max(len(vols) - 5, 1)
    return base > 0 and recent >= 1.1 * base


def _evaluate_primaries(
    *,
    regime: str,
    tech_score: float,
    bullish: bool,
    volume_ok: bool,
    rs: float | None,
    strict: bool,
) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]]]:
    supporting: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    qualified: list[str] = []

    if rs is not None and rs >= 0:
        supporting.append({"name": "Multi-timeframe Relative Strength", "result": "pass"})
    else:
        supporting.append({"name": "Multi-timeframe Relative Strength", "result": "weak"})

    if volume_ok:
        supporting.append({"name": "Volume confirmation of leadership", "result": "pass"})
    else:
        supporting.append({"name": "Volume confirmation of leadership", "result": "weak"})

    if rs is not None and rs >= STRONG_RS_THRESHOLD:
        supporting.append({"name": "Sector Relative Strength", "result": "pass"})
    else:
        supporting.append({"name": "Sector Relative Strength", "result": "weak"})

    if bullish:
        supporting.append({"name": "Price structure quality", "result": "pass"})
    else:
        supporting.append({"name": "Price structure quality", "result": "fail"})

    # Primaries require real RS when the family is RS-led (no tech-only substitute).
    candidates = {
        "Relative Strength Leadership": rs is not None and rs >= STRONG_RS_THRESHOLD,
        "Relative Strength Momentum Continuation": (
            tech_score >= 70 and bullish and rs is not None and rs >= 0
        ),
        "Sector Leadership Alignment": (rs is not None and rs >= STRONG_RS_THRESHOLD) and tech_score >= 65,
        "Strong RS + Trend Alignment": bullish and tech_score >= 68 and rs is not None and rs >= 0,
    }

    if regime == "Sideways" and strict:
        if candidates["Relative Strength Momentum Continuation"] and not (
            volume_ok and tech_score >= 72 and (rs is not None and rs >= STRONG_RS_THRESHOLD)
        ):
            candidates["Relative Strength Momentum Continuation"] = False
            rejected.append(
                {"name": "Relative Strength Momentum Continuation", "reason": "sideways_strict"}
            )

    for name, ok in candidates.items():
        if ok:
            qualified.append(name)
        else:
            if not any(r["name"] == name for r in rejected):
                rejected.append({"name": name, "reason": "conditions_not_met"})

    ranked = rank_primaries(qualified, regime=regime, rs=rs)
    return ranked, supporting, rejected


def evaluate_re002(ctx: LabExecutionContext) -> dict[str, Any]:
    """Core evaluate → dict suitable for Decision Object builder. Always returns a decision for the symbol."""
    reason_codes: list[str] = []
    rs_features = build_rs_features(ctx)
    regime = map_market_regime(ctx.market_regime)
    if not is_regime_usable(regime):
        reason_codes.append("missing_market_context")
        return {
            "recommendation_state": "REJECT",
            "market_regime": "UNKNOWN",
            "confidence_score": 0.0,
            "strategy_family": None,
            "strategy_name": None,
            "reason_codes": reason_codes,
            "evidence": {
                "regime": "UNKNOWN",
                "rs": rs_features,
                "eligibility": {"rs_prefilter_pass": False, "bull_stock_pass": False},
                "validation": {"market_regime": "missing"},
            },
            "explanation": "Missing or unusable market regime context.",
            "portfolio_decision": {"status": "skipped"},
            "risk_profile": {"mode": "n/a"},
            "primary_strategy": None,
            "supporting_strategies": [],
            "rejected_strategies": [],
            "evaluation_status": "rejected_by_rules",
        }

    rs = extract_sector_rs(ctx.sector_overlay)
    eligible, elig_reasons = bull_stock_and_rs_prefilter(
        candles=ctx.candles,
        technical_results=ctx.technical_results,
        sector_rs=rs,
    )

    portfolio = resolve_portfolio_snapshot(
        user_portfolio=ctx.user_portfolio,
        risk_settings=ctx.risk_settings,
    )
    port_block, port_reason = portfolio_blocks_buy(portfolio)

    tech_score = _tech_score(ctx.technical_results)
    bullish = _signal_bullish(ctx.technical_results)
    volume_ok = _volume_expanding(ctx.candles)

    if regime == "Bear" and BEAR_MINIMAL_PARTICIPATION:
        if not exceptional_rs_leader(technical_results=ctx.technical_results, sector_rs=rs):
            reason_codes.append("bear_regime_minimal_participation")
            return {
                "recommendation_state": "REJECT",
                "market_regime": regime,
                "confidence_score": min(tech_score / 100.0, 0.4),
                "strategy_family": None,
                "strategy_name": None,
                "reason_codes": reason_codes + elig_reasons,
                "evidence": {
                    "regime": regime,
                    "rs": rs_features,
                    "eligibility": {
                        "rs_prefilter_pass": eligible,
                        "bull_stock_pass": eligible,
                        "reasons": elig_reasons,
                    },
                    "validation": {
                        "market_regime": "pass",
                        "bear_exceptional_rs": "fail",
                        "leadership_quality": "fail",
                    },
                },
                "explanation": "Bear regime: only strongest RS survivors participate; not exceptional.",
                "portfolio_decision": {
                    "status": "ok" if portfolio.available else "unavailable",
                    "source": portfolio.source,
                },
                "risk_profile": {"regime": regime, "mode": "capital_preservation"},
                "primary_strategy": None,
                "supporting_strategies": [],
                "rejected_strategies": [{"name": "all_primaries", "reason": "bear_minimal"}],
                "evaluation_status": "rejected_by_rules",
            }

    if not eligible:
        # Always Decision Object REJECT — never silent skip
        mapped = []
        known = {
            "weak_relative_strength",
            "missing_relative_strength",
            "failed_bull_stock_filter",
            "insufficient_history",
        }
        for r in elig_reasons or []:
            if r in known:
                mapped.append(r)
            elif r.startswith("failed_") or r.startswith("weak_") or r.startswith("missing_"):
                mapped.append(r)
            else:
                mapped.append("failed_bull_stock_filter")
        if not mapped:
            mapped = ["failed_bull_stock_filter"]
        reason_codes.extend(mapped)
        return {
            "recommendation_state": "REJECT",
            "market_regime": regime,
            "confidence_score": min(tech_score / 100.0, 0.45),
            "strategy_family": None,
            "strategy_name": None,
            "reason_codes": reason_codes,
            "evidence": {
                "regime": regime,
                "rs": rs_features,
                "eligibility": {
                    "rs_prefilter_pass": False,
                    "bull_stock_pass": False,
                    "reasons": elig_reasons,
                },
                "validation": {"bull_stock_filter": "fail", "rs_prefilter": "fail"},
            },
            "explanation": "Failed Bull Stock + Relative Strength pre-filter.",
            "portfolio_decision": {
                "status": "ok" if portfolio.available else "unavailable",
                "source": portfolio.source,
            },
            "risk_profile": {"regime": regime},
            "primary_strategy": None,
            "supporting_strategies": [],
            "rejected_strategies": [],
            "evaluation_status": "rejected_by_rules",
        }

    ranked, supporting, rejected = _evaluate_primaries(
        regime=regime,
        tech_score=tech_score,
        bullish=bullish,
        volume_ok=volume_ok,
        rs=rs,
        strict=(regime == "Sideways" and SIDEWAYS_STRICT),
    )

    if not ranked:
        return {
            "recommendation_state": "REJECT",
            "market_regime": regime,
            "confidence_score": min(tech_score / 100.0, 0.5),
            "strategy_family": None,
            "strategy_name": None,
            "reason_codes": ["no_primary_strategy"],
            "evidence": {
                "regime": regime,
                "rs": rs_features,
                "supporting": supporting,
                "rejected": rejected,
                "eligibility": {"rs_prefilter_pass": True, "bull_stock_pass": True},
            },
            "explanation": "No primary leadership strategy qualified.",
            "portfolio_decision": {
                "status": "ok" if portfolio.available else "unavailable",
                "source": portfolio.source,
            },
            "risk_profile": {"regime": regime},
            "primary_strategy": None,
            "supporting_strategies": supporting,
            "rejected_strategies": rejected,
            "evaluation_status": "rejected_by_rules",
        }

    primary = select_primary(ranked)
    support_pass = sum(1 for s in supporting if s.get("result") == "pass")
    conf = score_confidence(
        tech_score=tech_score,
        rs=rs,
        support_pass=support_pass,
        regime=regime,
        validation_ok=not port_block,
    )

    if tech_score >= 72 and support_pass >= 2 and rs is not None and rs >= 0:
        state = "BUY"
    elif tech_score >= 55 and rs is not None:
        state = "WATCH"
    else:
        state = "REJECT"
        if rs is None:
            reason_codes.append("missing_relative_strength")
        else:
            reason_codes.append("low_technical_score")

    # Leadership quality soft check
    if state == "BUY" and rs is not None and rs < STRONG_RS_THRESHOLD and regime != "Bull":
        state = "WATCH"
        reason_codes.append("leadership_quality_failed")

    if port_block:
        if port_reason:
            reason_codes.append(port_reason)
        if state == "BUY":
            state = "WATCH"

    return {
        "recommendation_state": state,
        "market_regime": regime,
        "confidence_score": conf,
        "strategy_family": primary,
        "strategy_name": primary,
        "reason_codes": reason_codes,
        "evidence": {
            "regime": regime,
            "rs": rs_features,
            "priority_order": REGIME_PRIMARY_PRIORITY.get(regime, []),
            "qualified_primaries": ranked,
            "supporting": supporting,
            "rejected": rejected,
            "technical_score": tech_score,
            "eligibility": {"rs_prefilter_pass": True, "bull_stock_pass": True},
            "validation": {
                "market_regime": "pass",
                "bull_stock_filter": "pass",
                "rs_prefilter": "pass",
                "portfolio": "fail" if port_block else "pass",
                "liquidity": "pass" if volume_ok else "weak",
                "leadership_quality": "pass" if state != "REJECT" else "fail",
            },
        },
        "explanation": (
            f"Primary {primary} under {regime} regime; tech_score={tech_score:.1f}; "
            f"rs={rs}; state={state}."
        ),
        "portfolio_decision": {
            "status": "blocked" if port_block else "ok",
            "source": portfolio.source,
            "reason": port_reason,
        },
        "risk_profile": {"regime": regime, "mode": "rs_leadership"},
        "primary_strategy": primary,
        "supporting_strategies": supporting,
        "rejected_strategies": rejected,
        "evaluation_status": "success" if state != "REJECT" or not reason_codes else "rejected_by_rules",
    }
