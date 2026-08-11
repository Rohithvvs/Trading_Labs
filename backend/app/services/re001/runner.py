"""Isolated RE-001 runner — fail-open relative to production (async-safe)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ...config.settings import settings
from ...schemas.re001 import Re001DecisionObject
from .context import LabExecutionContext, build_lab_context
from .decision_builder import build_decision_object
from .engine import evaluate_re001
from .metrics import incr, snapshot as metrics_snapshot
from .persistence import persist_decision
from .registry import get_re001_registration, is_re001_active
from .scan_context import get_scan_run_id

logger = logging.getLogger("app.re001")


def _evaluate_sync(ctx: LabExecutionContext) -> Re001DecisionObject:
    result = evaluate_re001(ctx)
    if ctx.recommendation_backtest:
        result = dict(result)
        result["recommendation_backtest"] = ctx.recommendation_backtest
    return build_decision_object(ctx, result)


def _diagnostic_decision(
    ctx: LabExecutionContext,
    *,
    status: str,
    reason: str,
    message: str,
) -> Re001DecisionObject:
    reg = get_re001_registration()
    return Re001DecisionObject(
        recommendation_id=str(uuid.uuid4()),
        engine_id="RE-001",
        engine_version=reg.engine_version,
        market_regime="UNKNOWN",
        recommendation_state="REJECT",
        confidence_score=0.0,
        risk_profile={"mode": "diagnostic"},
        portfolio_decision={"status": "skipped"},
        evidence={"diagnostic": status, "reason": reason},
        explanation=message,
        reason_codes=[reason],
        symbol=ctx.symbol,
        scan_run_id=ctx.scan_run_id,
        analysis_history_id=ctx.analysis_history_id,
        evaluation_status=status,  # type: ignore[arg-type]
        timestamp=datetime.now(timezone.utc),
    )


def _persist_safe(
    decision: Re001DecisionObject,
    *,
    mode: str,
    db_session_factory: Any | None,
) -> None:
    if not settings.re001_persist_decisions or db_session_factory is None:
        return
    try:
        db = db_session_factory()
        try:
            row = persist_decision(db, decision, mode=mode)
            if row is not None:
                incr("persist_ok")
                # Auto paper trade on BUY — fail-open, never blocks lab path
                try:
                    state = str(getattr(decision, "recommendation_state", "") or "").upper()
                    if state == "BUY":
                        from ..auto_paper_trading_service import maybe_auto_paper_from_lab_decision

                        maybe_auto_paper_from_lab_decision(db, decision)
                except Exception as auto_exc:
                    logger.warning(
                        "RE-001 auto paper hook failed (ignored) | symbol=%s | err=%s",
                        getattr(decision, "symbol", None),
                        auto_exc,
                        exc_info=True,
                    )
            else:
                incr("persist_fail")
        finally:
            db.close()
    except Exception as exc:
        incr("persist_fail")
        logger.warning("RE-001 persist session failed | %s", exc, exc_info=True)


def _build_context(**kwargs: Any) -> LabExecutionContext:
    scan_run_id = kwargs.pop("scan_run_id", None) or get_scan_run_id()
    return build_lab_context(scan_run_id=scan_run_id, **kwargs)


async def run_re001_isolated_async(
    *,
    symbol: str,
    mode: str = "swing",
    scan_run_id: str | None = None,
    candles: list[Any] | None = None,
    technical_results: list[Any] | None = None,
    sentiment_score: float = 0.0,
    fundamental_result: Any | None = None,
    backtests: list[Any] | None = None,
    production_recommendation: Any | None = None,
    market_regime: Any | None = None,
    sector_overlay: Any | None = None,
    market_breadth_soft_score: float | None = None,
    user_portfolio: dict[str, Any] | None = None,
    risk_settings: dict[str, Any] | None = None,
    analysis_history_id: int | None = None,
    db_session_factory: Any | None = None,
    run_recommendation_backtest: bool = True,
    earnings_info: dict[str, Any] | None = None,
    eval_timeout_s: float | None = None,
    _executor: Any | None = None,
    _decision_sink: Any | None = None,
) -> Re001DecisionObject | None:
    """Async RE-001 entry: never raises into production path; does not block event loop.

    ``run_recommendation_backtest=False`` skips the 20–45s 3y backtest (used by the
    full stage-universe independent lab path so Top Set=20 scans can finish under
    600s). Technical gates + decision evaluate still run.

    Lab-path extensions (internal):
    - ``earnings_info``  — preloaded earnings blackout override (single bulk query).
    - ``eval_timeout_s`` — wall-clock evaluation timeout override (defaults to the
      ``RE001_TIMEOUT_MS`` setting). A dedicated ``_executor`` avoids the shared
      default thread pool being starved by concurrent scan work.
    - ``_decision_sink`` — batch persistence channel: ``sink.add(decision)``.
      When provided, the per-decision executor persist is skipped so the full
      universe lab path can commit rows in batches.
    """
    if not is_re001_active():
        return None

    reg = get_re001_registration()
    timeout_ms = float(getattr(settings, "re001_timeout_ms", 3000) or 3000)
    timeout_s = max(0.2, timeout_ms / 1000.0)
    if eval_timeout_s is not None and eval_timeout_s > 0:
        timeout_s = max(0.2, float(eval_timeout_s))

    def _run_cpu(fn: Any, *args: Any, **kwargs: Any) -> Any:
        if _executor is not None:
            return asyncio.get_running_loop().run_in_executor(_executor, fn, *args, **kwargs)
        return asyncio.to_thread(fn, *args, **kwargs)

    # ------------------------------------------------------------------
    # Pre-recommendation flow:
    #   technical qualification → (if qualified) 3y backtest → evaluate
    # Backtest never overrides technical NO-BUY; unqualifed skip backtest.
    # ------------------------------------------------------------------
    from ..lab_technical_precheck import precheck_re001
    from ..recommendation_backtest import (
        envelope_not_qualified,
        envelope_skipped_bulk_lab,
        run_three_year_backtest,
    )

    qualified, qual_reason, _tech_snap = await _run_cpu(
        precheck_re001,
        candles=candles or [],
        technical_results=technical_results or [],
        market_regime=market_regime,
        sector_overlay=sector_overlay,
        symbol=symbol,
        earnings_info=earnings_info,
    )

    rec_bt_dict: dict[str, Any] | None = None
    bt_for_ctx = list(backtests or [])
    if not qualified:
        env = envelope_not_qualified(symbol, "RE-001", reason=qual_reason)
        rec_bt_dict = env.to_dict()
        # Do not inject a fake scoring result
        bt_for_ctx = []
    elif not run_recommendation_backtest:
        env = envelope_skipped_bulk_lab(symbol, "RE-001")
        rec_bt_dict = env.to_dict()
        # Prefer any prefetched production backtests; else evaluate without new 3y run
        bt_for_ctx = list(backtests or [])
    else:
        env = await run_three_year_backtest(
            symbol=symbol,
            engine_id="RE-001",
            candles=candles,
            existing_backtests=backtests,
            allow_reuse=True,
        )
        rec_bt_dict = env.to_dict()
        bt_list = env.as_backtest_list()
        if bt_list:
            bt_for_ctx = bt_list
        elif backtests:
            # Keep production backtests available for context even if envelope not SUCCESS
            bt_for_ctx = list(backtests)

    ctx = _build_context(
        symbol=symbol,
        mode=mode,
        scan_run_id=scan_run_id,
        candles=candles,
        technical_results=technical_results,
        sentiment_score=sentiment_score,
        fundamental_result=fundamental_result,
        backtests=bt_for_ctx,
        production_recommendation=production_recommendation,
        market_regime=market_regime,
        sector_overlay=sector_overlay,
        market_breadth_soft_score=market_breadth_soft_score,
        user_portfolio=user_portfolio,
        risk_settings=risk_settings,
        analysis_history_id=analysis_history_id,
        recommendation_backtest=rec_bt_dict,
        earnings_info=earnings_info,
    )

    logger.info(
        "RE-001 start | symbol=%s | stage=%s | version=%s | scan_run_id=%s | analysis_history_id=%s | tech_qualified=%s | bt_status=%s",
        symbol,
        reg.stage,
        reg.engine_version,
        ctx.scan_run_id,
        ctx.analysis_history_id,
        qualified,
        (rec_bt_dict or {}).get("status"),
    )
    incr("runs")
    t0 = time.perf_counter()
    decision: Re001DecisionObject | None = None
    # Evaluation timeout is settings-driven (separate wall-clock from backtest phase above).
    try:
        decision = await asyncio.wait_for(
            _run_cpu(_evaluate_sync, ctx),
            timeout=timeout_s,
        )
        incr("success")
        state = (decision.recommendation_state or "").lower()
        if state in {"buy", "watch", "reject"}:
            incr(state)
    except TimeoutError:
        incr("timeout")
        logger.warning(
            "RE-001 timeout | symbol=%s | scan_run_id=%s | timeout_s=%.2f",
            symbol,
            ctx.scan_run_id,
            timeout_s,
        )
        decision = _diagnostic_decision(
            ctx,
            status="timeout",
            reason="re001_timeout",
            message=f"RE-001 evaluation timed out after {timeout_s:.2f}s",
        )
    except Exception as exc:
        incr("error")
        logger.warning(
            "RE-001 error | symbol=%s | scan_run_id=%s | err=%s",
            symbol,
            ctx.scan_run_id,
            exc,
            exc_info=True,
        )
        decision = _diagnostic_decision(
            ctx,
            status="error",
            reason="re001_error",
            message=f"RE-001 evaluation error: {exc}",
        )
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "RE-001 complete | symbol=%s | scan_run_id=%s | state=%s | status=%s | elapsed_ms=%.1f | metrics=%s",
            symbol,
            ctx.scan_run_id,
            getattr(decision, "recommendation_state", None),
            getattr(decision, "evaluation_status", None),
            elapsed_ms,
            metrics_snapshot(),
        )

    if decision is None:
        return None

    # Persist off the critical path — DB write + auto-paper was adding 5–10s after
    # evaluation timeout and blocking shortlist analysis concurrency.
    if _decision_sink is not None:
        try:
            _decision_sink.add(decision)
        except Exception as sink_exc:
            logger.warning(
                "RE-001 decision sink add failed | symbol=%s | err=%s",
                getattr(decision, "symbol", None),
                sink_exc,
            )
            _persist_safe(decision, mode=mode, db_session_factory=db_session_factory)
        return decision
    try:
        asyncio.get_running_loop().run_in_executor(
            None,
            lambda d=decision, m=mode, f=db_session_factory: _persist_safe(
                d, mode=m, db_session_factory=f
            ),
        )
    except Exception:
        _persist_safe(decision, mode=mode, db_session_factory=db_session_factory)
    return decision


def run_re001_isolated(**kwargs: Any) -> Re001DecisionObject | None:
    """Sync wrapper for tests/scripts. Prefer run_re001_isolated_async in async code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # Called from async context incorrectly — still fail-open via thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(lambda: asyncio.run(run_re001_isolated_async(**kwargs)))
            try:
                return fut.result(timeout=max(1.0, float(getattr(settings, "re001_timeout_ms", 3000) or 3000) / 1000.0 + 1.0))
            except Exception as exc:
                logger.warning("RE-001 sync-wrapper failed | %s", exc, exc_info=True)
                return None
    return asyncio.run(run_re001_isolated_async(**kwargs))
