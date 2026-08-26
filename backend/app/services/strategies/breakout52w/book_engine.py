"""Evaluate the current session and replay the Mode B 10% × 10 book."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ....utils import get_logger
from .alignment import NativeSeries, native_prefix, prior_high_index
from .costs import apply_buy, apply_sell, buy_cost, sell_cost
from .execution import (
    ATR_TRAIL_REASON,
    BACKTEST_END_CANONICAL,
    BACKTEST_END_REASON,
    ExecutionConfig,
    ExecutionDiagnostics,
    KERNEL_EXECUTION,
    apply_slippage,
    bar_from_maps,
    entry_fill_price,
    ltf_session_bars,
    record_symbol_failure,
    resolve_exit_fill,
)
from .identity import ALLOC_PCT, DEFAULT_CAPITAL, HIGH_LOOKBACK, RANK_LOOKBACK, STRATEGY_ID, VOL_SMA_PERIOD, WARMUP_SESSIONS
from .indicators import atr14, market_ok, market_sma50, momentum_60, prior_high_252, vol_sma20
from .portfolio import free_slots, shares_for_order, shares_from_notional, take_ranked, target_notional
from .signal import buy_signal, first_failure, rank_candidates, screener_pass
from .trail import initial_tsl, should_exit, update_trail

logger = get_logger("app.w52.book_engine")


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value))


def _sliding_prior_high(
    values: list[float], dates: list[date]
) -> dict[date, float | None]:
    """O(N) per-symbol precompute of ``prior_high_252`` keyed by session date.

    Exactly matches ``prior_high_252(values, j)`` for the native index ``j``
    (today present): max over the 252 sessions ending at j-1, or None when
    ``j < HIGH_LOOKBACK`` or any window value is non-finite.
    """
    n = len(values)
    out: dict[date, float | None] = {}
    if n < HIGH_LOOKBACK:
        return out
    dq: deque[int] = deque()
    bad = 0
    for k in range(HIGH_LOOKBACK):
        v = values[k]
        if not _finite(v):
            bad += 1
        else:
            while dq and values[dq[-1]] <= v:
                dq.pop()
            dq.append(k)
    for j in range(HIGH_LOOKBACK, n):
        out[dates[j]] = values[dq[0]] if (bad == 0 and dq) else None
        leave = j - HIGH_LOOKBACK
        lv = values[leave]
        if not _finite(lv):
            bad -= 1
        else:
            while dq and dq[0] <= leave:
                dq.popleft()
        nv = values[j]
        if not _finite(nv):
            bad += 1
        else:
            while dq and values[dq[-1]] <= nv:
                dq.pop()
            dq.append(j)
    return out


def _sliding_vol_sma(
    values: list[float], dates: list[date]
) -> dict[date, float | None]:
    """O(N) per-symbol precompute of ``vol_sma20`` keyed by session date.

    Matches ``vol_sma20(values, t)``: mean of the 20 sessions ending at t
    (today included), or None when ``t < VOL_SMA_PERIOD-1`` or any window
    value is non-finite.
    """
    n = len(values)
    out: dict[date, float | None] = {}
    if n < VOL_SMA_PERIOD:
        return out
    bad = 0
    s = 0.0
    for k in range(VOL_SMA_PERIOD):
        v = values[k]
        if not _finite(v):
            bad += 1
        else:
            s += v
    for t in range(VOL_SMA_PERIOD - 1, n):
        out[dates[t]] = (s / VOL_SMA_PERIOD) if bad == 0 else None
        if t + 1 < n:
            lv = values[t - VOL_SMA_PERIOD + 1]
            if not _finite(lv):
                bad -= 1
            else:
                s -= lv
            nv = values[t + 1]
            if not _finite(nv):
                bad += 1
            else:
                s += nv
    return out


def _sliding_momentum(
    values: list[float], dates: list[date]
) -> dict[date, float | None]:
    """O(N) per-symbol precompute of ``momentum_60`` keyed by session date.

    Matches ``momentum_60(values, t)``: values[t]/values[t-RANK_LOOKBACK]-1,
    or None when ``t < RANK_LOOKBACK`` or either endpoint is non-finite/zero.
    """
    n = len(values)
    out: dict[date, float | None] = {}
    for t in range(RANK_LOOKBACK, n):
        today = values[t]
        prev = values[t - RANK_LOOKBACK]
        if _finite(today) and _finite(prev) and float(prev) != 0:
            out[dates[t]] = float(today) / float(prev) - 1.0
        else:
            out[dates[t]] = None
    return out



@dataclass
class Holding:
    symbol: str
    shares: float
    entry_date: date
    entry_session_index: int
    entry_price: float
    hwm: float
    tsl: float
    signal_date: date | None = None
    signal_price: float | None = None
    entry_order_time: date | None = None
    buy_commission: float = 0.0
    entry_slippage: float = 0.0
    lifecycle: str = "LONG"


@dataclass
class PendingEntry:
    symbol: str
    signal_date: date
    signal_index: int
    signal_price: float
    atr: float | None


@dataclass
class Trade:
    symbol: str
    entry_date: date
    exit_date: date | None
    entry_price: float
    exit_price: float | None
    shares: float
    pnl_pct: float | None
    reason: str
    open: bool = False
    trade_id: str | None = None
    strategy_id: str = STRATEGY_ID
    direction: str = "LONG"
    signal_time: date | None = None
    entry_order_time: date | None = None
    entry_fill_time: date | None = None
    exit_order_time: date | None = None
    exit_fill_time: date | None = None
    quantity: float | None = None
    gross_pnl: float | None = None
    commission: float | None = None
    slippage: float | None = None
    net_pnl: float | None = None
    return_pct: float | None = None
    holding_period: int | None = None
    signal_price: float | None = None
    order_price: float | None = None
    fill_price: float | None = None
    fill_reason: str | None = None
    outcome: str | None = None
    exit_reason_canonical: str | None = None
    entry_signal: str | None = None


@dataclass
class BookState:
    cash: float = DEFAULT_CAPITAL
    initial_capital: float = DEFAULT_CAPITAL
    holdings: dict[str, Holding] = field(default_factory=dict)
    session_index: int = -1
    last_session: date | None = None
    sold_today: set[str] = field(default_factory=set)
    book_status: str = "WARMUP"
    market_ok: bool = False
    pending_entries: dict[str, PendingEntry] = field(default_factory=dict)
    lifecycle: dict[str, str] = field(default_factory=dict)


def _native_bars(
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    volumes: list[float | None],
    t: int,
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None], int | None]:
    """Joint compact: one missing OHLC bar is omitted from every series together."""
    hs: list[float | None] = []
    ls: list[float | None] = []
    cs: list[float | None] = []
    vs: list[float | None] = []
    today: int | None = None
    if t < 0:
        return hs, ls, cs, vs, None
    n = max(len(highs), len(lows), len(closes), len(volumes))
    end = min(t + 1, n)
    for i in range(end):
        h = highs[i] if i < len(highs) else None
        low = lows[i] if i < len(lows) else None
        c = closes[i] if i < len(closes) else None
        v = volumes[i] if i < len(volumes) else None
        if h is None and low is None and c is None:
            continue
        if i == t:
            today = len(hs)
        hs.append(h)
        ls.append(low)
        cs.append(c)
        vs.append(v)
    return hs, ls, cs, vs, today


def _native_indicators(
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    volumes: list[float | None],
    t: int,
) -> tuple[
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
]:
    """Indicators on this symbol's own sessions through calendar index ``t``.

    Today's close/high/volume are None when the symbol did not trade that date.
    """
    hs, ls, cs, vs, today = _native_bars(highs, lows, closes, volumes, t)
    close = cs[today] if today is not None else None
    high = hs[today] if today is not None else None
    vol = vs[today] if today is not None else None
    ph = prior_high_252(hs, prior_high_index(today, len(hs))) if hs else None
    vsma = vol_sma20(vs, today) if today is not None else None
    atr = atr14(hs, ls, cs, today) if today is not None else None
    mom = momentum_60(cs, today) if today is not None else None
    return close, high, vol, ph, vsma, atr, mom


def _mark_equity(state: BookState, prices: dict[str, float | None]) -> float:
    marked = 0.0
    for h in state.holdings.values():
        px = prices.get(h.symbol)
        if px is None:
            px = h.entry_price
        marked += h.shares * float(px)
    return state.cash + marked


def book_status_for(session_index: int, market_ok_flag: bool | None) -> str:
    if session_index < WARMUP_SESSIONS:
        return "WARMUP"
    if market_ok_flag is not True:
        return "MARKET_OFF"
    return "ACTIVE"


def _trade_id(symbol: str, entry: date, exit_d: date | None, reason: str) -> str:
    return f"{symbol}:{entry.isoformat()}:{(exit_d or date.min).isoformat()}:{reason}"


def _account_exit(
    h: Holding,
    *,
    exit_date: date,
    exit_price: float,
    reason: str,
    cfg: ExecutionConfig,
    canonical: str | None = None,
    exit_order_time: date | None = None,
) -> Trade:
    raw_exit = float(exit_price)
    slipped = apply_slippage(raw_exit, side="SELL", rate=cfg.slippage_rate)
    turnover = h.shares * slipped
    sell_fee = sell_cost(turnover) if cfg.apply_costs else 0.0
    buy_fee = float(h.buy_commission or 0.0)
    entry_slip = float(h.entry_slippage or 0.0)
    exit_slip = abs(raw_exit - slipped) * h.shares
    gross = h.shares * (slipped - h.entry_price)
    commission = buy_fee + sell_fee
    slippage = entry_slip + exit_slip
    net = gross - sell_fee - buy_fee
    # pnl_pct remains the price return used by 038 boards.
    pnl = (slipped / h.entry_price - 1.0) if h.entry_price else 0.0
    cost_basis = h.shares * h.entry_price
    ret = (net / cost_basis) if cost_basis else pnl
    hold = (exit_date - h.entry_date).days
    canon = canonical or (BACKTEST_END_CANONICAL if reason == BACKTEST_END_REASON else reason)
    return Trade(
        symbol=h.symbol,
        entry_date=h.entry_date,
        exit_date=exit_date,
        entry_price=h.entry_price,
        exit_price=slipped,
        shares=h.shares,
        pnl_pct=pnl,
        reason=reason,
        open=False,
        trade_id=_trade_id(h.symbol, h.entry_date, exit_date, reason),
        quantity=h.shares,
        gross_pnl=gross,
        commission=commission,
        slippage=slippage,
        net_pnl=net,
        return_pct=ret,
        holding_period=hold,
        signal_time=h.signal_date or h.entry_date,
        entry_order_time=h.entry_order_time or h.signal_date or h.entry_date,
        entry_fill_time=h.entry_date,
        exit_order_time=exit_order_time or exit_date,
        exit_fill_time=exit_date,
        signal_price=h.signal_price or h.entry_price,
        order_price=h.signal_price or h.entry_price,
        fill_price=slipped,
        fill_reason=reason,
        exit_reason_canonical=canon,
    )


def evaluate_session(
    *,
    session_index: int,
    dates: list[date],
    highs: dict[str, list[float | None]],
    lows: dict[str, list[float | None]],
    closes: dict[str, list[float | None]],
    volumes: dict[str, list[float | None]],
    benchmark: list[float | None],
    universe: set[str],
    state: BookState,
    data_failures: set[str] | None = None,
    unbuyable: set[str] | None = None,
    whole_shares: bool = False,
) -> dict[str, Any]:
    """Assign BUY / HOLD / WATCH / REJECT and today's orders without mutating replay history."""
    t = session_index
    failures = data_failures or set()
    skip = set(unbuyable or ())
    bench_n, t_b = native_prefix(benchmark, t) if t >= 0 else ([], None)
    mok = market_ok(bench_n, t_b) if t_b is not None else None
    nifty_close = bench_n[t_b] if t_b is not None else None
    nifty_sma = market_sma50(bench_n, t_b) if t_b is not None else None
    status = book_status_for(t, mok)
    sold = set(state.sold_today)
    held = set(state.holdings)

    rows: list[dict[str, Any]] = []
    candidates: list[tuple[str, float | None]] = []
    considered = set(universe) | held | failures
    for sym in sorted(considered):
        close, high, vol, ph, vsma, atr, mom = _native_indicators(
            highs.get(sym, []),
            lows.get(sym, []),
            closes.get(sym, []),
            volumes.get(sym, []),
            t,
        )
        is_held = sym in held
        is_sold = sym in sold
        gate = screener_pass(
            market_ok_flag=mok,
            close=close,
            prior_high=ph,
            volume=vol,
            vol_sma=vsma,
        )
        sig_ok = buy_signal(
            market_ok_flag=mok,
            close=close,
            prior_high=ph,
            volume=vol,
            vol_sma=vsma,
            held=is_held,
            sold_today=is_sold,
        )
        if sig_ok:
            candidates.append((sym, mom))
        rows.append(
            {
                "symbol": sym,
                "in_universe": sym in universe,
                "close": close,
                "high": high,
                "volume": vol,
                "high_252_prior": ph,
                "vol_sma20": vsma,
                "atr14": atr,
                "mom60": mom,
                "held": is_held,
                "sold_today": is_sold,
                "buy_signal": sig_ok,
                "screener_pass": gate,
                "data_source_failed": sym in failures,
            }
        )

    ranked = rank_candidates(candidates)
    rank_map = {s: r for s, _m, r in ranked}
    screener_ranked = rank_candidates(
        [(row["symbol"], row.get("mom60")) for row in rows if row.get("screener_pass")]
    )
    screener_rank_map = {s: r for s, _m, r in screener_ranked}
    free = free_slots(len(state.holdings))
    taken = take_ranked(ranked, free, unbuyable=skip) if status == "ACTIVE" and free > 0 else []
    taken_set = set(taken)

    orders: list[dict[str, Any]] = []
    # Trail exits for evaluate (read-only copy of state holdings)
    for h in state.holdings.values():
        _c, _hi, _vo, _ph, _vs, atr, _m = _native_indicators(
            highs.get(h.symbol, []),
            lows.get(h.symbol, []),
            closes.get(h.symbol, []),
            volumes.get(h.symbol, []),
            t,
        )
        close = _c
        if close is None:
            continue
        is_entry = h.entry_session_index == t
        hwm, tsl = update_trail(hwm=h.hwm, tsl=h.tsl, close=float(close), atr=atr, is_entry_bar=is_entry)
        if should_exit(close=float(close), tsl=tsl, is_entry_bar=is_entry):
            orders.append(
                {
                    "side": "EXIT",
                    "symbol": h.symbol,
                    "shares": h.shares,
                    "reason": "atr_trail",
                    "close": close,
                    "tsl": tsl,
                    "hwm": hwm,
                    "fill_model": "signal_close",
                }
            )

    for row in rows:
        sym = row["symbol"]
        is_held = row["held"]
        exiting = any(o["symbol"] == sym and o["side"] == "EXIT" for o in orders)
        if is_held and not exiting:
            opened_today = state.holdings[sym].entry_session_index == t
            row["signal"] = "BUY" if opened_today else "HOLD"
            row["first_failure"] = None
            row["buy_rank"] = rank_map.get(sym)
            row["screener_rank"] = screener_rank_map.get(sym)
            continue
        if exiting:
            row["held"] = False
        row["buy_rank"] = rank_map.get(sym)
        row["screener_rank"] = screener_rank_map.get(sym)
        if status == "WARMUP":
            row["signal"] = "REJECT"
            row["first_failure"] = row["first_failure"] if row.get("first_failure") else (
                first_failure(
                    in_universe=row["in_universe"],
                    data_source_failed=row["data_source_failed"],
                    prior_high=row["high_252_prior"],
                    close=row["close"],
                    high=row["high"],
                    volume=row["volume"],
                    vol_sma=row["vol_sma20"],
                    market_ok_flag=False,
                    sold_today=row["sold_today"],
                    held=False,
                    buy_rank=None,
                    free_slots=0,
                )
                or "insufficient_history"
            )
            continue
        if sym in taken_set:
            row["signal"] = "BUY"
            row["first_failure"] = None
            continue
        ff = first_failure(
            in_universe=row["in_universe"],
            data_source_failed=row["data_source_failed"],
            prior_high=row["high_252_prior"],
            close=row["close"],
            high=row["high"],
            volume=row["volume"],
            vol_sma=row["vol_sma20"],
            market_ok_flag=mok,
            sold_today=row["sold_today"],
            held=False,
            buy_rank=rank_map.get(sym),
            free_slots=free,
        )
        row["first_failure"] = ff
        if row["buy_signal"] and ff == "no_free_slot":
            row["signal"] = "WATCH"
        elif ff == "market_filter_off" and row["high_252_prior"] is not None:
            # stock legs already passed if we reached market filter
            row["signal"] = "WATCH"
            row["blocked_by"] = "market_filter"
        else:
            row["signal"] = "REJECT"

    prices = {sym: (closes.get(sym) or [None])[t] if t < len(closes.get(sym) or []) else None for sym in considered}
    equity = _mark_equity(state, prices)
    for i, sym in enumerate(taken):
        row = next(r for r in rows if r["symbol"] == sym)
        fill = float(row["close"])
        notional = min(target_notional(equity), max(state.cash, 0.0))
        shares = shares_from_notional(notional, fill, whole_shares=whole_shares)
        tsl0 = initial_tsl(fill, row["atr14"])
        orders.append(
            {
                "side": "BUY",
                "symbol": sym,
                "shares": shares,
                "reason": "breakout",
                "close": fill,
                "tsl0": tsl0,
                "atr": row["atr14"],
                "target_notional": notional,
                "target_weight": ALLOC_PCT,
                "fill_model": "signal_close",
                "rank": i + 1,
            }
        )

    return {
        "strategy_id": STRATEGY_ID,
        "book_status": status,
        "market_ok": mok is True,
        "nifty_close": nifty_close,
        "nifty_sma50": nifty_sma,
        "free_slots": free,
        "ranked": ranked,
        "selected": taken,
        "rows": rows,
        "orders": orders,
        "warmup": status == "WARMUP",
    }


def replay_book(
    dates: list[date],
    high_m: dict[str, dict[date, float]],
    low_m: dict[str, dict[date, float]],
    close_m: dict[str, dict[date, float]],
    vol_m: dict[str, dict[date, float]],
    index: dict[date, float],
    universe: set[str],
    *,
    initial_capital: float = DEFAULT_CAPITAL,
    whole_shares: bool = False,
    unbuyable: set[str] | None = None,
    delisted: set[str] | None = None,
    open_m: dict[str, dict[date, float]] | None = None,
    execution: ExecutionConfig | None = None,
    backtest_id: str | None = None,
    lower_tf: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    cfg = execution or KERNEL_EXECUTION
    open_m = open_m or {}
    diagnostics = ExecutionDiagnostics(
        lower_timeframe_requested=cfg.historical_fill_mode == "LOWER_TIMEFRAME",
        lower_timeframe_available=bool(lower_tf),
        lower_timeframe_fallback=cfg.historical_fill_mode == "LOWER_TIMEFRAME" and not lower_tf,
    )
    bt_id = backtest_id or "w52-replay"
    high_ns = {s: NativeSeries.from_map(high_m.get(s, {})) for s in universe}
    low_ns = {s: NativeSeries.from_map(low_m.get(s, {})) for s in universe}
    close_ns = {s: NativeSeries.from_map(close_m.get(s, {})) for s in universe}
    vol_ns = {s: NativeSeries.from_map(vol_m.get(s, {})) for s in universe}
    bench_ns = NativeSeries.from_map(index)
    skip = set(unbuyable or ())
    gone = set(delisted or ())

    # O(N) per-symbol precompute of the candidate-scan indicators. The previous
    # implementation recomputed prefix()+prior_high_252()+vol_sma20() for every
    # universe symbol on every session that had a free slot, which is O(N^2 * U)
    # and made the 755-symbol 18Y portfolio backtest appear to hang. These maps
    # hold exactly the same values the loop used (buy_signal already returns
    # False when close is None, so non-trading dates never consume them).
    ph_map = {s: _sliding_prior_high(high_ns[s].values, high_ns[s].dates) for s in universe}
    vsma_map = {s: _sliding_vol_sma(vol_ns[s].values, vol_ns[s].dates) for s in universe}
    mom_map = {s: _sliding_momentum(close_ns[s].values, close_ns[s].dates) for s in universe}

    state = BookState(cash=initial_capital, initial_capital=initial_capital)
    trades: list[Trade] = []
    equity_curve: list[dict[str, Any]] = []
    last_i = len(dates) - 1
    next_bar = cfg.order_fill_delay == "NEXT_BAR_OPEN"

    def _atr_on(sym: str, session: date) -> float | None:
        hs, t_h = high_ns[sym].prefix(session)
        ls, t_l = low_ns[sym].prefix(session)
        cs, t_c = close_ns[sym].prefix(session)
        if t_h is None or t_l is None or t_c is None:
            return None
        return atr14(hs, ls, cs, t_h)

    def _debit_buy(turnover: float) -> None:
        if cfg.apply_costs:
            state.cash = apply_buy(state.cash, turnover)
        else:
            state.cash -= turnover

    def _credit_sell(turnover: float) -> None:
        if cfg.apply_costs:
            state.cash = apply_sell(state.cash, turnover)
        else:
            state.cash += turnover

    def _close_holding(h: Holding, session: date, px: float, reason: str, canonical: str | None = None) -> None:
        state.holdings.pop(h.symbol, None)
        slipped = apply_slippage(float(px), side="SELL", rate=cfg.slippage_rate)
        _credit_sell(h.shares * slipped)
        tr = _account_exit(
            h, exit_date=session, exit_price=float(px), reason=reason, cfg=cfg, canonical=canonical
        )
        trades.append(tr)
        state.sold_today.add(h.symbol)
        state.lifecycle[h.symbol] = "FLAT"
        logger.info(
            "POSITION_CLOSED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s "
            "order_id=%s direction=LONG price=%s quantity=%s reason=%s",
            bt_id, STRATEGY_ID, h.symbol, session.isoformat(), tr.trade_id, tr.exit_price, h.shares, reason,
        )

    def _open_holding(
        *,
        symbol: str,
        session: date,
        session_index: int,
        fill: float,
        signal_date: date,
        signal_price: float,
        atr: float | None,
    ) -> Holding | None:
        if symbol in state.holdings:
            return None
        if cfg.pyramiding <= 0 and symbol in state.holdings:
            return None
        occupied = len(state.holdings) + (0 if next_bar else 0)
        if occupied >= cfg.max_positions:
            return None
        equity = _mark_equity(state, {**prices, symbol: fill})
        exec_px = apply_slippage(float(fill), side="BUY", rate=cfg.slippage_rate)
        sh = shares_for_order(
            exec_px,
            order_size_type=cfg.order_size_type,
            default_order_size=cfg.default_order_size,
            equity=equity,
            cash=state.cash,
            alloc_pct=cfg.alloc_pct,
            apply_costs=cfg.apply_costs,
            whole_shares=whole_shares,
        )
        if sh <= 0:
            return None
        turnover = sh * exec_px
        _debit_buy(turnover)
        tsl0 = initial_tsl(exec_px, atr)
        holding = Holding(
            symbol=symbol,
            shares=sh,
            entry_date=session,
            entry_session_index=session_index,
            entry_price=exec_px,
            hwm=exec_px,
            tsl=tsl0,
            signal_date=signal_date,
            signal_price=signal_price,
            entry_order_time=signal_date,
            buy_commission=buy_cost(turnover) if cfg.apply_costs else 0.0,
            entry_slippage=abs(exec_px - float(fill)) * sh,
            lifecycle="LONG",
        )
        state.holdings[symbol] = holding
        state.lifecycle[symbol] = "LONG"
        logger.info(
            "ORDER_FILLED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s "
            "order_id=%s direction=LONG price=%s quantity=%s reason=breakout",
            bt_id, STRATEGY_ID, symbol, session.isoformat(), f"{symbol}:{signal_date.isoformat()}:entry", exec_px, sh,
        )
        logger.info(
            "POSITION_OPENED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s "
            "order_id=%s direction=LONG price=%s quantity=%s reason=breakout",
            bt_id, STRATEGY_ID, symbol, session.isoformat(), f"{symbol}:{signal_date.isoformat()}:entry", exec_px, sh,
        )
        return holding

    for i, dt in enumerate(dates):
        state.sold_today = set()
        state.session_index = i
        state.last_session = dt
        prices = {s: close_m.get(s, {}).get(dt) for s in universe}
        bench_vals, t_b = bench_ns.prefix(dt)
        mok = market_ok(bench_vals, t_b) if t_b is not None else None
        state.market_ok = mok is True
        state.book_status = book_status_for(i, mok)

        # 1. Fill market entry orders created on a prior bar (TV default).
        if next_bar:
            for sym, order in list(state.pending_entries.items()):
                if order.signal_index >= i:
                    continue
                if sym in state.holdings or sym in skip:
                    state.pending_entries.pop(sym, None)
                    continue
                bar = bar_from_maps(sym, dt, open_m=open_m, high_m=high_m, low_m=low_m, close_m=close_m, vol_m=vol_m)
                fill = entry_fill_price(bar, cfg=cfg, signal_close=order.signal_price, diagnostics=diagnostics)
                if fill is None:
                    diagnostics.skipped_pending_entries += 1
                    state.pending_entries.pop(sym, None)
                    state.lifecycle[sym] = "FLAT"
                    continue
                atr = _atr_on(sym, dt)
                opened = _open_holding(
                    symbol=sym,
                    session=dt,
                    session_index=i,
                    fill=fill,
                    signal_date=order.signal_date,
                    signal_price=order.signal_price,
                    atr=atr,
                )
                state.pending_entries.pop(sym, None)
                if opened is None:
                    state.lifecycle[sym] = "FLAT"
                    continue
                if cfg.allow_entry_bar_exit:
                    ltf = ltf_session_bars(lower_tf, sym, dt)
                    hit = resolve_exit_fill(
                        bar, opened.tsl, cfg=cfg, lower_tf=ltf or None, diagnostics=diagnostics
                    )
                    if hit is not None:
                        logger.info(
                            "ORDER_CREATED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s "
                            "order_id=%s direction=LONG price=%s quantity=%s reason=%s",
                            bt_id, STRATEGY_ID, sym, dt.isoformat(),
                            _trade_id(sym, opened.entry_date, dt, hit.reason),
                            hit.price, opened.shares, hit.reason,
                        )
                        logger.info(
                            "ORDER_FILLED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s "
                            "order_id=%s direction=LONG price=%s quantity=%s reason=%s",
                            bt_id, STRATEGY_ID, sym, dt.isoformat(),
                            _trade_id(sym, opened.entry_date, dt, hit.reason),
                            hit.price, opened.shares, hit.reason,
                        )
                        _close_holding(opened, dt, hit.price, hit.reason)

        # 2. Delist exits
        for sym in list(state.holdings):
            if sym in gone:
                h = state.holdings[sym]
                px = prices.get(sym) or h.entry_price
                _close_holding(h, dt, float(px), "delist")

        # 3. Trail updates + exits. CLOSE_CROSS keeps 038 order (ratchet then test
        # close). INTRABAR tests the stop that existed at the prior close first.
        for sym, h in list(state.holdings.items()):
            close = prices.get(sym)
            if close is None:
                continue
            try:
                is_entry = h.entry_session_index == i
                atr = _atr_on(sym, dt)
                bar = bar_from_maps(sym, dt, open_m=open_m, high_m=high_m, low_m=low_m, close_m=close_m, vol_m=vol_m)
                if cfg.trail_touch == "INTRABAR_TOUCH":
                    block_entry = is_entry and not cfg.allow_entry_bar_exit
                    if not block_entry:
                        ltf = ltf_session_bars(lower_tf, sym, dt)
                        hit = resolve_exit_fill(
                            bar, h.tsl, cfg=cfg, lower_tf=ltf or None, diagnostics=diagnostics
                        )
                        if hit is not None:
                            _close_holding(h, dt, hit.price, ATR_TRAIL_REASON)
                            continue
                    h.hwm, h.tsl = update_trail(
                        hwm=h.hwm, tsl=h.tsl, close=float(close), atr=atr, is_entry_bar=block_entry
                    )
                else:
                    h.hwm, h.tsl = update_trail(
                        hwm=h.hwm, tsl=h.tsl, close=float(close), atr=atr, is_entry_bar=is_entry
                    )
                    if should_exit(close=float(close), tsl=h.tsl, is_entry_bar=is_entry):
                        _close_holding(h, dt, float(close), ATR_TRAIL_REASON)
            except Exception as exc:
                record_symbol_failure(
                    diagnostics, symbol=sym, error_type=type(exc).__name__, message=str(exc), stage="trail_exit"
                )
                logger.info(
                    "BACKTEST_SYMBOL_FAILED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s err=%s",
                    bt_id, STRATEGY_ID, sym, dt.isoformat(), exc,
                )

        # 4. End-of-backtest liquidation (final available candle only — not daily EOD).
        if i == last_i:
            if state.pending_entries:
                diagnostics.skipped_pending_entries += len(state.pending_entries)
                state.pending_entries.clear()
            if state.holdings:
                logger.info(
                    "BACKTEST_LIQUIDATION backtest_id=%s strategy_id=%s symbol=* timestamp=%s "
                    "order_id=- direction=LONG price=- quantity=%s reason=%s",
                    bt_id, STRATEGY_ID, dt.isoformat(), len(state.holdings), BACKTEST_END_CANONICAL,
                )
                for sym, h in list(state.holdings.items()):
                    px = prices.get(sym) or h.entry_price
                    _close_holding(h, dt, float(px), BACKTEST_END_REASON, canonical=BACKTEST_END_CANONICAL)

        equity = _mark_equity(state, prices)
        occupied = len(state.holdings) + len(state.pending_entries)
        free = free_slots(occupied, max_positions=cfg.max_positions)
        if state.book_status == "ACTIVE" and free > 0:
            cands: list[tuple[str, float | None]] = []
            for sym in universe:
                if sym in state.holdings or sym in state.sold_today or sym in state.pending_entries:
                    continue
                if not cfg.allow_reentry and state.lifecycle.get(sym) == "FLAT" and any(
                    t.symbol == sym for t in trades
                ):
                    continue
                try:
                    sig = buy_signal(
                        market_ok_flag=True,
                        close=prices.get(sym),
                        prior_high=ph_map[sym].get(dt),
                        volume=vol_m.get(sym, {}).get(dt),
                        vol_sma=vsma_map[sym].get(dt),
                        held=False,
                        sold_today=False,
                    )
                except Exception as exc:
                    record_symbol_failure(
                        diagnostics, symbol=sym, error_type=type(exc).__name__, message=str(exc), stage="signal"
                    )
                    continue
                if sig:
                    cands.append((sym, mom_map[sym].get(dt)))
            ranked = rank_candidates(cands)
            for sym in take_ranked(ranked, free, unbuyable=skip):
                signal_px = prices.get(sym)
                if signal_px is None or signal_px <= 0:
                    continue
                logger.info(
                    "ORDER_CREATED backtest_id=%s strategy_id=%s symbol=%s timestamp=%s "
                    "order_id=%s direction=LONG price=%s quantity=- reason=breakout",
                    bt_id, STRATEGY_ID, sym, dt.isoformat(), f"{sym}:{dt.isoformat()}:entry", signal_px,
                )
                if next_bar:
                    if i == last_i and cfg.skip_on_missing_next_bar:
                        diagnostics.skipped_pending_entries += 1
                        continue
                    state.pending_entries[sym] = PendingEntry(
                        symbol=sym,
                        signal_date=dt,
                        signal_index=i,
                        signal_price=float(signal_px),
                        atr=_atr_on(sym, dt),
                    )
                    state.lifecycle[sym] = "ENTRY_PENDING"
                    continue
                bar = bar_from_maps(sym, dt, open_m=open_m, high_m=high_m, low_m=low_m, close_m=close_m, vol_m=vol_m)
                fill = entry_fill_price(bar, cfg=cfg, signal_close=float(signal_px), diagnostics=diagnostics)
                if fill is None:
                    continue
                _open_holding(
                    symbol=sym,
                    session=dt,
                    session_index=i,
                    fill=fill,
                    signal_date=dt,
                    signal_price=float(signal_px),
                    atr=_atr_on(sym, dt),
                )

        equity = _mark_equity(state, prices)
        equity_curve.append(
            {
                "date": dt.isoformat(),
                "equity": equity,
                "cash": state.cash,
                "n_positions": len(state.holdings),
            }
        )

    return {
        "state": state,
        "trades": trades,
        "equity_curve": equity_curve,
        "diagnostics": diagnostics.as_dict(),
        "execution": cfg.as_public_dict(),
        "failed_symbols": list(diagnostics.failed_symbols),
        "skipped_symbols": list(diagnostics.skipped_symbols),
        "successful_symbols": sorted({t.symbol for t in trades} | set(state.holdings) | set(universe) - {f["symbol"] for f in diagnostics.failed_symbols}),
        "total_symbols": len(universe),
        "incomplete": bool(diagnostics.failed_symbols),
    }


def snapshot_open_trades(state: BookState, prices: dict[str, float | None], asof: date) -> list[Trade]:
    out: list[Trade] = []
    for h in state.holdings.values():
        px = prices.get(h.symbol)
        if px is None:
            px = h.entry_price
        pnl = (float(px) / h.entry_price - 1.0) if h.entry_price else 0.0
        out.append(
            Trade(
                symbol=h.symbol,
                entry_date=h.entry_date,
                exit_date=None,
                entry_price=h.entry_price,
                exit_price=float(px),
                shares=h.shares,
                pnl_pct=pnl,
                reason="open_mtm",
                open=True,
                trade_id=_trade_id(h.symbol, h.entry_date, None, "open_mtm"),
                quantity=h.shares,
                signal_time=h.signal_date or h.entry_date,
                entry_order_time=h.entry_order_time or h.signal_date or h.entry_date,
                entry_fill_time=h.entry_date,
                signal_price=h.signal_price or h.entry_price,
                order_price=h.signal_price or h.entry_price,
                fill_price=h.entry_price,
                fill_reason="open_mtm",
                commission=h.buy_commission,
                slippage=h.entry_slippage,
                return_pct=pnl,
            )
        )
    return out
