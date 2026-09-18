"""Stored 52W Strategy Tester metrics from closed-trade replay."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.strategies.breakout52w.analytics import build_symbol_dashboard
from app.services.strategies.breakout52w.identity import STRATEGY_ID
from app.services.strategies.breakout52w.performance_store import (
    TESTER_FIELDS,
    apply_stored_metrics,
    collect_symbol_performance,
    dashboard_from_stored,
    get_symbol_performance,
    list_symbol_performance,
    load_stored_dashboard,
    metrics_from_dashboard,
    persist_dashboard,
    row_to_dict,
    strategy_tester_payload,
    upsert_symbol_performance,
    windows_from_all_dashboard,
)


def _t(entry: str, exit: str | None, pnl: float, *, open_: bool = False, symbol: str = "IIFL-EQ") -> dict:
    return {
        "symbol": symbol,
        "entry_date": entry,
        "exit_date": exit,
        "entry_price": 100.0,
        "exit_price": None if open_ else 100.0 * (1 + pnl),
        "shares": 1.0,
        "pnl_pct": 0.0 if open_ else pnl,
        "reason": "open_mtm" if open_ else "atr_trail",
        "open": open_,
        "net_pnl": 0.0 if open_ else pnl * 100.0,
        "commission": 0.0,
        "gross_pnl": 0.0 if open_ else pnl * 100.0,
    }


BLOTTER = [
    _t("2021-02-09", "2021-03-25", 0.2725),
    _t("2022-04-27", "2022-05-09", -0.1959),
    _t("2022-10-27", "2022-12-23", 0.1045),
    _t("2023-07-10", "2023-08-14", 0.0382),
    _t("2023-10-16", "2023-10-26", -0.1110),
    _t("2025-10-30", "2026-01-22", -0.0054),
    _t("2026-08-21", None, 0.0, open_=True),
]


def _dash(blotter=BLOTTER, *, window="ALL", start=None, end=None):
    return build_symbol_dashboard(
        {
            "strategy_id": STRATEGY_ID,
            "evaluation_date": "2026-08-21",
            "recommendations": [{"symbol": "IIFL-EQ", "signal": "BUY"}],
        },
        "IIFL-EQ",
        window,
        blotter=blotter,
        asof=date(2026, 8, 21),
        initial_capital=100000,
        symbol_replay=True,
        window_start=start,
        window_end=end,
    )


def test_tester_fields_cover_requested_metrics():
    assert TESTER_FIELDS == (
        "total_pnl",
        "max_drawdown",
        "total_trades",
        "profitable_trades",
        "losing_trades",
        "breakeven",
        "profit_factor",
        "gross_profit",
        "gross_loss",
        "commission",
        "expected_payoff",
        "largest_profit",
        "largest_loss",
        "average_winning_trade",
        "average_losing_trade",
        "outlier_pnl",
    )


def test_metrics_from_closed_trades_match_ledger():
    dash = _dash(start=date(2008, 8, 21), end=date(2026, 8, 21))
    stored = metrics_from_dashboard(dash)
    dist = dash["trade_distribution"]
    ledger = dash["ledger"]
    assert stored["total_trades"] == 6
    assert stored["profitable_trades"] == 3
    assert stored["losing_trades"] == 3
    assert stored["breakeven"] == 0
    assert stored["profitable_trades"] + stored["losing_trades"] + stored["breakeven"] == stored["total_trades"]
    assert stored["total_pnl"] == ledger["net_pnl"]
    assert stored["gross_profit"] == ledger["gross_profit"]
    assert stored["gross_loss"] == ledger["gross_loss"]
    assert stored["expected_payoff"] == ledger["expected_payoff"]
    assert stored["largest_profit"] == ledger["largest_profit"]
    assert stored["largest_loss"] == ledger["largest_loss"]
    assert stored["average_winning_trade"] == ledger["average_profit"]
    assert stored["average_losing_trade"] == ledger["average_loss"]
    assert stored["outlier_pnl"] == ledger["outlier_pnl"]
    assert stored["commission"] == ledger["commission"]
    assert stored["source"] == "closed_trade_ledger"
    tester = strategy_tester_payload(stored)
    assert tester["total_trades"] == dist["total_trades"] == 6
    assert tester["profitable_trades"] == 3
    assert tester["losing_trades"] == 3
    assert tester["breakeven"] == 0
    assert set(tester) == set(TESTER_FIELDS)


def test_open_mark_is_not_a_profit_or_loss_trade():
    stored = metrics_from_dashboard(_dash())
    assert stored["total_trades"] == 6
    assert stored["profitable_trades"] + stored["losing_trades"] + stored["breakeven"] == 6


def test_window_slice_from_one_all_replay():
    all_dash = _dash(window="ALL", start=date(2008, 8, 21), end=date(2026, 8, 21))
    all_dash["data_hash"] = "abc123"
    all_dash["execution"] = {"profile": "KERNEL"}
    rows = windows_from_all_dashboard(
        all_dash, ("1Y", "5Y", "18Y", "ALL"), asof=date(2026, 8, 21)
    )
    by_window = {r["window"]: r for r in rows}
    assert by_window["1Y"]["total_trades"] == 1
    assert by_window["5Y"]["total_trades"] == 5
    assert by_window["18Y"]["total_trades"] == 6
    assert by_window["ALL"]["total_trades"] == 6
    assert by_window["ALL"]["data_hash"] == "abc123"
    assert by_window["1Y"]["profitable_trades"] + by_window["1Y"]["losing_trades"] == 1


def test_apply_stored_metrics_overrides_dashboard():
    dash = _dash()
    stored = metrics_from_dashboard(dash)
    stored["total_pnl"] = 12.5
    stored["profitable_trades"] = 3
    overlaid = apply_stored_metrics(dash, stored)
    assert overlaid["persisted"] is True
    assert overlaid["net_pnl"] == 12.5
    assert overlaid["strategy_tester"]["total_pnl"] == 12.5
    assert overlaid["ledger"]["winning_trades"] == 3
    assert overlaid["trade_distribution"]["winners"] == 3


def test_dashboard_from_stored_rebuilds_tester_panel():
    stored = metrics_from_dashboard(_dash(start=date(2018, 8, 21), end=date(2026, 8, 21)))
    dash = dashboard_from_stored(stored, signal="BUY", asof=date(2026, 8, 21))
    assert dash["persisted"] is True
    assert dash["strategy_tester"]["total_trades"] == 6
    assert dash["strategy_tester"]["profitable_trades"] == 3
    assert dash["strategy_tester"]["losing_trades"] == 3
    assert dash["trade_count"] == 6


@pytest.mark.asyncio
async def test_upsert_and_load_roundtrip(test_engine):
    dash = _dash(start=date(2018, 8, 21), end=date(2026, 8, 21))
    stored = await persist_dashboard(dash)
    row = await get_symbol_performance("IIFL-EQ", stored["window"])
    assert row is not None
    assert row.total_trades == 6
    assert row.profitable_trades == 3
    assert row.losing_trades == 3
    assert row.breakeven == 0
    assert row.total_pnl == stored["total_pnl"]
    assert row.source == "closed_trade_ledger"
    loaded = await load_stored_dashboard("IIFL-EQ", stored["window"], signal="HOLD")
    assert loaded is not None
    assert loaded["persisted"] is True
    assert loaded["strategy_tester"]["total_trades"] == 6
    assert loaded["signal"] == "HOLD"


@pytest.mark.asyncio
async def test_upsert_replaces_same_window(test_engine):
    first = metrics_from_dashboard(_dash())
    first["window"] = "ALL"
    first["total_pnl"] = 1.0
    await upsert_symbol_performance(first)
    first["total_pnl"] = 99.0
    first["total_trades"] = 6
    await upsert_symbol_performance(first)
    rows = await list_symbol_performance("IIFL-EQ")
    assert len(rows) == 1
    assert rows[0].total_pnl == 99.0


@pytest.mark.asyncio
async def test_collect_symbol_uses_one_all_replay(test_engine):
    all_dash = _dash(window="ALL", start=date(2008, 8, 21), end=date(2026, 8, 21))
    all_dash["data_hash"] = "hash-1"
    all_dash["execution"] = {"profile": "KERNEL"}

    async def _run(*_args, **_kwargs):
        return all_dash

    with patch(
        "app.services.strategies.breakout52w.window_backtest.run_symbol_window_backtest",
        new=AsyncMock(side_effect=_run),
    ), patch(
        "app.services.strategies.breakout52w.window_backtest.load_symbol_window_bars",
        new=AsyncMock(return_value=([], {}, {}, {}, {}, {}, {})),
    ):
        result = await collect_symbol_performance(
            "IIFL-EQ",
            asof=date(2026, 8, 21),
            windows=("1Y", "ALL"),
            force=True,
        )
    assert result["status"] == "stored"
    all_row = await get_symbol_performance("IIFL-EQ", "ALL")
    one_y = await get_symbol_performance("IIFL-EQ", "1Y")
    assert all_row is not None and one_y is not None
    assert all_row.total_trades == 6
    assert one_y.total_trades == 1
    assert all_row.profitable_trades == 3
    assert all_row.losing_trades == 3


@pytest.mark.asyncio
async def test_collect_skips_matching_hash(test_engine):
    dash = _dash(window="ALL", start=date(2008, 8, 21), end=date(2026, 8, 21))
    dash["data_hash"] = "same-hash"
    await persist_dashboard(dash)
    replay = AsyncMock()
    with patch(
        "app.services.strategies.breakout52w.window_backtest.load_symbol_window_bars",
        new=AsyncMock(return_value=([], {}, {"IIFL-EQ": {}}, {}, {}, {}, {})),
    ), patch(
        "app.services.strategies.breakout52w.window_backtest.dataset_fingerprint",
        return_value={"data_hash": "same-hash"},
    ), patch(
        "app.services.strategies.breakout52w.window_backtest.run_symbol_window_backtest",
        new=replay,
    ):
        result = await collect_symbol_performance("IIFL-EQ", asof=date(2026, 8, 21), force=False)
    assert result["status"] == "skipped"
    replay.assert_not_awaited()


def test_get_w52_symbol_serves_stored_dashboard():
    from app.routes.scanner import get_w52_symbol

    stored_dash = _dash()
    stored_dash["persisted"] = True
    stored_dash["strategy_tester"] = strategy_tester_payload(metrics_from_dashboard(stored_dash))
    latest = SimpleNamespace(
        payload={
            "evaluation_date": "2026-08-21",
            "recommendations": [{"symbol": "IIFL-EQ", "signal": "BUY", "technicals": {"atr": 1}}],
            "initial_capital": 100000,
        }
    )
    replay = AsyncMock()

    async def _run():
        with (
            patch(
                "app.services.strategies.breakout52w.persistence.load_latest",
                new=AsyncMock(return_value=latest),
            ),
            patch(
                "app.services.strategies.breakout52w.performance_store.load_stored_dashboard",
                new=AsyncMock(return_value=stored_dash),
            ),
            patch(
                "app.services.strategies.breakout52w.window_backtest.run_symbol_window_backtest",
                new=replay,
            ),
        ):
            return await get_w52_symbol(
                "IIFL-EQ",
                window="ALL",
                start_date=None,
                end_date=None,
                execution_profile=None,
                historical_fill_mode=None,
                refresh=False,
                _=SimpleNamespace(),
            )

    body = asyncio.run(_run())
    replay.assert_not_awaited()
    assert body["persisted"] is True
    assert body["strategy_tester"]["total_trades"] == 6
    assert body["dashboard"]["trade_distribution"]["winners"] == 3
    assert body["dashboard"]["trade_distribution"]["losers"] == 3


def test_get_w52_symbol_tv_tester_uses_tester_capital():
    from app.routes.scanner import get_w52_symbol
    from app.services.strategies.breakout52w.execution import TV_TESTER_CAPITAL

    latest = SimpleNamespace(
        payload={
            "evaluation_date": "2026-08-24",
            "recommendations": [{"symbol": "WELCORP-EQ", "signal": "BUY", "technicals": {}}],
            "initial_capital": 100000,
        }
    )
    replay = AsyncMock(return_value={"window": "ALL", "trade_count": 2954, "execution": {"profile": "TV_TESTER"}})

    async def _run():
        with (
            patch(
                "app.services.strategies.breakout52w.persistence.load_latest",
                new=AsyncMock(return_value=latest),
            ),
            patch(
                "app.services.strategies.breakout52w.performance_store.load_stored_dashboard",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.strategies.breakout52w.performance_store.persist_dashboard",
                new=AsyncMock(),
            ),
            patch(
                "app.services.strategies.breakout52w.window_backtest.run_symbol_window_backtest",
                new=replay,
            ),
        ):
            return await get_w52_symbol(
                "WELCORP-EQ",
                window="ALL",
                start_date="2000-06-23",
                end_date="2026-08-24",
                execution_profile="TV_TESTER",
                historical_fill_mode=None,
                refresh=False,
                _=SimpleNamespace(),
            )

    body = asyncio.run(_run())
    replay.assert_awaited()
    kwargs = replay.await_args.kwargs
    assert kwargs["initial_capital"] == TV_TESTER_CAPITAL
    assert kwargs["execution_profile"] == "TV_TESTER"
    assert body["window"] == "ALL"


def test_row_to_dict_exposes_tester_block():
    stored = metrics_from_dashboard(_dash())
    skip = {
        "strategy_tester",
        "period_start",
        "period_end",
        "evaluation_date",
        "strategy_id",
        "symbol",
        "window",
        "execution_profile",
    }
    fake = SimpleNamespace(
        **{k: stored.get(k) for k in stored if k not in skip},
        computed_at=None,
        period_start=date(2008, 8, 21),
        period_end=date(2026, 8, 21),
        evaluation_date=date(2026, 8, 21),
        strategy_id=STRATEGY_ID,
        symbol="IIFL-EQ",
        window="ALL",
        execution_profile="KERNEL",
    )
    out = row_to_dict(fake)
    assert out["strategy_tester"]["profitable_trades"] == stored["profitable_trades"]
    assert out["period_start"] == "2008-08-21"
