"""Build RE-002 Decision Object from engine output + context."""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from ...schemas.re001 import TradeGuidance
from ...schemas.re002 import Re002DecisionObject
from .context import LabExecutionContext
from .decision_validator import coerce_state_for_reasons, validate_decision_object
from .registry import get_re002_registration
from .technicals import build_re002_technicals

logger = logging.getLogger("app.re002")


def _clamp_confidence(raw: Any) -> float:
    try:
        conf = float(raw if raw is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(conf) or math.isinf(conf):
        return 0.0
    return max(0.0, min(1.0, conf))


def _trade_guidance_from_production(prod: Any | None) -> TradeGuidance | None:
    if prod is None:
        return None
    plans = getattr(prod, "trade_plans", None) or (
        prod.get("trade_plans") if isinstance(prod, dict) else None
    )
    if not plans:
        return None
    p0 = plans[0]
    try:
        entry_low = float(getattr(p0, "entry_low", None) or p0.get("entry_low") or 0)  # type: ignore[union-attr]
        entry_high = float(getattr(p0, "entry_high", None) or p0.get("entry_high") or 0)  # type: ignore[union-attr]
        stop_loss = float(getattr(p0, "stop_loss", None) or p0.get("stop_loss") or 0)  # type: ignore[union-attr]
        target_1 = float(getattr(p0, "target_1", None) or p0.get("target_1") or 0)  # type: ignore[union-attr]
        rr = getattr(p0, "risk_reward_ratio", None)
        if rr is None and isinstance(p0, dict):
            rr = p0.get("risk_reward_ratio")
        complete = entry_low > 0 and entry_high >= entry_low and stop_loss > 0 and target_1 > 0
        return TradeGuidance(
            entry_low=entry_low or None,
            entry_high=entry_high or None,
            stop_loss=stop_loss or None,
            target_1=target_1 or None,
            risk_reward_ratio=float(rr) if rr is not None else None,
            complete=complete,
        )
    except Exception as exc:
        logger.debug("RE-002 trade guidance parse skipped | %s", exc)
        return None


def build_decision_object(
    ctx: LabExecutionContext,
    engine_result: dict[str, Any],
) -> Re002DecisionObject:
    reg = get_re002_registration()
    reasons = list(engine_result.get("reason_codes") or [])
    state = str(engine_result.get("recommendation_state") or "REJECT")
    if state not in {"BUY", "WATCH", "REJECT"}:
        state = "REJECT"
    state = coerce_state_for_reasons(state, reasons)  # type: ignore[arg-type]

    prod = ctx.production_recommendation
    prod_action = None
    prod_score = None
    if prod is not None:
        prod_action = str(
            getattr(prod, "action", None)
            or (prod.get("action") if isinstance(prod, dict) else None)
            or ""
        )
        try:
            prod_score = float(
                getattr(prod, "score", None)
                if not isinstance(prod, dict)
                else prod.get("score")
            )
            if prod_score is not None and (math.isnan(prod_score) or math.isinf(prod_score)):
                prod_score = None
        except (TypeError, ValueError):
            prod_score = None

    # FR-015 MVP: RE-002 does not invent native levels; prefer production trade_plans
    # when complete so operator paper prefill has usable guidance + RE-002 provenance.
    guidance = _trade_guidance_from_production(prod)
    mismatch = None
    if prod_action:
        mismatch = prod_action.upper() != state

    evidence = dict(engine_result.get("evidence") or {})
    evidence["strategy_trace"] = {
        "primary_strategy": engine_result.get("primary_strategy"),
        "supporting_strategies": engine_result.get("supporting_strategies") or [],
        "rejected_strategies": engine_result.get("rejected_strategies") or [],
        "regime_bucket": engine_result.get("market_regime"),
    }

    rec_bt = ctx.recommendation_backtest or engine_result.get("recommendation_backtest")
    if rec_bt:
        evidence["recommendation_backtest"] = rec_bt
        if rec_bt.get("backtest_score") is not None:
            evidence["backtest_score"] = rec_bt.get("backtest_score")
        evidence["backtest_status"] = rec_bt.get("status") or rec_bt.get("backtest_status")
        evidence.setdefault(
            "score_separation",
            {
                "technical_score": evidence.get("technical_score")
                or evidence.get("rs", {}).get("technical_score"),
                "backtest_score": evidence.get("backtest_score"),
                "note": "Technical and backtest scores are independent; backtest cannot create BUY.",
            },
        )

    conf = _clamp_confidence(engine_result.get("confidence_score"))
    if (
        rec_bt
        and rec_bt.get("score_eligible")
        and rec_bt.get("backtest_score") is not None
        and state in {"BUY", "WATCH"}
    ):
        try:
            bt_part = max(0.0, min(1.0, float(rec_bt["backtest_score"]) / 100.0))
            conf = _clamp_confidence(conf * 0.75 + bt_part * 0.25)
        except (TypeError, ValueError):
            pass
    symbol = str(ctx.symbol or "").strip().upper() or None
    experiment_id = ctx.experiment_id or reg.experiment_id

    market_regime_dict = (
        ctx.market_regime.model_dump()
        if ctx.market_regime is not None and hasattr(ctx.market_regime, "model_dump")
        else (ctx.market_regime if isinstance(ctx.market_regime, dict) else {})
    )
    sector_overlay_dict = (
        ctx.sector_overlay.model_dump()
        if ctx.sector_overlay is not None and hasattr(ctx.sector_overlay, "model_dump")
        else (ctx.sector_overlay if isinstance(ctx.sector_overlay, dict) else {})
    )
    # Prefer technicals computed in engine_result when present (single source); else build here.
    tech_analysis = engine_result.get("technical_analysis")
    if not tech_analysis:
        tech_analysis = build_re002_technicals(
            ctx.candles,
            sector_overlay_dict,
            market_regime_dict,
            benchmark_candles=list(ctx.benchmark_candles or []),
            benchmark_symbol=ctx.benchmark_symbol,
            symbol=ctx.symbol,
            earnings_info=ctx.earnings_info,
            as_of=ctx.scan_date,
        )

    obj = Re002DecisionObject(
        recommendation_id=str(uuid.uuid4()),
        engine_id="RE-002",
        engine_version=reg.engine_version,
        experiment_id=experiment_id,
        market_regime=engine_result.get("market_regime") or "UNKNOWN",  # type: ignore[arg-type]
        trading_objective="relative_strength_leadership",
        trading_style="long_only_swing",
        strategy_family=engine_result.get("strategy_family"),
        strategy_name=engine_result.get("strategy_name"),
        recommendation_state=state,  # type: ignore[arg-type]
        confidence_score=conf,
        risk_profile=engine_result.get("risk_profile") or {},
        portfolio_decision=engine_result.get("portfolio_decision") or {},
        evidence=evidence,
        technical_analysis=tech_analysis,
        explanation=str(engine_result.get("explanation") or ""),
        timestamp=datetime.now(timezone.utc),
        reason_codes=reasons,
        trade_guidance=guidance,
        production_action=prod_action or None,
        production_score=prod_score,
        is_mismatch=mismatch,
        symbol=symbol,
        scan_run_id=ctx.scan_run_id,
        analysis_history_id=ctx.analysis_history_id,
        evaluation_status=engine_result.get("evaluation_status") or "success",  # type: ignore[arg-type]
    )

    ok, errs = validate_decision_object(obj)
    if not ok and obj.recommendation_state == "BUY":
        obj.recommendation_state = "REJECT"
        obj.reason_codes = list(obj.reason_codes) + ["validation_failed"] + errs
        obj.evaluation_status = "rejected_by_rules"
    return obj
