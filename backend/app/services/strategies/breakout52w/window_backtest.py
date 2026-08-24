"""On-demand period backtest for one 52W name.

Uses the existing book_engine.replay_book and daily_ohlcv / index_ohlcv.
Does not change scan lookback, selection rules, or cost/portfolio math.
"""

from __future__ import annotations

import hashlib
import time
from datetime import date, datetime, timedelta
from typing import Any

from ....config.settings import settings
from ....utils import get_logger
from .analytics import (
    WINDOW_YEARS,
    assess_window_coverage,
    build_symbol_dashboard,
    resolve_window_bounds,
)
from .book_engine import replay_book, snapshot_open_trades
from .execution import parse_execution_profile
from .identity import DEFAULT_CAPITAL, HIGH_LOOKBACK, STRATEGY_ID, STRATEGY_VERSION, TIMEFRAME, WARMUP_CALENDAR_DAYS
from .period import (
    PeriodRequestError,
    backtest_cache_key,
    filter_period_trades,
    slice_replay_dates,
)

logger = get_logger("app.w52.window_backtest")

_WINDOW_CACHE: dict[str, dict[str, Any]] = {}
_WINDOW_CACHE_ORDER: list[str] = []
_WINDOW_CACHE_MAX = 64


def _min_coverage_ratio() -> float:
    try:
        return float(getattr(settings, "w52_backtest_min_coverage_ratio", 0.5))
    except (TypeError, ValueError):
        return 0.5


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, type):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _trade_dict(tr) -> dict[str, Any]:
    return {
        "symbol": tr.symbol,
        "entry_date": tr.entry_date.isoformat(),
        "exit_date": tr.exit_date.isoformat() if tr.exit_date else None,
        "entry_price": tr.entry_price,
        "exit_price": tr.exit_price,
        "shares": tr.shares,
        "pnl_pct": tr.pnl_pct,
        "reason": tr.reason,
        "open": tr.open,
        "trade_id": getattr(tr, "trade_id", None),
        "gross_pnl": getattr(tr, "gross_pnl", None),
        "commission": getattr(tr, "commission", None),
        "slippage": getattr(tr, "slippage", None),
        "net_pnl": getattr(tr, "net_pnl", None),
        "outcome": getattr(tr, "outcome", None),
        "signal_time": tr.signal_time.isoformat() if getattr(tr, "signal_time", None) else None,
        "entry_fill_time": tr.entry_fill_time.isoformat() if getattr(tr, "entry_fill_time", None) else None,
        "exit_fill_time": tr.exit_fill_time.isoformat() if getattr(tr, "exit_fill_time", None) else None,
        "exit_reason": getattr(tr, "exit_reason_canonical", None) or tr.reason,
    }


def dataset_fingerprint(symbol: str, close_m: dict[date, float], dates: list[date]) -> dict[str, Any]:
    first = dates[0] if dates else None
    last = dates[-1] if dates else None
    first_close = close_m.get(first) if first else None
    last_close = close_m.get(last) if last else None
    raw = f"{symbol}|{len(dates)}|{first}|{last}|{first_close}|{last_close}"
    return {
        "symbol": symbol,
        "candle_count": len(dates),
        "first_date": first.isoformat() if first else None,
        "last_date": last.isoformat() if last else None,
        "first_close": first_close,
        "last_close": last_close,
        "data_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
    }


def fetch_start_for_window(start: date, window: str) -> date | None:
    key = (window or "").upper()
    if key == "ALL":
        return None
    return start - timedelta(days=WARMUP_CALENDAR_DAYS)


def clear_window_backtest_cache() -> None:
    _WINDOW_CACHE.clear()
    _WINDOW_CACHE_ORDER.clear()


def _cache_get(key: str) -> dict[str, Any] | None:
    hit = _WINDOW_CACHE.get(key)
    if hit is None:
        logger.info("BACKTEST_CACHE_MISS cache_key=%s", key)
        return None
    logger.info("BACKTEST_CACHE_HIT cache_key=%s", key)
    return hit


def _cache_set(key: str, value: dict[str, Any]) -> None:
    if key in _WINDOW_CACHE:
        _WINDOW_CACHE[key] = value
        return
    if len(_WINDOW_CACHE_ORDER) >= _WINDOW_CACHE_MAX:
        oldest = _WINDOW_CACHE_ORDER.pop(0)
        _WINDOW_CACHE.pop(oldest, None)
    _WINDOW_CACHE_ORDER.append(key)
    _WINDOW_CACHE[key] = value


async def load_symbol_window_bars(
    symbol: str,
    *,
    start: date,
    end: date,
    window: str,
) -> tuple[list[date], dict, dict, dict, dict, dict[date, float], dict]:
    from ...market_data_ingestion.repository import fetch_equity_history, fetch_index_history

    from_date = fetch_start_for_window(start, window)
    logger.info(
        "BACKTEST_DATA_LOAD symbol=%s window=%s requested_start=%s requested_end=%s fetch_from=%s",
        symbol,
        window,
        start.isoformat(),
        end.isoformat(),
        from_date.isoformat() if from_date else "full",
    )
    eq = await fetch_equity_history(symbol, from_date=from_date)
    idx = await fetch_index_history(
        getattr(settings, "strategy_index_store_symbol", None) or "NIFTY500",
        from_date=from_date,
    )
    eq = [r for r in eq if (d := _as_date(r.get("trade_date"))) is not None and d <= end]
    idx = [r for r in idx if (d := _as_date(r.get("trade_date"))) is not None and d <= end]

    high_m: dict[str, dict[date, float]] = {symbol: {}}
    low_m: dict[str, dict[date, float]] = {symbol: {}}
    close_m: dict[str, dict[date, float]] = {symbol: {}}
    vol_m: dict[str, dict[date, float]] = {symbol: {}}
    open_m: dict[str, dict[date, float]] = {symbol: {}}
    dates_set: set[date] = set()
    for row in eq:
        d = _as_date(row.get("trade_date"))
        if d is None:
            continue
        high_m[symbol][d] = float(row["high"])
        low_m[symbol][d] = float(row["low"])
        close_m[symbol][d] = float(row["close"])
        vol_m[symbol][d] = float(row.get("volume") or 0)
        if row.get("open") is not None:
            open_m[symbol][d] = float(row["open"])
        dates_set.add(d)
    index: dict[date, float] = {}
    for row in idx:
        d = _as_date(row.get("trade_date"))
        if d is None:
            continue
        index[d] = float(row["close"])
        dates_set.add(d)
    dates = sorted(dates_set)
    first = dates[0] if dates else None
    last = dates[-1] if dates else None
    logger.info(
        "BACKTEST_DATA_RECEIVED symbol=%s first_candle=%s last_candle=%s candle_count=%s index_count=%s",
        symbol,
        first.isoformat() if first else None,
        last.isoformat() if last else None,
        len(eq),
        len(index),
    )
    return dates, high_m, low_m, close_m, vol_m, index, open_m


def insufficient_dashboard(
    *,
    symbol: str,
    window: str,
    asof: date,
    coverage: dict[str, Any],
    signal: str | None = None,
    technicals: dict[str, Any] | None = None,
    initial_capital: float = DEFAULT_CAPITAL,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    key, start, end = resolve_window_bounds(asof, window, start=start, end=end)
    return {
        "strategy_id": STRATEGY_ID,
        "symbol": symbol,
        "window": key,
        "period_start": coverage.get("actual_start") or start.isoformat(),
        "period_end": coverage.get("actual_end") or end.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "signal": signal,
        "technicals": technicals,
        "total_return": None,
        "symbol_return": None,
        "cagr": None,
        "max_drawdown": None,
        "win_rate": None,
        "trade_count": 0,
        "sharpe_ratio": None,
        "profit_factor": None,
        "profit_factor_infinite": False,
        "initial_capital": round(float(initial_capital), 2),
        "ending_capital": None,
        "avg_trade_return": None,
        "max_consecutive_losses": 0,
        "verdict": None,
        "equity_curve": [],
        "drawdown_curve": [],
        "benchmark_curve": [],
        "index_curve": [],
        "monthly_returns": [],
        "trades": [],
        "trade_distribution": {
            "total_trades": 0,
            "winners": 0,
            "losers": 0,
            "breakevens": 0,
            "open_trades": 0,
            "source": "closed_trade_ledger",
        },
        "best_trade": None,
        "worst_trade": None,
        "top_winning": [],
        "top_losing": [],
        "never_selected_in_window": False,
        "backtest_failed": False,
        "unavailable_reason": "insufficient_history",
        "coverage": coverage,
        "replay_kind": "symbol_window",
        "book_metrics": None,
    }


async def load_lower_timeframe_bars(
    symbol: str,
    *,
    start: date,
    end: date,
) -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    """Load 60-minute bars when present. Never fabricate missing intrabar data."""
    from sqlalchemy import select

    from ....db.session import AsyncSessionLocal
    from ....models.market_data import HistoricalCandle

    start_ts = datetime.combine(start, datetime.min.time())
    end_ts = datetime.combine(end, datetime.max.time())
    rows: list[Any] = []
    resolution = None
    async with AsyncSessionLocal() as db:
        for res in ("60", "60min", "1H", "15", "15min"):
            stmt = (
                select(HistoricalCandle)
                .where(
                    HistoricalCandle.symbol == symbol,
                    HistoricalCandle.resolution == res,
                    HistoricalCandle.timestamp >= start_ts,
                    HistoricalCandle.timestamp <= end_ts,
                )
                .order_by(HistoricalCandle.timestamp.asc())
                .limit(50_000)
            )
            found = list((await db.scalars(stmt)).all())
            if found:
                rows = found
                resolution = res
                break
    if not rows:
        return {}, None
    out = [
        {
            "timestamp": r.timestamp,
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume or 0),
        }
        for r in rows
    ]
    return {symbol: out}, resolution


async def run_symbol_window_backtest(
    symbol: str,
    window: str = "3Y",
    *,
    asof: date | None = None,
    start: date | None = None,
    end: date | None = None,
    initial_capital: float = DEFAULT_CAPITAL,
    signal: str | None = None,
    technicals: dict[str, Any] | None = None,
    execution_profile: str | None = None,
    historical_fill_mode: str | None = None,
) -> dict[str, Any]:
    """Load stored daily bars and replay 52W rules across the requested window."""
    started = time.perf_counter()
    symbol = symbol.upper()
    asof = asof or date.today()
    profile = execution_profile or getattr(settings, "w52_execution_profile", None) or "KERNEL"
    fill_mode = historical_fill_mode or getattr(settings, "w52_historical_fill_mode", None)
    cfg = parse_execution_profile(profile, fill_mode=fill_mode)
    try:
        key, start, end = resolve_window_bounds(asof, window, start=start, end=end)
    except PeriodRequestError as exc:
        logger.info("BACKTEST_FAILED backtest_id=- strategy_id=%s symbol=%s timestamp=%s reason=%s", STRATEGY_ID, symbol, asof.isoformat(), exc)
        raise
    cache_key = backtest_cache_key(
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        universe_id=symbol,
        timeframe=TIMEFRAME,
        start_date=start,
        end_date=end,
        execution_config_hash=cfg.hash(),
    )
    logger.info(
        "BACKTEST_STARTED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s "
        "window=%s start_date=%s end_date=%s profile=%s fill_mode=%s",
        cache_key[:16],
        STRATEGY_ID,
        symbol,
        asof.isoformat(),
        key,
        start.isoformat(),
        end.isoformat(),
        cfg.profile,
        cfg.historical_fill_mode,
    )
    logger.info(
        "BACKTEST_REQUEST_ACCEPTED strategy=%s symbol=%s timeframe=%s window=%s "
        "start_date=%s end_date=%s cache_key=%s execution=%s",
        STRATEGY_ID,
        symbol,
        TIMEFRAME,
        key,
        start.isoformat(),
        end.isoformat(),
        cache_key,
        cfg.profile,
    )
    logger.info("BACKTEST_SYMBOL_STARTED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s", cache_key[:16], STRATEGY_ID, symbol, asof.isoformat())
    dates, high_m, low_m, close_m, vol_m, index, open_m = await load_symbol_window_bars(
        symbol, start=start, end=end, window=key
    )
    coverage = assess_window_coverage(
        [d for d in dates if d in close_m.get(symbol, {})],
        start=start,
        end=end,
        window=key,
        min_ratio=_min_coverage_ratio(),
    )
    if not coverage["sufficient"]:
        logger.info(
            "BACKTEST_INSUFFICIENT_HISTORY symbol=%s window=%s candle_count=%s coverage_ratio=%s requested=%s..%s actual=%s..%s",
            symbol,
            key,
            coverage.get("candle_count"),
            coverage.get("coverage_ratio"),
            coverage.get("requested_start"),
            coverage.get("requested_end"),
            coverage.get("actual_start"),
            coverage.get("actual_end"),
        )
        return insufficient_dashboard(
            symbol=symbol,
            window=key,
            asof=asof,
            coverage=coverage,
            signal=signal,
            technicals=technicals,
            initial_capital=initial_capital,
            start=start,
            end=end,
        )

    fp = dataset_fingerprint(symbol, close_m.get(symbol, {}), [d for d in dates if d in close_m.get(symbol, {})])
    result_key = f"{cache_key}:{fp['data_hash']}"
    cached_result = _cache_get(result_key)
    if cached_result is not None:
        return cached_result
    logger.info(
        "BACKTEST_DATASET symbol=%s candle_count=%s first_date=%s last_date=%s first_close=%s last_close=%s data_hash=%s",
        symbol,
        fp.get("candle_count"),
        fp.get("first_date"),
        fp.get("last_date"),
        fp.get("first_close"),
        fp.get("last_close"),
        fp.get("data_hash"),
    )
    sliced = slice_replay_dates(dates, period_start=start, period_end=end)
    replay_dates = sliced["dates"] or dates
    logger.info(
        "BACKTEST_WARMUP_APPLIED symbol=%s window=%s warmup_sessions=%s "
        "insufficient_warmup=%s warmup_start=%s actual_start=%s actual_end=%s",
        symbol,
        key,
        sliced.get("warmup_sessions_used"),
        sliced.get("insufficient_warmup"),
        sliced.get("warmup_start"),
        sliced.get("actual_start"),
        sliced.get("actual_end"),
    )
    logger.info(
        "BACKTEST_ENGINE_INPUT symbol=%s window=%s start=%s end=%s candle_count=%s first=%s last=%s",
        symbol,
        key,
        start.isoformat(),
        end.isoformat(),
        len(replay_dates),
        replay_dates[0].isoformat() if replay_dates else None,
        replay_dates[-1].isoformat() if replay_dates else None,
    )
    lower_tf = None
    ltf_res = None
    if cfg.historical_fill_mode == "LOWER_TIMEFRAME" and replay_dates:
        lower_tf, ltf_res = await load_lower_timeframe_bars(symbol, start=replay_dates[0], end=replay_dates[-1])
        if not lower_tf:
            logger.info(
                "BACKTEST_SYMBOL_FAILED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s "
                "err=lower_timeframe_missing fallback=DEFAULT_OHLC",
                result_key[:16], STRATEGY_ID, symbol, asof.isoformat(),
            )
    replay = replay_book(
        replay_dates,
        high_m,
        low_m,
        close_m,
        vol_m,
        index,
        {symbol},
        initial_capital=float(initial_capital),
        open_m=open_m,
        execution=cfg,
        backtest_id=result_key[:16],
        lower_tf=lower_tf,
    )
    if replay.get("diagnostics", {}).get("lower_timeframe_fallback") or (
        cfg.historical_fill_mode == "LOWER_TIMEFRAME" and not lower_tf
    ):
        replay.setdefault("diagnostics", {})["lower_timeframe_fallback"] = True
        replay["diagnostics"]["lower_timeframe_resolution"] = ltf_res
    prices = {symbol: close_m.get(symbol, {}).get(end) or close_m.get(symbol, {}).get(replay_dates[-1] if replay_dates else dates[-1])}
    open_tr = snapshot_open_trades(replay["state"], prices, end)
    all_trades = list(replay["trades"]) + list(open_tr)
    period_trades = filter_period_trades(all_trades, start, end)
    logger.info(
        "BACKTEST_TRADES_GENERATED symbol=%s window=%s generated=%s period_trades=%s",
        symbol,
        key,
        len(all_trades),
        len(period_trades),
    )
    logger.info("BACKTEST_AGGREGATION_STARTED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s", result_key[:16], STRATEGY_ID, symbol, asof.isoformat())
    index_curve = [
        {"date": d.isoformat(), "close": float(c)}
        for d, c in sorted(index.items())
        if start <= d <= end
    ]
    dash = build_symbol_dashboard(
        {
            "strategy_id": STRATEGY_ID,
            "evaluation_date": asof.isoformat(),
            "recommendations": [{"symbol": symbol, "signal": signal, "technicals": technicals}],
        },
        symbol,
        key,
        blotter=period_trades,
        equity_curve=list(replay.get("equity_curve") or []),
        index_curve=index_curve,
        asof=asof,
        initial_capital=float(initial_capital),
        symbol_replay=True,
        coverage=coverage,
        window_start=start,
        window_end=end,
        execution_config=cfg,
    )
    dash["replay_kind"] = "symbol_window"
    dash["symbol"] = symbol
    dash["data_hash"] = fp["data_hash"]
    dash["first_close"] = fp["first_close"]
    dash["last_close"] = fp["last_close"]
    dash["cache_key"] = result_key
    dash["requested_start"] = start.isoformat()
    dash["requested_end"] = end.isoformat()
    dash["warmup_sessions_used"] = sliced.get("warmup_sessions_used")
    dash["diagnostics"] = replay.get("diagnostics")
    dash["incomplete"] = bool(replay.get("incomplete"))
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "BACKTEST_METRICS_CALCULATED symbol=%s window=%s trade_count=%s avg_trade_return=%s "
        "total_return=%s duration_ms=%s",
        symbol,
        key,
        dash.get("trade_count"),
        dash.get("avg_trade_return"),
        dash.get("total_return"),
        duration_ms,
    )
    logger.info(
        "BACKTEST_ENGINE_OUTPUT symbol=%s window=%s trades=%s equity_points=%s period=%s..%s return=%s",
        symbol,
        key,
        dash.get("trade_count"),
        len(dash.get("equity_curve") or []),
        dash.get("period_start"),
        dash.get("period_end"),
        dash.get("total_return"),
    )
    logger.info(
        "BACKTEST_SYMBOL_COMPLETED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s trade_count=%s",
        result_key[:16], STRATEGY_ID, symbol, asof.isoformat(), dash.get("trade_count"),
    )
    dist = dash.get("trade_distribution") or {}
    logger.info(
        "BACKTEST_COMPLETED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s window=%s "
        "start_date=%s end_date=%s timeframe=%s closed_trade_count=%s open_trade_count=%s "
        "winner_count=%s loser_count=%s breakeven_count=%s entry_count=%s exit_count=%s "
        "cache_key=%s duration_ms=%s",
        result_key[:16],
        STRATEGY_ID,
        symbol,
        asof.isoformat(),
        key,
        start.isoformat(),
        end.isoformat(),
        TIMEFRAME,
        dist.get("total_trades", dash.get("trade_count")),
        dist.get("open_trades"),
        dist.get("winners"),
        dist.get("losers"),
        dist.get("breakevens"),
        len(period_trades),
        dist.get("total_trades"),
        result_key,
        duration_ms,
    )
    _cache_set(result_key, dash)
    return dash


# Imported by tests that assert warmup padding exists.
assert HIGH_LOOKBACK >= 252
assert WINDOW_YEARS["3Y"] == 3
