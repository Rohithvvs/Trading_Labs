"""Scanner results projected per recommendation engine (Production | RE-001 | RE-002).

Brownfield adapter: does not change scan scoring. Production reuses the latest
completed production scan; RE engines reuse ``recommendation_engine_decisions``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .recommendation_engine_ids import (
    PRODUCTION,
    RE_001,
    RE_002,
    normalize_recommendation_engine,
)

logger = logging.getLogger("app.scanner_engine_results")


def normalize_scanner_engine(value: str | None) -> str:
    """Accept production/re001/re002 and product labels."""
    if value is None or not str(value).strip():
        return PRODUCTION
    raw = str(value).strip()
    # Query-param friendly aliases
    key = raw.lower().replace("_", "-").replace(" ", "")
    if key in {"production", "prod", "baseline"}:
        return PRODUCTION
    if key in {"re-001", "re001", "re1"}:
        return RE_001
    if key in {"re-002", "re002", "re2"}:
        return RE_002
    return normalize_recommendation_engine(raw)


async def get_production_scanner_results(*, force: bool = False) -> dict[str, Any]:
    """Latest Production scan in analysis / ScreenerResponse shape (+ available)."""
    from ..db.scan_store import load_latest_scan

    data = await load_latest_scan()
    if not data:
        return {
            "available": False,
            "recommendation_engine": PRODUCTION,
            "message": "No completed production scan found",
        }
    return {
        "available": True,
        "recommendation_engine": PRODUCTION,
        **data,
    }


def _lab_decisions_to_screener(
    rows: list[Any],
    *,
    engine: str,
    scan_run_id: str | None,
    scanned_at: str | None,
) -> dict[str, Any]:
    """Map RE decision rows → ScreenerResponse-compatible payload for Scanner UI.

    Source of truth = Recommendation Lab Scan Comparison cohort.
    MUST include every decision: BUY, WATCH, and REJECT (never drop REJECT).
    """
    buy: list[str] = []
    watch: list[str] = []
    reject: list[str] = []
    # Full cohort for Scanner Favorites / row builder (BUY + WATCH + REJECT)
    cohort: list[str] = []
    analysis_items: list[dict[str, Any]] = []
    all_analyzed: list[dict[str, Any]] = []
    rankings: list[dict[str, Any]] = []

    # Rank BUY / WATCH / REJECT by confidence within band (matches lab comparison visibility)
    def _state(row: Any) -> str:
        raw = str(getattr(row, "recommendation_state", None) or "REJECT").strip().upper()
        if raw in {"BUY", "WATCH", "REJECT"}:
            return raw
        # Normalize lab aliases
        if raw in {"BULLISH", "LONG"}:
            return "BUY"
        if raw in {"NEUTRAL", "SIDEWAYS", "HOLD"}:
            return "WATCH"
        if raw in {"BEARISH", "SELL"}:
            return "REJECT"
        return "REJECT"

    def _conf(row: Any) -> float:
        try:
            return float(getattr(row, "confidence_score", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    ordered = sorted(
        rows,
        key=lambda r: (
            0 if _state(r) == "BUY" else 1 if _state(r) == "WATCH" else 2,
            -_conf(r),
            str(getattr(r, "symbol", "") or ""),
        ),
    )

    rank = 0
    for row in ordered:
        symbol = str(getattr(row, "symbol", "") or "").strip().upper()
        if not symbol:
            continue
        state = _state(row)
        conf = _conf(row)
        # Lab stores confidence 0–1; Scanner table multiplies in places — keep 0–1
        if conf > 1.0:
            conf = conf / 100.0
        # Score: prefer production_score when present else confidence*100 as display score
        prod_score = getattr(row, "production_score", None)
        try:
            score = float(prod_score) if prod_score is not None else round(conf * 100.0, 2)
        except (TypeError, ValueError):
            score = round(conf * 100.0, 2)

        tg = getattr(row, "trade_guidance", None) or {}
        if not isinstance(tg, dict):
            tg = {}
        stop = tg.get("stop_loss")
        t1 = tg.get("target_1")
        t2 = tg.get("target_2")
        entry_low = tg.get("entry_low")
        entry_high = tg.get("entry_high")
        try:
            rr = None
            if stop is not None and entry_high is not None and t1 is not None:
                risk = abs(float(entry_high) - float(stop))
                reward = abs(float(t1) - float(entry_high))
                rr = round(reward / risk, 2) if risk > 0 else None
        except (TypeError, ValueError):
            rr = None

        strategy = getattr(row, "strategy_name", None) or getattr(row, "strategy_family", None)
        summary = str(getattr(row, "explanation", None) or "").strip() or (
            f"{engine} {state}" + (f" · {strategy}" if strategy else "")
        )

        # Always include in full cohort (Scanner must match Lab row count)
        cohort.append(symbol)
        rank += 1
        rankings.append({"symbol": symbol, "rank": rank, "score": score})

        if state == "BUY":
            buy.append(symbol)
        elif state == "WATCH":
            watch.append(symbol)
        else:
            reject.append(symbol)

        # Analysis items for EVERY state including REJECT (Favorites table builds from these)
        # Never emit 0.0 for missing levels — paper-order pydantic uses gt=0 and rejects zeros.
        def _pos(v) -> float | None:
            try:
                if v is None:
                    return None
                f = float(v)
                return f if f > 0 else None
            except (TypeError, ValueError):
                return None

        el = _pos(entry_low)
        eh = _pos(entry_high)
        sl = _pos(stop)
        tg1 = _pos(t1)
        tg2 = _pos(t2)
        rec_id = str(getattr(row, "recommendation_id", "") or "").strip() or None
        eng_ver = str(getattr(row, "engine_version", "") or "").strip() or None
        exp_id = getattr(row, "experiment_id", None)
        exp_id = str(exp_id).strip() if exp_id else None

        trade_plans = []
        if state in {"BUY", "WATCH"} and any(v is not None for v in (el, eh, sl, tg1)):
            trade_plans.append(
                {
                    "mode": "swing",
                    "strategy_name": strategy or engine,
                    "setup_type": "lab",
                    "timeframe": "1d",
                    "bias": "long",
                    "entry_low": el,
                    "entry_high": eh,
                    "stop_loss": sl,
                    "target_1": tg1,
                    "target_2": tg2,
                    "risk_reward_ratio": rr,
                    "notes": f"Auto-mapped from {engine}",
                }
            )
        analysis_items.append(
            {
                "symbol": symbol,
                "ohlcv": [],
                "technical": [
                    {
                        "mode": "swing",
                        "signal": state.lower(),
                        "score": score,
                        "indicators": {},
                        "summary": summary[:240],
                    }
                ],
                "news_articles": [],
                "news_summary": "",
                "news_sentiment_label": "n/a",
                "news_sentiment_score": 0.0,
                "backtests": [],
                "recommendation": {
                    "action": state,
                    "confidence": conf,
                    "score": score,
                    "reasoning": {
                        "bullets": [summary[:200]] if summary else [],
                        "risk_factors": [] if state != "REJECT" else [summary[:200] or "Rejected by lab engine"],
                        "invalidation_signals": [],
                    },
                    "trade_plans": trade_plans,
                    "summary": summary[:500],
                    # Lab provenance for paper-order BUY path
                    "recommendation_id": rec_id,
                    "source_engine_id": engine,
                    "source_engine_version": eng_ver,
                    "experiment_id": exp_id,
                },
                "disclaimer": f"{engine} lab decision (advisory).",
                "trade_readiness": (
                    "Ready" if state == "BUY" else "Avoid" if state == "REJECT" else "Review manually"
                ),
                "lab_engines": {
                    engine: {
                        "engine_id": engine,
                        "recommendation_state": state,
                        "confidence_score": conf,
                        "technical_analysis": getattr(row, "technical_analysis", None),
                    }
                },
            }
        )

        matched = state in {"BUY", "WATCH"}
        all_analyzed.append(
            {
                "symbol": symbol,
                "matched": matched,
                "score": score,
                "close_price": 0.0,
                "tech_signal": state,
                "conditions": {
                    "broad_trend_eligibility": matched,
                    "hard_filters_pass": matched,
                    "core_trend_filter_pass": matched,
                    "core_momentum_filter_pass": matched,
                    "basic_liquidity_filter_pass": True,
                    "data_source_failed": False,
                    "data_quality_failed": False,
                },
                "recommendation": state,
                "confidence": conf,
                "reason": summary[:200],
                "source_engine_id": engine,
            }
        )

    completed = scanned_at
    return {
        "available": True,
        "recommendation_engine": engine,
        "scan_run_id": scan_run_id,
        "screener_name": f"{engine} Scanner",
        # Full lab cohort size (BUY+WATCH+REJECT) — must match Recommendation Lab row count
        "scanned_symbols": len(cohort),
        "data_valid_symbols": list(cohort),
        # BUY+WATCH only (eligible for trade consideration)
        "eligible_symbols": buy + watch,
        # CRITICAL: shortlisted drives Scanner Favorites rows — include REJECT so Lab and Scanner match
        "shortlisted_symbols": list(cohort),
        "buy_candidate_symbols": buy,
        "watch_candidate_symbols": watch,
        "reject_candidate_symbols": reject,
        "buy_count": len(buy),
        "watch_count": len(watch),
        "reject_count": len(reject),
        "total_count": len(cohort),
        "all_analyzed_stocks": all_analyzed,
        "matches": [a for a in all_analyzed if a.get("matched")],
        "scanned_at": completed,
        "last_scan_completed_at": completed,
        "analysis": {
            "generated_at": completed,
            "items": analysis_items,
            "rankings": {"rankings": rankings},
        },
        "data_source": f"recommendation_engine_decisions:{engine}",
        "data_warning": None,
    }


def get_lab_engine_scanner_results(db: Session, engine: str) -> dict[str, Any]:
    """Latest multi-symbol cohort for RE-001 / RE-002 as scanner payload."""
    eng = normalize_scanner_engine(engine)
    if eng not in {RE_001, RE_002}:
        eng = RE_001

    from .re001.lab_query import list_recent_scan_runs
    from .re001.persistence import list_decisions_for_scan

    recent = list_recent_scan_runs(
        db,
        limit=5,
        engine_id=eng,
        min_decisions=2,  # prefer multi-symbol cohorts
        prefer_cohorts=True,
    )
    if not recent:
        # Fall back to any single-decision runs
        recent = list_recent_scan_runs(
            db,
            limit=5,
            engine_id=eng,
            min_decisions=1,
            prefer_cohorts=True,
        )
    if not recent:
        return {
            "available": False,
            "recommendation_engine": eng,
            "message": f"No completed {eng} scan decisions found",
            "shortlisted_symbols": [],
            "buy_candidate_symbols": [],
            "watch_candidate_symbols": [],
            "all_analyzed_stocks": [],
            "scanned_symbols": 0,
        }

    scan_run_id = recent[0]["scan_run_id"]
    scanned_at = recent[0].get("latest_created_at")
    rows = list_decisions_for_scan(db, scan_run_id, engine_id=eng)
    if not rows:
        return {
            "available": False,
            "recommendation_engine": eng,
            "scan_run_id": scan_run_id,
            "message": f"No decisions for {eng} scan_run_id={scan_run_id}",
            "shortlisted_symbols": [],
            "buy_candidate_symbols": [],
            "watch_candidate_symbols": [],
            "all_analyzed_stocks": [],
            "scanned_symbols": 0,
        }
    return _lab_decisions_to_screener(
        rows,
        engine=eng,
        scan_run_id=scan_run_id,
        scanned_at=scanned_at,
    )


async def get_scanner_results_for_engine(
    db_sync: Session | None,
    engine: str | None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Unified entry: Production async store, RE engines sync decision table."""
    eng = normalize_scanner_engine(engine)
    if eng == PRODUCTION:
        return await get_production_scanner_results(force=force)
    if db_sync is None:
        return {
            "available": False,
            "recommendation_engine": eng,
            "message": "Database session required for lab engines",
        }
    return get_lab_engine_scanner_results(db_sync, eng)
