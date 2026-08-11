"""RE-001 strategy orchestration — approved Trend Continuation core logic.

Decision path (core):
  mandatory gates (Keltner close breakout, RVOL>1.5, HA bullish + wick,
  RSI14>50, earnings clear)
  AND composite score > 75
  (weights: 0.35 volume / 0.30 trend / 0.20 HA / 0.15 RSI)

Production tech_score / regime support counts do NOT create BUY and cannot
override a failed mandatory gate.
"""

from __future__ import annotations

from typing import Any

from .context import LabExecutionContext
from .earnings import earnings_info_from_override, lookup_next_earnings
from .eligibility import bull_stock_filter_pass, exceptional_rs_leader, _tech_score
from .portfolio_context import portfolio_blocks_buy, resolve_portfolio_snapshot
from .regime import is_regime_usable, map_market_regime
from .strategy_config import BEAR_MINIMAL_PARTICIPATION, REGIME_PRIMARY_PRIORITY
from .technicals import COMPOSITE_BUY_THRESHOLD, build_re001_technicals


def _sector_rs(ctx: LabExecutionContext) -> float | None:
    so = ctx.sector_overlay
    if so is None:
        return None
    try:
        v = getattr(so, "sector_rs_20", None)
        if v is None and isinstance(so, dict):
            v = so.get("sector_rs_20")
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _capital_from_portfolio(portfolio: Any) -> float | None:
    try:
        cash = getattr(portfolio, "available_cash", None)
        if cash is not None and float(cash) > 0:
            return float(cash)
    except (TypeError, ValueError):
        pass
    return None


def _resolve_earnings(ctx: LabExecutionContext) -> dict[str, Any]:
    override = earnings_info_from_override(ctx.earnings_info)
    if override is not None:
        return override
    return lookup_next_earnings(ctx.symbol, as_of=ctx.scan_date)


def _gate_reason_codes(failed: list[str]) -> list[str]:
    mapping = {
        "keltner_breakout": "keltner_breakout_failed",
        "relative_volume": "relative_volume_failed",
        "ha_bullish": "ha_not_bullish",
        "ha_lower_wick": "ha_lower_wick_failed",
        "rsi": "rsi_below_threshold",
        "earnings_clear": "earnings_blackout",
    }
    return [mapping.get(f, f"gate_{f}") for f in failed]


def evaluate_re001(ctx: LabExecutionContext) -> dict[str, Any]:
    """Core evaluate → dict suitable for Decision Object builder."""
    reason_codes: list[str] = []
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
            "evidence": {"regime": "UNKNOWN", "validation": {"market_regime": "missing"}},
            "explanation": "Missing or unusable market regime context.",
            "portfolio_decision": {"status": "skipped"},
            "risk_profile": {"mode": "n/a"},
            "primary_strategy": None,
            "supporting_strategies": [],
            "rejected_strategies": [],
            "evaluation_status": "rejected_by_rules",
            "technical_analysis": {},
        }

    rs = _sector_rs(ctx)
    eligible, elig_reasons = bull_stock_filter_pass(
        candles=ctx.candles,
        technical_results=ctx.technical_results,
        sector_rs=rs,
    )

    portfolio = resolve_portfolio_snapshot(
        user_portfolio=ctx.user_portfolio,
        risk_settings=ctx.risk_settings,
    )
    port_block, port_reason = portfolio_blocks_buy(portfolio)
    capital = _capital_from_portfolio(portfolio)

    # Informational only — never drives RE-001 BUY
    prod_tech_score = _tech_score(ctx.technical_results)

    if regime == "Bear" and BEAR_MINIMAL_PARTICIPATION:
        if not exceptional_rs_leader(technical_results=ctx.technical_results, sector_rs=rs):
            reason_codes.append("bear_regime_minimal_participation")
            tech = build_re001_technicals(
                ctx.candles,
                ctx.technical_results,
                earnings_info=_resolve_earnings(ctx),
                capital=capital,
            )
            return {
                "recommendation_state": "REJECT",
                "market_regime": regime,
                "confidence_score": min(prod_tech_score / 100.0, 0.4),
                "strategy_family": None,
                "strategy_name": None,
                "reason_codes": reason_codes + elig_reasons,
                "evidence": {
                    "regime": regime,
                    "validation": {
                        "market_regime": "pass",
                        "bull_stock_filter": "fail" if not eligible else "pass",
                        "bear_exceptional_rs": "fail",
                    },
                    "production_tech_score": prod_tech_score,
                },
                "explanation": "Bear regime: ordinary continuation rejected; not an exceptional RS leader.",
                "portfolio_decision": {
                    "status": "ok" if portfolio.available else "unavailable",
                    "source": portfolio.source,
                },
                "risk_profile": {"regime": regime, "mode": "capital_preservation"},
                "primary_strategy": None,
                "supporting_strategies": [],
                "rejected_strategies": [{"name": "all_primaries", "reason": "bear_minimal"}],
                "evaluation_status": "rejected_by_rules",
                "technical_analysis": tech,
            }

    if not eligible:
        reason_codes.extend(elig_reasons or ["bull_stock_filter_failed"])
        tech = build_re001_technicals(
            ctx.candles,
            ctx.technical_results,
            earnings_info=_resolve_earnings(ctx),
            capital=capital,
        )
        return {
            "recommendation_state": "REJECT",
            "market_regime": regime,
            "confidence_score": min(prod_tech_score / 100.0, 0.45),
            "strategy_family": None,
            "strategy_name": None,
            "reason_codes": reason_codes,
            "evidence": {
                "regime": regime,
                "validation": {"bull_stock_filter": "fail", "reasons": elig_reasons},
                "production_tech_score": prod_tech_score,
            },
            "explanation": "Failed Bull Stock Filter eligibility.",
            "portfolio_decision": {
                "status": "ok" if portfolio.available else "unavailable",
                "source": portfolio.source,
            },
            "risk_profile": {"regime": regime},
            "primary_strategy": None,
            "supporting_strategies": [],
            "rejected_strategies": [],
            "evaluation_status": "rejected_by_rules",
            "technical_analysis": tech,
        }

    # ---- Core RE-001 setup evaluation (single source of truth) ----
    earnings = _resolve_earnings(ctx)
    tech = build_re001_technicals(
        ctx.candles,
        ctx.technical_results,
        earnings_info=earnings,
        capital=capital,
    )

    if tech.get("error"):
        reason_codes.append("insufficient_history" if "insufficient" in str(tech.get("error")) else "technicals_error")
        return {
            "recommendation_state": "REJECT",
            "market_regime": regime,
            "confidence_score": 0.0,
            "strategy_family": None,
            "strategy_name": None,
            "reason_codes": reason_codes,
            "evidence": {"regime": regime, "technicals_error": tech.get("error")},
            "explanation": f"RE-001 technical evaluation failed: {tech.get('error')}",
            "portfolio_decision": {
                "status": "ok" if portfolio.available else "unavailable",
                "source": portfolio.source,
            },
            "risk_profile": {"regime": regime},
            "primary_strategy": None,
            "supporting_strategies": [],
            "rejected_strategies": [],
            "evaluation_status": "rejected_by_rules",
            "technical_analysis": tech,
        }

    decision_block = tech.get("decision") or {}
    gates = tech.get("gates") or {}
    mandatory_ok = bool(tech.get("mandatory_gates_pass"))
    composite = float(tech.get("composite_score") or 0.0)
    score_ok = composite > COMPOSITE_BUY_THRESHOLD
    failed_gates = list(decision_block.get("failed_gates") or [])

    supporting: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []

    supporting.append(
        {
            "name": "Keltner Breakout",
            "result": "pass" if gates.get("keltner_breakout") else "fail",
        }
    )
    supporting.append(
        {
            "name": "Relative Volume",
            "result": "pass" if gates.get("relative_volume") else "fail",
        }
    )
    supporting.append(
        {
            "name": "Heikin-Ashi",
            "result": "pass" if gates.get("ha_bullish") and gates.get("ha_lower_wick") else "fail",
        }
    )
    supporting.append(
        {"name": "RSI14", "result": "pass" if gates.get("rsi") else "fail"}
    )
    supporting.append(
        {
            "name": "Earnings Clear",
            "result": "pass" if gates.get("earnings_clear") else "fail",
        }
    )
    if rs is not None and rs >= 0:
        supporting.append({"name": "Relative Strength", "result": "pass"})
    else:
        supporting.append({"name": "Relative Strength", "result": "weak"})

    # Primary strategy identity for explainability (Keltner breakout path)
    primary = "Breakout Continuation"
    order = REGIME_PRIMARY_PRIORITY.get(regime, REGIME_PRIMARY_PRIORITY["Sideways"])
    if primary not in order:
        primary = order[0] if order else "Trend Following"

    if not mandatory_ok:
        reason_codes.extend(_gate_reason_codes(failed_gates))
        state = "REJECT"
        conf = min(0.5, max(0.1, composite / 100.0 * 0.5))
        explanation = (
            f"RE-001 mandatory gate(s) failed: {', '.join(failed_gates) or 'unknown'}; "
            f"composite={composite:.2f}."
        )
        for g in failed_gates:
            rejected.append({"name": g, "reason": "mandatory_gate_failed"})
    elif not score_ok:
        reason_codes.append("composite_score_below_threshold")
        state = "WATCH"
        conf = min(0.7, max(0.35, composite / 100.0 * 0.85))
        explanation = (
            f"RE-001 gates passed but composite {composite:.2f} "
            f"<= {COMPOSITE_BUY_THRESHOLD} (BUY requires > {COMPOSITE_BUY_THRESHOLD})."
        )
    else:
        state = "BUY"
        conf = min(0.95, max(0.55, composite / 100.0))
        explanation = (
            f"RE-001 Trend Continuation BUY: all mandatory gates passed; "
            f"composite={composite:.2f} > {COMPOSITE_BUY_THRESHOLD}; "
            f"primary={primary} under {regime}."
        )

    # Portfolio validation may only downgrade BUY — never create BUY
    if port_block:
        if port_reason:
            reason_codes.append(port_reason)
        if state == "BUY":
            state = "WATCH"
            explanation = (
                f"{explanation} Downgraded to WATCH: portfolio validation "
                f"({port_reason or 'blocked'})."
            )

    risk = tech.get("risk") or {}
    risk_profile = {
        "regime": regime,
        "mode": "continuation",
        "entry": risk.get("entry"),
        "stop_loss": risk.get("selected_sl"),
        "take_profit": risk.get("take_profit"),
        "position_size": risk.get("position_size"),
        "risk_per_share": risk.get("risk_per_share"),
        "risk_reward": risk.get("risk_reward"),
        "breakeven_trigger": risk.get("breakeven_trigger"),
    }

    return {
        "recommendation_state": state,
        "market_regime": regime,
        "confidence_score": conf,
        "strategy_family": primary if state in {"BUY", "WATCH"} else None,
        "strategy_name": primary if state in {"BUY", "WATCH"} else None,
        "reason_codes": reason_codes,
        "evidence": {
            "regime": regime,
            "priority_order": REGIME_PRIMARY_PRIORITY.get(regime, []),
            "supporting": supporting,
            "rejected": rejected,
            "production_tech_score": prod_tech_score,
            "re001_composite_score": composite,
            "mandatory_gates": gates,
            "scoring": tech.get("scoring"),
            "validation": {
                "market_regime": "pass",
                "bull_stock_filter": "pass",
                "portfolio": "fail" if port_block else "pass",
                "keltner_breakout": "pass" if gates.get("keltner_breakout") else "fail",
                "relative_volume": "pass" if gates.get("relative_volume") else "fail",
                "ha": "pass" if gates.get("ha_bullish") and gates.get("ha_lower_wick") else "fail",
                "rsi": "pass" if gates.get("rsi") else "fail",
                "earnings": "pass" if gates.get("earnings_clear") else "fail",
                "composite": "pass" if score_ok else "fail",
            },
        },
        "explanation": explanation,
        "portfolio_decision": {
            "status": "blocked" if port_block else "ok",
            "source": portfolio.source,
            "reason": port_reason,
        },
        "risk_profile": risk_profile,
        "primary_strategy": primary if state in {"BUY", "WATCH"} else None,
        "supporting_strategies": supporting,
        "rejected_strategies": rejected,
        "evaluation_status": "success" if state != "REJECT" or not reason_codes else "rejected_by_rules",
        "technical_analysis": tech,
        "trade_guidance_payload": {
            "entry_low": risk.get("entry"),
            "entry_high": risk.get("entry"),
            "stop_loss": risk.get("selected_sl"),
            "target_1": risk.get("take_profit"),
            "risk_reward_ratio": risk.get("risk_reward"),
        }
        if risk.get("valid")
        else None,
    }
