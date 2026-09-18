"""LTM scan orchestrator: freshness → evaluate → book replay → publish."""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from ....config.settings import settings
from ....db.session import AsyncSessionLocal
from ....models.market_data import HistoricalCandle
from ....models.strategy_market_data import DailyOhlcv, IndexOhlcv
from ....services.lock_service import DistributedLockService
from ....services.market_data_ingestion.freshness import evaluate_freshness
from ....services.market_data_ingestion.repository import (
    extend_scan_statement_timeout,
    fetch_daily_ohlcv_for_symbols,
    iter_symbol_chunks,
)
from ....services.universe_service import UniverseService
from ....utils.symbol import canonical_symbol
from . import persistence
from .attribution import apply_windowed_attribution, build_boards, empty_backtest, per_name_backtests
from .book_engine import BookState, evaluate_session, replay_book, snapshot_open_trades
from .identity import (
    ATTRIBUTION_YEARS,
    CACHE_KEY_LATEST,
    DEFAULT_CAPITAL,
    DEFAULT_MODE,
    DISPLAY_NAME,
    LOCK_NAME,
    RESEARCH_BPS,
    SHORT_NAME,
    STRATEGY_ID,
)
from .rejection import breakdown

logger = logging.getLogger("app.strategies.ltm.scan")


def _pos(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or n <= 0:
        return None
    return n


def published_trade_levels(*, signal: str, close_t: Any) -> dict[str, float | None]:
    """LTM is buy-and-hold: publish signal-close entry, never invent SL/target."""
    if signal not in {"BUY", "WATCH"}:
        return {"entry": None, "stop_loss": None, "target": None, "risk_reward": None}
    return {
        "entry": _pos(close_t),
        "stop_loss": None,
        "target": None,
        "risk_reward": None,
    }

LIMITATIONS = [
    "Published historical numbers may be survivorship-biased if only the current NIFTY 500 list is available.",
    "Signal-close replay assumes you trade the close just used to rank (look-ahead vs a live trader).",
    "No stop-loss: a name can lose most of its value inside the year.",
    "Ten-name concentration with no sector cap.",
    "Full annual turnover even when a name remains a leader.",
    "Past compounded growth is not a forecast.",
]


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _trade_dict(tr) -> dict[str, Any]:
    return {
        "symbol": canonical_symbol(tr.symbol),
        "entry_date": tr.entry_date.isoformat(),
        "exit_date": tr.exit_date.isoformat() if tr.exit_date else None,
        "entry_price": tr.entry_price,
        "exit_price": tr.exit_price,
        "shares": tr.shares,
        "pnl_pct": tr.pnl_pct,
        "reason": tr.reason,
        "open": tr.open,
    }


def _as_session_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


async def _load_matrix_from_strategy(symbols: list[str]) -> tuple[list[date], dict[str, dict[date, float]], dict[date, float]]:
    rows = await fetch_daily_ohlcv_for_symbols(
        symbols,
        columns=(DailyOhlcv.trade_date, DailyOhlcv.symbol, DailyOhlcv.close),
    )
    async with AsyncSessionLocal() as db:
        idx_stmt = (
            select(IndexOhlcv.trade_date, IndexOhlcv.close)
            .where(IndexOhlcv.symbol == settings.strategy_index_store_symbol)
        )
        idx_rows = (await db.execute(idx_stmt)).all()

    matrix: dict[str, dict[date, float]] = defaultdict(dict)
    dates_set: set[date] = set()
    for trade_date, symbol, close in rows:
        matrix[symbol][trade_date] = float(close)
        dates_set.add(trade_date)
    index = {d: float(c) for d, c in idx_rows}
    dates = sorted(index.keys()) if index else sorted(dates_set)
    return dates, dict(matrix), index


async def _load_matrix_from_historical_candles(
    symbols: list[str],
) -> tuple[list[date], dict[str, dict[date, float]], dict[date, float]]:
    """Fallback when strategy-grade daily_ohlcv is empty (Production candle store)."""
    rows: list[Any] = []
    async with AsyncSessionLocal() as db:
        await extend_scan_statement_timeout(db)
        for chunk in iter_symbol_chunks(symbols):
            stmt = select(
                HistoricalCandle.timestamp,
                HistoricalCandle.symbol,
                HistoricalCandle.close,
            ).where(
                HistoricalCandle.symbol.in_(chunk),
                HistoricalCandle.resolution.in_(("1D", "D", "1d")),
            )
            rows.extend((await db.execute(stmt)).all())

    matrix: dict[str, dict[date, float]] = defaultdict(dict)
    dates_set: set[date] = set()
    for ts, symbol, close in rows:
        session = _as_session_date(ts)
        matrix[symbol][session] = float(close)
        dates_set.add(session)
    return sorted(dates_set), dict(matrix), {}


async def _load_matrix(symbols: list[str]) -> tuple[list[date], dict[str, dict[date, float]], dict[date, float], str]:
    dates, matrix, index = await _load_matrix_from_strategy(symbols)
    source = "daily_ohlcv"
    if len(dates) < 253:
        fb_dates, fb_matrix, fb_index = await _load_matrix_from_historical_candles(symbols)
        if len(fb_dates) > len(dates):
            logger.warning(
                "LTM using historical_candles fallback | strategy_sessions=%s | candle_sessions=%s",
                len(dates),
                len(fb_dates),
            )
            dates, matrix, index = fb_dates, fb_matrix, fb_index or index
            source = "historical_candles"
    return dates, matrix, index, source


def _history_valid(matrix: dict[str, dict[date, float]], dates: list[date], sym: str, t_idx: int) -> bool:
    if t_idx < 252:
        return False
    series = matrix.get(sym, {})
    return dates[t_idx] in series and dates[t_idx - 252] in series


def _book_metrics(equity_curve: list[dict[str, Any]], index: dict[date, float], initial: float) -> dict[str, Any]:
    if not equity_curve:
        return {}
    eq = [p["equity"] for p in equity_curve]
    final = eq[-1]
    total_return = final / initial - 1.0 if initial else 0.0
    start_d = date.fromisoformat(equity_curve[0]["date"])
    end_d = date.fromisoformat(equity_curve[-1]["date"])
    days = max((end_d - start_d).days, 1)
    cagr = (final / initial) ** (365.25 / days) - 1.0 if initial and final > 0 else 0.0
    peak = eq[0]
    max_dd = 0.0
    for v in eq:
        peak = max(peak, v)
        if peak:
            max_dd = min(max_dd, v / peak - 1.0)
    calmar = (cagr / abs(max_dd)) if max_dd < 0 else None
    idx_vals = []
    for p in equity_curve:
        d = date.fromisoformat(p["date"])
        if d in index:
            idx_vals.append(index[d])
    bench_ret = None
    if len(idx_vals) >= 2 and idx_vals[0]:
        bench_ret = idx_vals[-1] / idx_vals[0] - 1.0
    invested = sum(1 for p in equity_curve if p.get("equity", 0) > p.get("cash", 0) + 1)
    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_dd": max_dd,
        "calmar": calmar,
        "exposure": invested / len(equity_curve) if equity_curve else 0.0,
        "excess_vs_nifty500": (total_return - bench_ret) if bench_ret is not None else None,
        "ending_equity": final,
        "initial_capital": initial,
    }


def build_payload(
    *,
    scan_id: str,
    evaluation_date: date,
    ev: dict[str, Any],
    replay: dict[str, Any],
    dates: list[date],
    matrix: dict[str, dict[date, float]],
    index: dict[date, float],
    universe: set[str],
    mode: str,
    survivorship_biased: bool,
    initial_capital: float,
    company_name_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    t_idx = len(dates) - 1
    prices = {s: matrix.get(s, {}).get(evaluation_date) for s in universe}
    state: BookState = replay["state"]
    open_tr = snapshot_open_trades(state, prices, evaluation_date)
    all_trades = list(replay["trades"]) + open_tr
    history_valid = {s for s in universe if _history_valid(matrix, dates, s, t_idx)}
    reports = per_name_backtests(
        all_trades, asof=evaluation_date, years=ATTRIBUTION_YEARS, history_valid=history_valid
    )

    signals = {row["symbol"]: row["signal"] for row in ev["rows"]}
    recs = []
    if company_name_map is None:
        try:
            company_name_map = UniverseService.get_company_name_map_sync()
        except Exception:
            company_name_map = {}

    fail_codes: list[str] = []
    data_valid = 0
    evaluated = 0
    data_failures = 0
    for row in ev["rows"]:
        sym = row["symbol"]
        canon_sym = canonical_symbol(sym)
        comp_name = company_name_map.get(canon_sym) or company_name_map.get(sym)
        hv = sym in history_valid
        if row.get("data_source_failed"):
            data_failures += 1
        if row.get("close_t") is not None:
            data_valid += 1
        evaluated += 1
        if row["first_failure"]:
            fail_codes.append(row["first_failure"])
        bt = reports.get(sym) if hv else None
        if hv and bt is None:
            bt = empty_backtest(evaluation_date, years=ATTRIBUTION_YEARS)
        levels = published_trade_levels(signal=row["signal"], close_t=row.get("close_t"))
        recs.append(
            {
                "rank": row.get("eligible_rank"),
                "symbol": canon_sym,
                "company_name": comp_name,
                "signal": row["signal"],
                "momentum_252": row.get("momentum_252"),
                "score_kind": "momentum_252",
                "gate_pass": bool(row.get("momentum_252") is not None and (row["momentum_252"] or 0) > 0.50),
                "selected": row["selected"],
                "first_failure": row["first_failure"],
                "entry": levels["entry"],
                "stop_loss": levels["stop_loss"],
                "target": levels["target"],
                "risk_reward": levels["risk_reward"],
                "target_weight": (1.0 / len(ev["selected"])) if ev["selected"] and row["selected"] else None,
                "technicals": {
                    "momentum_252": row.get("momentum_252"),
                    "close_t": row.get("close_t"),
                    "close_t_minus_252": row.get("close_t_minus_252"),
                    "rank_among_eligible": row.get("eligible_rank"),
                    "gate_pass": bool(row.get("momentum_252") is not None and (row["momentum_252"] or 0) > 0.50),
                    "selected": row["selected"],
                    "clock_status": ev["clock_status"],
                    "sessions_to_rebalance": ev["sessions_to_rebalance"],
                    "hard_filters_pass": row["first_failure"] is None or row["first_failure"] == "ranked_outside_top_10" or row["selected"],
                },
                "backtest_1y": None
                if not hv
                else {
                    "window_start": bt["window_start"],
                    "window_end": bt["window_end"],
                    "trade_count": bt["trade_count"],
                    "net_return": bt["net_return"],
                    "win_rate": bt["win_rate"],
                    "max_drawdown": bt["max_drawdown"],
                    "profit_factor": bt["profit_factor"] if bt.get("profit_factor") != float("inf") else None,
                    "never_selected_in_window": bt["never_selected_in_window"],
                    "trades": [_trade_dict(t) for t in bt.get("trades") or []],
                },
            }
        )

    recs.sort(key=lambda r: (0 if r["signal"] == "BUY" else 1 if r["signal"] == "WATCH" else 2, r["rank"] or 10_000, r["symbol"]))
    buy = [r["symbol"] for r in recs if r["signal"] == "BUY"]
    watch = [r["symbol"] for r in recs if r["signal"] == "WATCH"]
    reject_n = sum(1 for r in recs if r["signal"] == "REJECT")
    top5, least5 = build_boards(reports, signals, company_names=company_name_map)
    holdings = [
        {
            "symbol": canonical_symbol(h.symbol),
            "company_name": company_name_map.get(canonical_symbol(h.symbol)),
            "shares": h.shares,
            "avg_cost": h.avg_cost,
            "mark": prices.get(h.symbol),
            "unrealized_pct": ((prices[h.symbol] / h.avg_cost - 1.0) if prices.get(h.symbol) and h.avg_cost else None),
        }
        for h in state.holdings.values()
    ]
    last_cohort = replay["cohorts"][-1] if replay["cohorts"] else None
    payload = {
        "strategy_id": STRATEGY_ID,
        "display_name": DISPLAY_NAME,
        "short_name": SHORT_NAME,
        "scan_id": scan_id,
        "status": "completed",
        "recommendations_final": True,
        "evaluation_date": evaluation_date.isoformat(),
        "clock_status": ev["clock_status"],
        "sessions_to_rebalance": ev["sessions_to_rebalance"],
        "last_rebalance_date": _iso(state.last_rebalance_date),
        "next_rebalance_estimate": None,
        "survivorship_biased": survivorship_biased,
        "warmup": ev["clock_status"] == "WARMUP",
        "mode": mode,
        "fill_model": "signal_close",
        "summary": {
            "total": len(recs),
            "data_valid": data_valid,
            "evaluated": evaluated,
            "final_candidates": len(ev["selected"]),
            "buy": len(buy),
            "watch": len(watch),
            "reject": reject_n,
            "data_failures": data_failures,
        },
        "rejection_breakdown": breakdown(fail_codes, evaluated),
        "recommendations": recs,
        "buy_candidate_symbols": buy,
        "watch_candidate_symbols": watch,
        "exits": (last_cohort or {}).get("exits") or [],
        "entries": (last_cohort or {}).get("entries") or [],
        "holdings": holdings,
        "top5_positive": top5,
        "least5": least5,
        "book_metrics": _book_metrics(replay["equity_curve"], index, initial_capital),
        "equity_curve": replay["equity_curve"],
        "blotter": [_trade_dict(t) for t in all_trades],
        "index_curve": [{"date": d.isoformat(), "close": float(c)} for d, c in sorted(index.items())],
        "initial_capital": initial_capital,
        "limitations": LIMITATIONS,
    }
    return apply_windowed_attribution(payload, years=ATTRIBUTION_YEARS)


async def run_scan(*, mode: str | None = None, progress_cb=None, scan_id: uuid.UUID | None = None) -> dict[str, Any]:
    mode_u = (mode or settings.ltm_default_mode or DEFAULT_MODE).upper()
    capital = float(settings.ltm_initial_capital or DEFAULT_CAPITAL)
    lock = DistributedLockService(settings.ltm_lock_name or LOCK_NAME, ttl_seconds=3600)
    got = await lock.acquire(timeout_seconds=2)
    if not got:
        if scan_id is not None:
            latest = await persistence.load_latest(STRATEGY_ID)
            await persistence.update_run(
                scan_id, status="failed", error_code="LTM_SCAN_IN_PROGRESS", finished=True
            )
            if latest is None or latest.scan_id == scan_id:
                await persistence.save_latest(
                    STRATEGY_ID,
                    scan_id=scan_id,
                    status="failed",
                    payload={"error_code": "LTM_SCAN_IN_PROGRESS", "recommendations_final": False},
                    error_code="LTM_SCAN_IN_PROGRESS",
                )
        return {"error_code": "LTM_SCAN_IN_PROGRESS", "status": "failed"}

    if scan_id is None:
        run = await persistence.create_run(STRATEGY_ID)
        scan_id = run.scan_id

    async def stage(name: str, pct: int, status: str, **progress_meta: Any) -> None:
        await persistence.update_run(
            scan_id, status=status, stage=name, progress_pct=pct, progress_meta=progress_meta or None
        )
        await persistence.save_latest(
            STRATEGY_ID,
            scan_id=scan_id,
            status=status,
            payload={"scan_id": str(scan_id), "status": status, "recommendations_final": False, "stage": name},
        )
        if progress_cb:
            await progress_cb({"stage": name, "progress": pct, "scan_id": str(scan_id), **progress_meta})

    try:
        await stage("evaluating", 5, "evaluating")
        symbols = await UniverseService.get_active_nifty500_symbols()
        from .candle_backfill import ensure_strategy_daily_ready

        await ensure_strategy_daily_ready(symbols, min_sessions=253)
        fresh = await evaluate_freshness(active_symbols=symbols)
        if settings.is_strategy_market_data_gate_enabled() and not fresh.ok:
            payload = {"error_code": "MARKET_DATA_STALE", **fresh.to_dict(), "recommendations_final": False}
            await persistence.update_run(
                scan_id, status="blocked_stale", error_code="MARKET_DATA_STALE", payload=payload, finished=True
            )
            await persistence.save_latest(
                STRATEGY_ID, scan_id=scan_id, status="blocked_stale", payload=payload, error_code="MARKET_DATA_STALE"
            )
            return payload

        universe = set(symbols)
        dates, matrix, index, data_source = await _load_matrix(symbols)
        if len(dates) < 253:
            payload = {
                "error_code": "LTM_INSUFFICIENT_DATA",
                "status": "failed",
                "message": (
                    f"Need at least 253 daily sessions to compute 252-session momentum; "
                    f"found {len(dates)} in {data_source}."
                ),
                "recommendations_final": False,
            }
            await persistence.update_run(scan_id, status="failed", error_code="LTM_INSUFFICIENT_DATA", payload=payload, finished=True)
            await persistence.save_latest(STRATEGY_ID, scan_id=scan_id, status="failed", payload=payload)
            return payload

        t_idx = len(dates) - 1
        evaluation_date = dates[t_idx]
        prev_idx = t_idx - 252
        closes_t: dict[str, float | None] = {}
        closes_prev: dict[str, float | None] = {}
        symbols_list = sorted(universe)
        total = len(symbols_list)
        for i, symbol in enumerate(symbols_list, 1):
            closes_t[symbol] = matrix.get(symbol, {}).get(evaluation_date)
            closes_prev[symbol] = matrix.get(symbol, {}).get(dates[prev_idx]) if prev_idx >= 0 else None
            if i == 1 or i == total or i % 20 == 0:
                pct = 8 + int(28 * i / max(total, 1))
                await persistence.update_run(
                    scan_id,
                    status="evaluating",
                    stage="evaluating",
                    progress_pct=min(pct, 38),
                    progress_meta={
                        "current_symbol": symbol,
                        "processed_count": i,
                        "total_count": total,
                    },
                )

        await stage("backtesting", 40, "backtesting")
        replay = replay_book(
            dates,
            matrix,
            universe,
            mode=mode_u,
            initial_capital=capital,
            bps=RESEARCH_BPS,
            whole_shares=False,
        )
        st_pre = replay["state"]
        last_for_eval = st_pre.last_rebalance_index
        if st_pre.last_rebalance_date == evaluation_date and last_for_eval is not None:
            last_for_eval = last_for_eval - 252 if last_for_eval >= 252 else None
        ev = evaluate_session(
            session_index=t_idx,
            last_rebalance_index=last_for_eval,
            closes_t=closes_t,
            closes_t_minus_252=closes_prev,
            universe=universe,
        )

        await stage("publishing", 85, "publishing")
        payload = _json_safe(build_payload(
            scan_id=str(scan_id),
            evaluation_date=evaluation_date,
            ev=ev,
            replay=replay,
            dates=dates,
            matrix=matrix,
            index=index,
            universe=universe,
            mode=mode_u,
            survivorship_biased=True,
            initial_capital=capital,
        ))
        payload["data_source"] = data_source
        st = replay["state"]
        await persistence.save_book_state(
            cash=st.cash,
            equity=replay["equity_curve"][-1]["equity"] if replay["equity_curve"] else st.cash,
            session_index=st.session_index,
            last_rebalance_index=st.last_rebalance_index,
            last_rebalance_date=st.last_rebalance_date,
            clock_status=ev["clock_status"],
            holdings=[
                {
                    "symbol": h.symbol,
                    "shares": h.shares,
                    "avg_cost": h.avg_cost,
                    "entry_date": h.entry_date.isoformat(),
                    "entry_session_index": h.entry_session_index,
                }
                for h in st.holdings.values()
            ],
            mode=mode_u,
            survivorship_biased=True,
            initial_capital=capital,
        )
        await persistence.update_run(scan_id, status="completed", stage="completed", progress_pct=100, payload=payload, finished=True)
        await persistence.save_latest(STRATEGY_ID, scan_id=scan_id, status="completed", payload=payload)
        logger.info("LTM scan completed scan_id=%s selected=%s", scan_id, len(ev["selected"]))
        return payload
    except Exception as exc:
        logger.exception("LTM scan failed")
        payload = {"error_code": "LTM_SCAN_FAILED", "status": "failed", "detail": str(exc), "recommendations_final": False}
        await persistence.update_run(scan_id, status="failed", error_code="LTM_SCAN_FAILED", error_detail=str(exc), payload=payload, finished=True)
        await persistence.save_latest(STRATEGY_ID, scan_id=scan_id, status="failed", payload=payload, error_code="LTM_SCAN_FAILED")
        return payload
    finally:
        await lock.release()


async def start_scan_background(mode: str | None = None) -> dict[str, Any]:
    active = await persistence.find_active_run()
    if active:
        return {"error_code": "LTM_SCAN_IN_PROGRESS", "scan_id": str(active.scan_id), "status": active.status}

    run = await persistence.create_run(STRATEGY_ID)
    await persistence.save_latest(
        STRATEGY_ID,
        scan_id=run.scan_id,
        status="queued",
        payload={
            "scan_id": str(run.scan_id),
            "status": "queued",
            "recommendations_final": False,
            "stage": "queued",
        },
    )

    import asyncio

    async def _runner() -> None:
        await run_scan(mode=mode, scan_id=run.scan_id)

    asyncio.create_task(_runner())
    return {
        "scan_id": str(run.scan_id),
        "status": "queued",
        "strategy_id": STRATEGY_ID,
        "started_at": run.started_at.isoformat() if run.started_at else None,
    }
