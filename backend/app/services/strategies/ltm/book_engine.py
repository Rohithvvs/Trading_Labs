"""Evaluate the current session and replay the Mode A/B book on an aligned matrix."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .calendar import clock_status, sessions_to_rebalance
from .identity import (
    DEFAULT_CAPITAL,
    DEFAULT_MODE,
    MAX_SELECTED,
    RESEARCH_BPS,
    STRATEGY_ID,
)
from .momentum import is_eligible, momentum_252, rank_eligible, select_top
from .portfolio import shares_from_notional, target_notionals
from .rejection import first_failure


@dataclass
class Holding:
    symbol: str
    shares: float
    avg_cost: float
    entry_date: date
    entry_session_index: int


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


@dataclass
class BookState:
    cash: float = DEFAULT_CAPITAL
    initial_capital: float = DEFAULT_CAPITAL
    holdings: dict[str, Holding] = field(default_factory=dict)
    last_rebalance_index: int | None = None
    last_rebalance_date: date | None = None
    mode: str = DEFAULT_MODE
    session_index: int = -1


def _fill_price(close: float, *, side: str, bps: float = RESEARCH_BPS) -> float:
    if side == "buy":
        return close * (1.0 + bps)
    return close * (1.0 - bps)


def evaluate_session(
    *,
    session_index: int,
    last_rebalance_index: int | None,
    closes_t: dict[str, float | None],
    closes_t_minus_252: dict[str, float | None],
    universe: set[str],
    data_failures: set[str] | None = None,
    failed_closes: set[str] | None = None,
) -> dict[str, Any]:
    """Rank/select and assign first-failure for every considered name."""
    status, since, fire = clock_status(session_index, last_rebalance_index)
    failures = data_failures or set()
    missing_t = failed_closes or set()
    pairs: list[tuple[str, float]] = []
    rows: list[dict[str, Any]] = []

    considered = set(universe) | set(closes_t) | set(closes_t_minus_252) | failures
    for sym in sorted(considered):
        in_uni = sym in universe
        ct = None if sym in missing_t else closes_t.get(sym)
        prev = closes_t_minus_252.get(sym)
        mom = momentum_252(ct, prev) if in_uni else None
        if in_uni and mom is not None and is_eligible(mom):
            pairs.append((sym, mom))
        rows.append(
            {
                "symbol": sym,
                "in_universe": in_uni,
                "close_t": ct,
                "close_t_minus_252": prev,
                "momentum_252": mom,
                "data_source_failed": sym in failures,
            }
        )

    ranked = rank_eligible(pairs)
    selected = select_top(ranked, MAX_SELECTED)
    selected_set = {s for s, _m, _r in selected}
    rank_map = {s: r for s, _m, r in ranked}

    for row in rows:
        row["eligible_rank"] = rank_map.get(row["symbol"])
        row["selected"] = row["symbol"] in selected_set
        row["first_failure"] = first_failure(
            in_universe=row["in_universe"],
            close_t=row["close_t"],
            close_t_minus_252=row["close_t_minus_252"],
            data_source_failed=row["data_source_failed"],
            eligible_rank=row["eligible_rank"],
        )
        if status == "WARMUP":
            row["signal"] = "REJECT"
        elif row["selected"] and fire:
            row["signal"] = "BUY"
        elif row["selected"] and status == "MID_CYCLE":
            row["signal"] = "WATCH"
        else:
            row["signal"] = "REJECT"

    return {
        "strategy_id": STRATEGY_ID,
        "clock_status": status,
        "sessions_since_rebalance": since,
        "sessions_to_rebalance": sessions_to_rebalance(session_index, last_rebalance_index),
        "fire": fire,
        "ranked": ranked,
        "selected": selected,
        "rows": rows,
    }


def _mark_equity(state: BookState, prices: dict[str, float | None]) -> float:
    marked = 0.0
    for h in state.holdings.values():
        px = prices.get(h.symbol)
        if px is None:
            px = h.avg_cost
        marked += h.shares * float(px)
    return state.cash + marked


def _liquidate(
    state: BookState,
    prices: dict[str, float | None],
    on_date: date,
    reason: str,
    trades: list[Trade],
    *,
    bps: float = RESEARCH_BPS,
) -> list[dict[str, Any]]:
    exits: list[dict[str, Any]] = []
    for sym, h in list(state.holdings.items()):
        raw = prices.get(sym)
        if raw is None:
            raw = h.avg_cost
        fill = _fill_price(float(raw), side="sell", bps=bps)
        proceeds = h.shares * fill
        state.cash += proceeds
        pnl = (fill / h.avg_cost - 1.0) if h.avg_cost else 0.0
        trades.append(
            Trade(
                symbol=sym,
                entry_date=h.entry_date,
                exit_date=on_date,
                entry_price=h.avg_cost,
                exit_price=fill,
                shares=h.shares,
                pnl_pct=pnl,
                reason=reason,
                open=False,
            )
        )
        exits.append({"symbol": sym, "shares": h.shares, "reason": reason, "fill": fill})
    state.holdings.clear()
    return exits


def replay_book(
    dates: list[date],
    close_matrix: dict[str, dict[date, float]],
    universe: set[str],
    *,
    mode: str = DEFAULT_MODE,
    initial_capital: float = DEFAULT_CAPITAL,
    bps: float = RESEARCH_BPS,
    whole_shares: bool = False,
    unbuyable: set[str] | None = None,
) -> dict[str, Any]:
    """Replay the book on an aligned date list. Same filters as evaluate_session."""
    state = BookState(cash=initial_capital, initial_capital=initial_capital, mode=mode)
    trades: list[Trade] = []
    equity_curve: list[dict[str, Any]] = []
    cohorts: list[dict[str, Any]] = []
    skip = set(unbuyable or ())

    for i, dt in enumerate(dates):
        prices = {sym: close_matrix.get(sym, {}).get(dt) for sym in universe}
        for sym, series in close_matrix.items():
            if dt in series:
                prices[sym] = series[dt]
        is_last = i == len(dates) - 1
        status, _since, fire = clock_status(i, state.last_rebalance_index)

        if fire:
            prev_t = dates[i - 252] if i >= 252 else None
            closes_prev = {
                sym: (close_matrix.get(sym, {}).get(prev_t) if prev_t else None) for sym in set(prices)
            }
            ev = evaluate_session(
                session_index=i,
                last_rebalance_index=state.last_rebalance_index,
                closes_t=prices,
                closes_t_minus_252=closes_prev,
                universe=universe,
            )
            exits = _liquidate(state, prices, dt, "REBALANCE", trades, bps=bps)
            selected_syms = [s for s, _m, _r in ev["selected"]]
            buyable_skip = set(skip)
            for s in selected_syms:
                if prices.get(s) is None:
                    buyable_skip.add(s)
            notionals = target_notionals(
                selected=selected_syms,
                cash_after_sells=state.cash,
                equity=state.cash,
                mode=mode,
                skip=buyable_skip,
                whole_shares=whole_shares,
                prices={k: v for k, v in prices.items() if v is not None},
            )
            entries: list[dict[str, Any]] = []
            for sym, notional in notionals.items():
                raw = prices.get(sym)
                if raw is None:
                    continue
                fill = _fill_price(float(raw), side="buy", bps=bps)
                shares = shares_from_notional(notional, fill, whole_shares=whole_shares)
                if shares <= 0:
                    continue
                cost = shares * fill
                if cost > state.cash + 1e-9:
                    shares = shares_from_notional(state.cash, fill, whole_shares=whole_shares)
                    cost = shares * fill
                if shares <= 0:
                    continue
                state.cash -= cost
                state.holdings[sym] = Holding(
                    symbol=sym, shares=shares, avg_cost=fill, entry_date=dt, entry_session_index=i
                )
                entries.append({"symbol": sym, "shares": shares, "notional": cost, "fill": fill})
            state.last_rebalance_index = i
            state.last_rebalance_date = dt
            cohorts.append({"date": dt.isoformat(), "selected": selected_syms, "exits": exits, "entries": entries})
        elif is_last and state.holdings:
            _liquidate(state, prices, dt, "eod_liquidation", trades, bps=bps)

        state.session_index = i
        equity_curve.append(
            {
                "date": dt.isoformat(),
                "equity": _mark_equity(state, prices),
                "cash": state.cash,
                "clock_status": status if not fire else "REBALANCE",
            }
        )

    return {
        "state": state,
        "trades": trades,
        "equity_curve": equity_curve,
        "cohorts": cohorts,
    }


def snapshot_open_trades(state: BookState, prices: dict[str, float | None], asof: date) -> list[Trade]:
    open_trades: list[Trade] = []
    for h in state.holdings.values():
        raw = prices.get(h.symbol)
        mark = float(raw) if raw is not None else h.avg_cost
        pnl = (mark / h.avg_cost - 1.0) if h.avg_cost else 0.0
        open_trades.append(
            Trade(
                symbol=h.symbol,
                entry_date=h.entry_date,
                exit_date=None,
                entry_price=h.avg_cost,
                exit_price=mark,
                shares=h.shares,
                pnl_pct=pnl,
                reason="open_mtm",
                open=True,
            )
        )
    return open_trades
