"""Isolated TradingView TEST-tape replay.

Always-in long, qty from ExecutionConfig (default 1), signal at bar close,
fill at next session open, flatten at the following session open. Same-bar
re-entry fills are blocked (next entry is the session after the exit).

Not used by the 52W scanner. Does not import 52W signal or prior-high helpers.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .book_engine import (
    BookState,
    Holding,
    _account_exit,
    _mark_equity,
    _trade_id,
)
from .costs import apply_buy, apply_sell
from .execution import (
    ExecutionConfig,
    ExecutionDiagnostics,
    TV_TESTER_EXECUTION,
    apply_slippage,
    bar_from_maps,
    entry_fill_price,
    round_to_tick,
)
from .identity import DEFAULT_CAPITAL
from .portfolio import shares_for_order

TEST_ENTRY_SIGNAL = "TEST"
TEST_EXIT_REASON = "Close entry(s) order TEST"


def replay_tv_tester_tape(
    dates: list[date],
    high_m: dict[str, dict[date, float]],
    low_m: dict[str, dict[date, float]],
    close_m: dict[str, dict[date, float]],
    vol_m: dict[str, dict[date, float]],
    index: dict[date, float],
    universe: set[str],
    *,
    initial_capital: float = DEFAULT_CAPITAL,
    open_m: dict[str, dict[date, float]] | None = None,
    execution: ExecutionConfig | None = None,
    backtest_id: str | None = None,
    lower_tf: dict[str, list[dict[str, Any]]] | None = None,
    whole_shares: bool = False,
    unbuyable: set[str] | None = None,
    delisted: set[str] | None = None,
    session_dates: set[date] | None = None,
) -> dict[str, Any]:
    del lower_tf, unbuyable, delisted  # unused; signature matches replay_book callers
    cfg = execution or TV_TESTER_EXECUTION
    open_m = open_m or {}
    diagnostics = ExecutionDiagnostics()
    bt_id = backtest_id or "tv-tester-tape"
    symbols = sorted(universe)
    trades: list = []
    equity_curve: list[dict[str, Any]] = []
    state = BookState(cash=float(initial_capital), initial_capital=float(initial_capital))
    pending_entry: dict[str, date] = {}
    pending_exit: set[str] = set()
    skipped_sessions = 0

    def _is_session(day: date) -> bool:
        return session_dates is None or day in session_dates

    def _has_later_session(idx: int) -> bool:
        for later in dates[idx + 1 :]:
            if _is_session(later):
                return True
        return False

    def _fill_px(raw: float, *, side: str) -> float:
        rounded = round_to_tick(float(raw), cfg.tick_size)
        return apply_slippage(rounded, side=side, rate=cfg.slippage_rate)

    def _qty(fill: float) -> float:
        return shares_for_order(
            fill,
            order_size_type=cfg.order_size_type,
            default_order_size=cfg.default_order_size,
            equity=state.cash,
            cash=state.cash,
            alloc_pct=cfg.alloc_pct,
            apply_costs=cfg.apply_costs,
            whole_shares=whole_shares,
        )

    for i, dt in enumerate(dates):
        if not _is_session(dt):
            skipped_sessions += 1
            continue
        state.session_index = i
        state.last_session = dt
        state.sold_today = set()
        has_next = _has_later_session(i)
        prices: dict[str, float | None] = {}

        for symbol in symbols:
            bar = bar_from_maps(
                symbol,
                dt,
                open_m=open_m,
                high_m=high_m,
                low_m=low_m,
                close_m=close_m,
                vol_m=vol_m,
            )
            prices[symbol] = bar.close

            holding = state.holdings.get(symbol)
            if holding is not None and symbol in pending_exit:
                fill = entry_fill_price(
                    bar, cfg=cfg, signal_close=holding.entry_price, diagnostics=diagnostics
                )
                if fill is None:
                    diagnostics.skipped_pending_entries += 1
                    pending_exit.discard(symbol)
                else:
                    px = _fill_px(float(fill), side="SELL")
                    turnover = holding.shares * px
                    if cfg.apply_costs:
                        state.cash = apply_sell(state.cash, turnover)
                    else:
                        state.cash += turnover
                    tr = _account_exit(
                        holding,
                        exit_date=dt,
                        exit_price=px,
                        reason=TEST_EXIT_REASON,
                        cfg=cfg,
                        canonical=TEST_EXIT_REASON,
                        exit_order_time=holding.entry_date,
                    )
                    tr.trade_id = _trade_id(symbol, holding.entry_date, dt, TEST_EXIT_REASON)
                    tr.entry_signal = TEST_ENTRY_SIGNAL
                    trades.append(tr)
                    state.holdings.pop(symbol, None)
                    state.lifecycle[symbol] = "FLAT"
                    pending_exit.discard(symbol)
                    state.sold_today.add(symbol)

            holding = state.holdings.get(symbol)
            if holding is None and symbol in pending_entry:
                same_bar_block = symbol in state.sold_today and not cfg.allow_same_bar_reentry
                if same_bar_block:
                    pass  # keep pending_entry for the next session
                else:
                    fill = entry_fill_price(bar, cfg=cfg, signal_close=None, diagnostics=diagnostics)
                    if fill is None:
                        diagnostics.skipped_pending_entries += 1
                        pending_entry.pop(symbol, None)
                    else:
                        exec_px = _fill_px(float(fill), side="BUY")
                        sh = _qty(exec_px)
                        if sh > 0:
                            turnover = sh * exec_px
                            if cfg.apply_costs:
                                state.cash = apply_buy(state.cash, turnover)
                            else:
                                state.cash -= turnover
                            signal_date = pending_entry.pop(symbol)
                            state.holdings[symbol] = Holding(
                                symbol=symbol,
                                shares=sh,
                                entry_date=dt,
                                entry_session_index=i,
                                entry_price=exec_px,
                                hwm=exec_px,
                                tsl=exec_px,
                                signal_date=signal_date,
                                signal_price=exec_px,
                                entry_order_time=signal_date,
                                buy_commission=0.0,
                                entry_slippage=abs(exec_px - float(fill)) * sh,
                                lifecycle="LONG",
                            )
                            state.lifecycle[symbol] = "LONG"
                        else:
                            pending_entry.pop(symbol, None)

            holding = state.holdings.get(symbol)
            if holding is not None and symbol not in pending_exit:
                if has_next or not cfg.skip_on_missing_next_bar:
                    pending_exit.add(symbol)

            if state.holdings.get(symbol) is None and symbol not in pending_entry:
                if has_next:
                    pending_entry[symbol] = dt
                    state.lifecycle[symbol] = "ENTRY_PENDING"

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
        "successful_symbols": sorted({t.symbol for t in trades} | set(state.holdings) | set(universe)),
        "total_symbols": len(universe),
        "incomplete": bool(diagnostics.failed_symbols),
        "replay_kind": "tv_tester_tape",
        "backtest_id": bt_id,
        "skipped_sessions": skipped_sessions,
    }
