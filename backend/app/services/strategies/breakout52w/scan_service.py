"""52W scan orchestrator: freshness → evaluate → book replay → publish."""

from __future__ import annotations

import asyncio
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
    clamp_ohlcv_lookback,
    fetch_daily_ohlcv_for_symbols,
    iter_symbol_chunks,
)
from ....services.universe_service import UniverseService
from ....utils.symbol import canonical_symbol
from . import persistence
from .alignment import history_valid_native
from .attribution import apply_windowed_attribution, build_boards, empty_backtest, per_name_backtests
from .book_engine import BookState, evaluate_session, replay_book, snapshot_open_trades
from .execution import KERNEL_EXECUTION, parse_execution_profile
from .identity import (
    ATTRIBUTION_YEARS,
    DEFAULT_CAPITAL,
    DEFAULT_MODE,
    DEFAULT_OHLCV_LOOKBACK,
    DISPLAY_NAME,
    HIGH_LOOKBACK,
    HISTORICAL_PERIOD,
    LOCK_NAME,
    SHORT_NAME,
    STRATEGY_ID,
    WARMUP_SESSIONS,
)
from .period import period_window_start, scan_fetch_from_date, slice_replay_dates
from .rejection import breakdown
from .session_overlay import overlay_current_session
from .trail import initial_tsl

logger = logging.getLogger("app.strategies.w52.scan")


def _pos(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or n <= 0:
        return None
    return n


def published_trade_levels(
    *,
    signal: str,
    close: Any,
    atr14: Any,
    holding_tsl: Any = None,
) -> dict[str, float | None]:
    """Publish the book's fill/stop. Never invent a profit target."""
    if signal not in {"BUY", "HOLD", "WATCH"}:
        return {"entry": None, "stop_loss": None, "target": None, "risk_reward": None}
    entry = _pos(close)
    stop = _pos(holding_tsl)
    if stop is None and signal in {"BUY", "WATCH"} and entry is not None:
        stop = _pos(initial_tsl(entry, atr14 if atr14 is not None else None))
    return {
        "entry": entry,
        "stop_loss": stop,
        "target": None,
        "risk_reward": None,
    }

LIMITATIONS = [
    "Published historical numbers may be survivorship-biased if only the current NIFTY 500 list is available.",
    "Signal-close replay assumes you trade the close just used to test the breakout (look-ahead vs a live trader).",
    "Volume average and average true range include the signal bar.",
    "The buy signal is a state, not a first print — late entries can be late in the move.",
    "No hard stop: a close can print far below the trail (gap-through risk).",
    "Win rate is historically below 50%; the edge is payoff, not hit rate.",
    "Ten-name concentration with no sector cap.",
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


def scan_ohlcv_lookback() -> int:
    """Bounded sessions fetched for a 52W scan. Not a trading threshold."""
    configured = int(getattr(settings, "w52_ohlcv_lookback_sessions", DEFAULT_OHLCV_LOOKBACK))
    maximum = int(getattr(settings, "ohlcv_lookback_max_sessions", 2000))
    return clamp_ohlcv_lookback(configured, maximum=maximum, minimum=HIGH_LOOKBACK + 8)


def _public_scan_error(exc: BaseException) -> str:
    raw = str(exc)
    lowered = raw.lower()
    if "statement timeout" in lowered or "querycanceled" in type(exc).__name__.lower():
        return "Daily history query timed out."
    if "sql:" in lowered or len(raw) > 280:
        return "Daily history load failed."
    return raw


async def _load_from_strategy(symbols: list[str], *, from_date: date):
    rows = await fetch_daily_ohlcv_for_symbols(
        symbols,
        columns=(
            DailyOhlcv.trade_date,
            DailyOhlcv.symbol,
            DailyOhlcv.high,
            DailyOhlcv.low,
            DailyOhlcv.close,
            DailyOhlcv.volume,
        ),
        from_date=from_date,
    )
    min_date = None
    for trade_date, *_rest in rows:
        if min_date is None or trade_date < min_date:
            min_date = trade_date
    async with AsyncSessionLocal() as db:
        idx_stmt = select(IndexOhlcv.trade_date, IndexOhlcv.close).where(
            IndexOhlcv.symbol == settings.strategy_index_store_symbol
        )
        if min_date is not None:
            idx_stmt = idx_stmt.where(IndexOhlcv.trade_date >= min_date)
        idx_rows = (await db.execute(idx_stmt)).all()

    high_m: dict[str, dict[date, float]] = defaultdict(dict)
    low_m: dict[str, dict[date, float]] = defaultdict(dict)
    close_m: dict[str, dict[date, float]] = defaultdict(dict)
    vol_m: dict[str, dict[date, float]] = defaultdict(dict)
    dates_set: set[date] = set()
    for trade_date, symbol, high, low, close, volume in rows:
        high_m[symbol][trade_date] = float(high)
        low_m[symbol][trade_date] = float(low)
        close_m[symbol][trade_date] = float(close)
        vol_m[symbol][trade_date] = float(volume or 0)
        dates_set.add(trade_date)
    index = {d: float(c) for d, c in idx_rows}
    # Evaluation calendar is the union of equity sessions. Do not replace it with
    # the index calendar — that drops symbol-specific dates (holidays / 2026-06-26)
    # and would again mis-count a name's own 252 sessions.
    dates = sorted(dates_set)
    return dates, dict(high_m), dict(low_m), dict(close_m), dict(vol_m), index


async def _load_from_candles(symbols: list[str], *, from_date: date):
    from_ts = datetime.combine(from_date, datetime.min.time())
    rows: list[Any] = []
    async with AsyncSessionLocal() as db:
        for chunk in iter_symbol_chunks(symbols):
            stmt = (
                select(
                    HistoricalCandle.timestamp,
                    HistoricalCandle.symbol,
                    HistoricalCandle.high,
                    HistoricalCandle.low,
                    HistoricalCandle.close,
                    HistoricalCandle.volume,
                )
                .where(
                    HistoricalCandle.symbol.in_(chunk),
                    HistoricalCandle.resolution.in_(("1D", "D", "1d")),
                    HistoricalCandle.timestamp >= from_ts,
                )
                .order_by(HistoricalCandle.symbol.asc(), HistoricalCandle.timestamp.asc())
            )
            rows.extend((await db.execute(stmt)).all())
    high_m: dict[str, dict[date, float]] = defaultdict(dict)
    low_m: dict[str, dict[date, float]] = defaultdict(dict)
    close_m: dict[str, dict[date, float]] = defaultdict(dict)
    vol_m: dict[str, dict[date, float]] = defaultdict(dict)
    dates_set: set[date] = set()
    for ts, symbol, high, low, close, volume in rows:
        session = _as_session_date(ts)
        high_m[symbol][session] = float(high)
        low_m[symbol][session] = float(low)
        close_m[symbol][session] = float(close)
        vol_m[symbol][session] = float(volume or 0)
        dates_set.add(session)
    return sorted(dates_set), dict(high_m), dict(low_m), dict(close_m), dict(vol_m), {}


async def _load_matrices(symbols: list[str], *, from_date: date):
    dates, high_m, low_m, close_m, vol_m, index = await _load_from_strategy(symbols, from_date=from_date)
    source = "daily_ohlcv"
    if len(dates) < 253:
        fb = await _load_from_candles(symbols, from_date=from_date)
        if len(fb[0]) > len(dates):
            dates, high_m, low_m, close_m, vol_m, index = fb[0], fb[1], fb[2], fb[3], fb[4], fb[5] or index
            source = "historical_candles"
    return dates, high_m, low_m, close_m, vol_m, index, source


def _history_valid(high_m: dict[str, dict[date, float]], dates: list[date], sym: str, t_idx: int) -> bool:
    if t_idx < 0 or t_idx >= len(dates):
        return False
    return history_valid_native(high_m.get(sym, {}), dates[t_idx])


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
    idx_vals = [index[date.fromisoformat(p["date"])] for p in equity_curve if date.fromisoformat(p["date"]) in index]
    bench_ret = None
    if len(idx_vals) >= 2 and idx_vals[0]:
        bench_ret = idx_vals[-1] / idx_vals[0] - 1.0
    invested = sum(1 for p in equity_curve if p.get("n_positions", 0) > 0)
    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_dd": max_dd,
        "calmar": calmar,
        "exposure": invested / len(equity_curve) if equity_curve else 0.0,
        "excess_vs_nifty500": (cagr - ((idx_vals[-1] / idx_vals[0]) ** (365.25 / days) - 1.0)) if bench_ret is not None and idx_vals[0] else None,
        "ending_equity": final,
        "initial_capital": initial,
    }


def _align(series: dict[date, float], dates: list[date]) -> list[float | None]:
    return [series.get(d) for d in dates]


def build_payload(
    *,
    scan_id: str,
    evaluation_date: date,
    ev: dict[str, Any],
    replay: dict[str, Any],
    dates: list[date],
    high_m: dict[str, dict[date, float]],
    close_m: dict[str, dict[date, float]],
    index: dict[date, float],
    universe: set[str],
    mode: str,
    survivorship_biased: bool,
    initial_capital: float,
    attribution_failed: set[str] | None = None,
    company_name_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    t_idx = len(dates) - 1
    prices = {s: close_m.get(s, {}).get(evaluation_date) for s in universe}
    state: BookState = replay["state"]
    open_tr = snapshot_open_trades(state, prices, evaluation_date)
    all_trades = list(replay["trades"]) + open_tr
    history_valid = {s for s in universe if _history_valid(high_m, dates, s, t_idx)}
    failed = set(attribution_failed or ())
    reports = per_name_backtests(
        all_trades,
        asof=evaluation_date,
        years=ATTRIBUTION_YEARS,
        history_valid=history_valid,
        failed=failed,
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
        if row.get("data_source_failed") or sym in failed:
            data_failures += 1
        if row.get("close") is not None:
            data_valid += 1
        evaluated += 1
        if row.get("first_failure") and row.get("signal") == "REJECT":
            fail_codes.append(row["first_failure"])
        if hv and sym in failed:
            bt = empty_backtest(evaluation_date, years=ATTRIBUTION_YEARS, failed=True)
        elif hv:
            bt = reports.get(sym) or empty_backtest(evaluation_date, years=ATTRIBUTION_YEARS)
        else:
            bt = None
        holding = state.holdings.get(sym)
        levels = published_trade_levels(
            signal=row["signal"],
            close=row.get("close"),
            atr14=row.get("atr14"),
            holding_tsl=holding.tsl if holding is not None else None,
        )
        recs.append(
            {
                "rank": row.get("screener_rank") or row.get("buy_rank"),
                "symbol": canon_sym,
                "company_name": comp_name,
                "signal": row["signal"],
                "close": row.get("close"),
                "high_252_prior": row.get("high_252_prior"),
                "volume": row.get("volume"),
                "vol_sma20": row.get("vol_sma20"),
                "atr14": row.get("atr14"),
                "mom60": row.get("mom60"),
                "score_kind": "momentum_60",
                "market_ok": ev["market_ok"],
                "blocked_by": row.get("blocked_by"),
                "first_failure": row.get("first_failure"),
                "buy_signal": bool(row.get("buy_signal")),
                "screener_pass": bool(row.get("screener_pass")),
                "entry": levels["entry"],
                "stop_loss": levels["stop_loss"],
                "target": levels["target"],
                "risk_reward": levels["risk_reward"],
                "target_weight": 0.10 if row["signal"] == "BUY" else None,
                "target_notional": None,
                "technicals": {
                    "close_t": row.get("close"),
                    "high_252_prior": row.get("high_252_prior"),
                    "close_vs_prior_high": (
                        None
                        if row.get("close") is None or row.get("high_252_prior") is None
                        else float(row["close"]) >= float(row["high_252_prior"])
                    ),
                    "volume": row.get("volume"),
                    "vol_sma20": row.get("vol_sma20"),
                    "volume_vs_average": (
                        None
                        if row.get("volume") is None or row.get("vol_sma20") is None
                        else float(row["volume"]) > float(row["vol_sma20"])
                    ),
                    "atr14": row.get("atr14"),
                    "mom60": row.get("mom60"),
                    "rank_among_signals": row.get("buy_rank"),
                    "market_ok": ev["market_ok"],
                    "nifty_close": ev.get("nifty_close"),
                    "nifty_sma50": ev.get("nifty_sma50"),
                    "slot_status": (
                        "taken"
                        if row["signal"] == "BUY"
                        else "held"
                        if row["signal"] == "HOLD"
                        else "sold_today"
                        if row.get("sold_today")
                        else "no_slot"
                        if row["signal"] == "WATCH"
                        else "rejected"
                    ),
                    "hwm": state.holdings[sym].hwm if sym in state.holdings else None,
                    "tsl": state.holdings[sym].tsl if sym in state.holdings else None,
                    "would_exit": False,
                    "hard_filters_pass": bool(row.get("buy_signal")) or row["signal"] in {"BUY", "HOLD", "WATCH"},
                },
                "backtest_1y": None
                if bt is None
                else {
                    "window_start": bt["window_start"],
                    "window_end": bt["window_end"],
                    "trade_count": bt["trade_count"],
                    "net_return": bt["net_return"],
                    "win_rate": bt["win_rate"],
                    "max_drawdown": bt["max_drawdown"],
                    "profit_factor": bt["profit_factor"] if bt.get("profit_factor") != float("inf") else None,
                    "never_selected_in_window": bt["never_selected_in_window"],
                    "failed": bt.get("failed", False),
                    "trades": [_trade_dict(t) for t in bt.get("trades") or []],
                },
            }
        )

    # Gate passers (TradingView-style) before book HOLD so the scan list matches the Pine screener.
    order_key = {"BUY": 0, "WATCH": 1, "HOLD": 2, "REJECT": 3}
    recs.sort(
        key=lambda r: (
            0 if r.get("screener_pass") or r.get("buy_signal") or r.get("signal") in {"BUY", "WATCH"} else order_key.get(r["signal"], 9),
            order_key.get(r["signal"], 9),
            r["rank"] or 10_000,
            r["symbol"],
        )
    )
    buy_n = sum(1 for r in recs if r["signal"] == "BUY")
    hold_n = sum(1 for r in recs if r["signal"] == "HOLD")
    watch_n = sum(1 for r in recs if r["signal"] == "WATCH")
    reject_n = sum(1 for r in recs if r["signal"] == "REJECT")
    top5, least5 = build_boards(reports, signals, company_names=company_name_map)
    holdings = [
        {
            "symbol": canonical_symbol(h.symbol),
            "company_name": company_name_map.get(canonical_symbol(h.symbol)),
            "shares": h.shares,
            "entry_price": h.entry_price,
            "entry_date": h.entry_date.isoformat(),
            "hwm": h.hwm,
            "tsl": h.tsl,
            "mark": prices.get(h.symbol),
            "unrealized_pct": ((prices[h.symbol] / h.entry_price - 1.0) if prices.get(h.symbol) and h.entry_price else None),
        }
        for h in state.holdings.values()
    ]
    payload = {
        "strategy_id": STRATEGY_ID,
        "display_name": DISPLAY_NAME,
        "short_name": SHORT_NAME,
        "scan_id": scan_id,
        "status": "completed",
        "recommendations_final": True,
        "evaluation_date": evaluation_date.isoformat(),
        "book_status": ev["book_status"],
        "market_ok": ev["market_ok"],
        "nifty_close": ev.get("nifty_close"),
        "nifty_sma50": ev.get("nifty_sma50"),
        "n_positions": len(state.holdings),
        "cash": state.cash,
        "equity": replay["equity_curve"][-1]["equity"] if replay["equity_curve"] else state.cash,
        "free_slots": ev["free_slots"],
        "survivorship_biased": survivorship_biased,
        "warmup": ev["warmup"],
        "mode": mode,
        "fill_model": "signal_close",
        "summary": {
            "total": len(recs),
            "data_valid": data_valid,
            "evaluated": evaluated,
            "final_candidates": len(ev["selected"]),
            "screener_matches": sum(1 for r in recs if r.get("screener_pass") or r.get("buy_signal")),
            "buy": buy_n,
            "hold": hold_n,
            "watch": watch_n,
            "reject": reject_n,
            "data_failures": data_failures,
        },
        "screener_matches": [r["symbol"] for r in recs if r.get("screener_pass") or r.get("buy_signal")],
        "rejection_breakdown": breakdown(fail_codes, evaluated),
        "recommendations": recs,
        "orders": ev["orders"],
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


_active_scan_task: asyncio.Task | None = None
_active_scan_id: uuid.UUID | None = None


def is_scan_active_in_memory(scan_id: uuid.UUID | str | None = None) -> bool:
    global _active_scan_task, _active_scan_id
    if _active_scan_task is None or _active_scan_task.done():
        return False
    if scan_id is not None and _active_scan_id is not None:
        return str(_active_scan_id) == str(scan_id)
    return True


def cancel_active_scan() -> bool:
    global _active_scan_task
    if _active_scan_task is not None and not _active_scan_task.done():
        _active_scan_task.cancel()
        return True
    return False


async def run_scan(*, mode: str | None = None, progress_cb=None, scan_id: uuid.UUID | None = None) -> dict[str, Any]:
    mode_u = (mode or getattr(settings, "w52_default_mode", None) or DEFAULT_MODE).upper()
    capital = float(getattr(settings, "w52_initial_capital", None) or DEFAULT_CAPITAL)
    lock = DistributedLockService(getattr(settings, "w52_lock_name", None) or LOCK_NAME, ttl_seconds=300)
    got = await lock.acquire(timeout_seconds=2)
    if not got:
        if scan_id is not None:
            latest = await persistence.load_latest(STRATEGY_ID)
            await persistence.update_run(
                scan_id, status="failed", error_code="W52_SCAN_IN_PROGRESS", finished=True
            )
            if latest is None or latest.scan_id == scan_id:
                await persistence.save_latest(
                    STRATEGY_ID,
                    scan_id=scan_id,
                    status="failed",
                    payload={"error_code": "W52_SCAN_IN_PROGRESS", "recommendations_final": False},
                    error_code="W52_SCAN_IN_PROGRESS",
                )
        return {"error_code": "W52_SCAN_IN_PROGRESS", "status": "failed"}
    lock.start_heartbeat()

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
        logger.info("SCAN_STARTED strategy=%s scan_id=%s mode=%s", STRATEGY_ID, scan_id, mode_u)
        await stage("evaluating", 5, "evaluating")
        symbols = await UniverseService.get_active_nifty500_symbols()
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
        logger.info("UNIVERSE_LOADED strategy=%s scan_id=%s stock_count=%s", STRATEGY_ID, scan_id, len(universe))
        fetch_from = scan_fetch_from_date(date.today())
        logger.info(
            "BACKTEST_DATE_RANGE_RESOLVED strategy=%s universe=%s timeframe=1D "
            "historical_period=%s fetch_from=%s asof_hint=%s",
            STRATEGY_ID,
            len(symbols),
            HISTORICAL_PERIOD,
            fetch_from.isoformat(),
            date.today().isoformat(),
        )
        load_started = datetime.now(timezone.utc)
        dates, high_m, low_m, close_m, vol_m, index, data_source = await _load_matrices(
            symbols, from_date=fetch_from
        )
        dates, high_m, low_m, close_m, vol_m, index, bar_source = await overlay_current_session(
            dates, high_m, low_m, close_m, vol_m, index, symbols
        )
        if bar_source in {"live_session", "completed_history"}:
            data_source = f"{data_source}+{bar_source}"
        if len(dates) < 253:
            payload = {
                "error_code": "W52_INSUFFICIENT_DATA",
                "status": "failed",
                "message": f"Need at least 253 daily sessions; found {len(dates)} in {data_source}.",
                "recommendations_final": False,
            }
            await persistence.update_run(scan_id, status="failed", error_code="W52_INSUFFICIENT_DATA", payload=payload, finished=True)
            await persistence.save_latest(STRATEGY_ID, scan_id=scan_id, status="failed", payload=payload)
            return payload

        t_idx = len(dates) - 1
        evaluation_date = dates[t_idx]
        logger.info(
            "BACKTEST_DATA_LOAD strategy=%s source=%s candle_sessions=%s "
            "first=%s last=%s fetch_from=%s duration_ms=%s",
            STRATEGY_ID,
            data_source,
            len(dates),
            dates[0].isoformat() if dates else None,
            dates[-1].isoformat() if dates else None,
            fetch_from.isoformat(),
            int((datetime.now(timezone.utc) - load_started).total_seconds() * 1000),
        )
        warmup = slice_replay_dates(
            dates,
            period_start=period_window_start(evaluation_date, HISTORICAL_PERIOD),
            period_end=evaluation_date,
            warmup_sessions=WARMUP_SESSIONS,
        )
        logger.info(
            "BACKTEST_WARMUP_APPLIED strategy=%s warmup_sessions=%s "
            "insufficient_warmup=%s performance_sessions=%s warmup_start=%s actual_start=%s actual_end=%s",
            STRATEGY_ID,
            warmup.get("warmup_sessions_used"),
            warmup.get("insufficient_warmup"),
            len(warmup.get("performance_dates") or []),
            warmup.get("warmup_start"),
            warmup.get("actual_start"),
            warmup.get("actual_end"),
        )
        highs: dict[str, list[float | None]] = {}
        lows: dict[str, list[float | None]] = {}
        closes: dict[str, list[float | None]] = {}
        volumes: dict[str, list[float | None]] = {}
        symbols_list = sorted(universe)
        total = len(symbols_list)
        align_started = datetime.now(timezone.utc)
        for i, symbol in enumerate(symbols_list, 1):
            highs[symbol] = _align(high_m.get(symbol, {}), dates)
            lows[symbol] = _align(low_m.get(symbol, {}), dates)
            closes[symbol] = _align(close_m.get(symbol, {}), dates)
            volumes[symbol] = _align(vol_m.get(symbol, {}), dates)
            if i == 1 or i == total or i % 20 == 0:
                pct = 8 + int(28 * i / max(total, 1))
                await persistence.update_run(
                    scan_id,
                    status="evaluating",
                    stage="evaluating",
                    progress_pct=min(pct, 38),
                    progress_meta={
                        "phase": "stock_processing",
                        "current_symbol": symbol,
                        "processed_count": i,
                        "total_count": total,
                    },
                )
        logger.info(
            "INDIVIDUAL_BACKTESTS_COMPLETED strategy=%s scan_id=%s stock_count=%s "
            "duration_ms=%s",
            STRATEGY_ID,
            scan_id,
            total,
            int((datetime.now(timezone.utc) - align_started).total_seconds() * 1000),
        )
        bench = _align(index, dates)

        # Clear stale per-symbol counters so the UI does not show "755/755" +
        # the last symbol while the portfolio backtest runs. The portfolio
        # stage is tracked separately via phase=portfolio_backtest.
        await stage(
            "backtesting",
            40,
            "backtesting",
            phase="portfolio_backtest",
            current_symbol=None,
            processed_count=None,
            total_count=None,
        )
        logger.info("PORTFOLIO_BACKTEST_STARTED strategy=%s scan_id=%s", STRATEGY_ID, scan_id)
        logger.info(
            "BACKTEST_STARTED backtest_id=%s strategy_id=%s symbol=* timestamp=%s total_symbols=%s",
            scan_id, STRATEGY_ID, evaluation_date.isoformat(), len(universe),
        )
        replay_started = datetime.now(timezone.utc)
        timeout_s = int(getattr(settings, "w52_portfolio_backtest_timeout_seconds", 300))
        exec_cfg = parse_execution_profile(getattr(settings, "w52_execution_profile", None))
        try:
            replay = await asyncio.wait_for(
                asyncio.to_thread(
                    replay_book,
                    dates,
                    high_m,
                    low_m,
                    close_m,
                    vol_m,
                    index,
                    universe,
                    initial_capital=capital,
                    whole_shares=False,
                    execution=exec_cfg,
                    backtest_id=str(scan_id),
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.error(
                "SCAN_TIMEOUT strategy=%s scan_id=%s stage=portfolio_backtest budget_s=%s",
                STRATEGY_ID,
                scan_id,
                timeout_s,
            )
            raise TimeoutError(f"Portfolio backtest exceeded {timeout_s}s budget")
        except Exception as p_exc:
            logger.error(
                "PORTFOLIO_BACKTEST_FAILED strategy=%s scan_id=%s err=%s",
                STRATEGY_ID,
                scan_id,
                p_exc,
            )
            raise
        failed_n = len(replay.get("failed_symbols") or [])
        logger.info(
            "PORTFOLIO_BACKTEST_COMPLETED strategy=%s scan_id=%s trade_count=%s "
            "equity_points=%s duration_ms=%s failed_symbols=%s incomplete=%s",
            STRATEGY_ID,
            scan_id,
            len(replay.get("trades") or []),
            len(replay.get("equity_curve") or []),
            int((datetime.now(timezone.utc) - replay_started).total_seconds() * 1000),
            failed_n,
            bool(replay.get("incomplete")),
        )
        logger.info(
            "BACKTEST_COMPLETED backtest_id=%s strategy_id=%s symbol=* timestamp=%s "
            "successful_symbols=%s failed_symbols=%s total_symbols=%s",
            scan_id,
            STRATEGY_ID,
            evaluation_date.isoformat(),
            len(universe) - failed_n,
            failed_n,
            len(universe),
        )
        ev = evaluate_session(
            session_index=t_idx,
            dates=dates,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            benchmark=bench,
            universe=universe,
            state=replay["state"],
        )

        await stage(
            "publishing",
            85,
            "publishing",
            phase="publishing",
            current_symbol=None,
            processed_count=None,
            total_count=None,
        )
        logger.info("RESULT_PERSISTENCE_STARTED strategy=%s scan_id=%s", STRATEGY_ID, scan_id)
        try:
            company_name_map = await UniverseService.get_company_name_map()
        except Exception:
            company_name_map = {}
        payload = _json_safe(
            build_payload(
                scan_id=str(scan_id),
                evaluation_date=evaluation_date,
                ev=ev,
                replay=replay,
                dates=dates,
                high_m=high_m,
                close_m=close_m,
                index=index,
                universe=universe,
                mode=mode_u,
                survivorship_biased=True,
                initial_capital=capital,
                company_name_map=company_name_map,
            )
        )
        payload["data_source"] = data_source
        payload["evaluation_bar"] = bar_source
        payload["evaluation_date"] = evaluation_date.isoformat()
        payload["execution"] = (replay.get("execution") or KERNEL_EXECUTION.as_public_dict())
        payload["diagnostics"] = replay.get("diagnostics")
        payload["failed_symbols"] = replay.get("failed_symbols") or []
        payload["incomplete"] = bool(replay.get("incomplete"))
        if payload["incomplete"]:
            payload["recommendations_final"] = False
            payload["status"] = "completed_partial"
        st = replay["state"]
        await persistence.save_book_state(
            cash=st.cash,
            equity=payload.get("equity") or st.cash,
            session_index=st.session_index,
            last_session_processed=st.last_session,
            book_status=ev["book_status"],
            market_ok=ev["market_ok"],
            nifty_close=ev.get("nifty_close"),
            nifty_sma50=ev.get("nifty_sma50"),
            holdings=[
                {
                    "symbol": h.symbol,
                    "shares": h.shares,
                    "entry_price": h.entry_price,
                    "entry_date": h.entry_date.isoformat(),
                    "entry_session_index": h.entry_session_index,
                    "hwm": h.hwm,
                    "tsl": h.tsl,
                }
                for h in st.holdings.values()
            ],
            sold_today=sorted(st.sold_today),
            mode=mode_u,
            survivorship_biased=True,
            initial_capital=capital,
        )
        run_status = "completed_partial" if payload.get("incomplete") else "completed"
        await persistence.update_run(scan_id, status=run_status, stage="completed", progress_pct=100, payload=payload, finished=True)
        await persistence.save_latest(STRATEGY_ID, scan_id=scan_id, status=run_status, payload=payload)
        logger.info(
            "RESULT_PERSISTENCE_COMPLETED strategy=%s scan_id=%s selected=%s blotter=%s "
            "window_start=%s window_end=%s",
            STRATEGY_ID,
            scan_id,
            len(ev["selected"]),
            len(payload.get("blotter") or []),
            payload.get("attribution_window_start"),
            payload.get("attribution_window_end"),
        )
        logger.info("SCAN_COMPLETED strategy=%s scan_id=%s selected=%s", STRATEGY_ID, scan_id, len(ev["selected"]))
        return payload
    except asyncio.CancelledError:
        logger.warning("SCAN_CANCELLED strategy=%s scan_id=%s", STRATEGY_ID, scan_id)
        payload = {
            "error_code": "W52_SCAN_CANCELLED",
            "status": "cancelled",
            "detail": "Scan was cancelled",
            "recommendations_final": False,
        }
        await persistence.update_run(
            scan_id, status="cancelled", error_code="W52_SCAN_CANCELLED", error_detail="Scan was cancelled", payload=payload, finished=True
        )
        await persistence.save_latest(STRATEGY_ID, scan_id=scan_id, status="cancelled", payload=payload, error_code="W52_SCAN_CANCELLED")
        raise
    except Exception as exc:
        is_timeout = isinstance(exc, TimeoutError)
        logger.exception("SCAN_FAILED strategy=%s scan_id=%s timeout=%s", STRATEGY_ID, scan_id, is_timeout)
        public = _public_scan_error(exc)
        error_code = "W52_SCAN_TIMEOUT" if is_timeout else "W52_SCAN_FAILED"
        payload = {
            "error_code": error_code,
            "status": "failed",
            "detail": public,
            "recommendations_final": False,
        }
        await persistence.update_run(
            scan_id, status="failed", error_code=error_code, error_detail=public, payload=payload, finished=True
        )
        await persistence.save_latest(STRATEGY_ID, scan_id=scan_id, status="failed", payload=payload, error_code=error_code)
        return payload
    finally:
        await lock.release()


async def start_scan_background(mode: str | None = None) -> dict[str, Any]:
    global _active_scan_task, _active_scan_id

    # If a task is actively running in memory in this process
    if _active_scan_task is not None and not _active_scan_task.done():
        active = await persistence.find_active_run()
        scan_id_str = str(active.scan_id) if active else str(_active_scan_id)
        return {
            "error_code": "W52_SCAN_IN_PROGRESS",
            "scan_id": scan_id_str,
            "status": active.status if active else "evaluating",
            "strategy_id": STRATEGY_ID,
        }

    active = await persistence.find_active_run()
    if active:
        return {
            "error_code": "W52_SCAN_IN_PROGRESS",
            "scan_id": str(active.scan_id),
            "status": active.status,
            "strategy_id": STRATEGY_ID,
        }

    run = await persistence.create_run(STRATEGY_ID)
    _active_scan_id = run.scan_id
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

    async def _runner() -> None:
        try:
            await run_scan(mode=mode, scan_id=run.scan_id)
        except Exception:
            logger.exception("SCAN_BACKGROUND_TASK_FAILED strategy=%s scan_id=%s", STRATEGY_ID, run.scan_id)
        finally:
            global _active_scan_task, _active_scan_id
            if _active_scan_id == run.scan_id:
                _active_scan_task = None
                _active_scan_id = None

    _active_scan_task = asyncio.create_task(_runner())
    return {
        "scan_id": str(run.scan_id),
        "status": "queued",
        "strategy_id": STRATEGY_ID,
        "started_at": run.started_at.isoformat() if run.started_at else None,
    }

