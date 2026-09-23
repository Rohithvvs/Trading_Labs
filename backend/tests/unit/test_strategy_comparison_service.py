"""Unit tests for Strategy Comparison composition (no backtest re-run)."""

from __future__ import annotations

from app.services.strategy_comparison.comparison_service import (
    SOURCE_INDICATOR,
    _apply_equity_averages,
    _detect_source,
    config_mismatches,
    extract_indicator_logic,
    extract_logic,
    metrics_from_lean,
    metrics_from_strategy_run,
    monthly_yearly_from_equity,
    radar_profile,
    signal_comparison,
    trade_distribution,
)


def test_extract_logic_from_builder_snapshot():
    snapshot = {
        "name": "Momentum",
        "universe": "ALL_755",
        "timeframe": "1D",
        "side": "LONG",
        "filters": [
            {"id": "f1", "field": "CLOSE", "operator": ">", "value": {"indicator": "SMA", "period": 50}},
            {"id": "f2", "field": "RSI", "operator": ">", "value": 55},
        ],
        "position_rules": {
            "side": "LONG",
            "entry_rule": "WINDOW_START",
            "exit_rule": "WINDOW_END",
            "stop_loss_pct": 5,
            "target_pct": 10,
            "trailing_stop_pct": 3,
        },
        "source": {"type": "builder"},
    }
    logic = extract_logic(snapshot)
    assert logic["position_type"] == "LONG"
    assert logic["stop_loss"] == "5%"
    assert logic["take_profit"] == "10%"
    assert logic["trailing_stop"] == "3%"
    assert logic["pine_code"] is None
    joined = " ".join(logic["entry_conditions"]).upper()
    assert "CLOSE" in joined or "SMA" in joined
    assert "RSI" in joined
    assert any("SMA" in i.upper() for i in logic["indicators"])
    assert any("Window End" in c for c in logic["exit_conditions"])


def test_extract_logic_includes_pine_code():
    snapshot = {
        "name": "Pine Strat",
        "filters": [{"id": "f1", "field": "CLOSE", "operator": ">", "value": {"indicator": "SMA", "period": 50}}],
        "source": {"type": "pine", "pine_code": "//@version=6\nstrategy('x')\n"},
        "position_rules": {"side": "SHORT"},
    }
    logic = extract_logic(snapshot)
    assert logic["source_type"] == "pine"
    assert "strategy('x')" in logic["pine_code"]
    assert logic["position_type"] == "SHORT"


def test_config_mismatches_detects_different_universes_and_dates():
    warnings = config_mismatches(
        [
            {
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "universe": "ALL_755",
                "timeframe": "1D",
                "initial_capital": 100000,
                "commission": None,
                "slippage": None,
                "position_type": "LONG",
            },
            {
                "start_date": "2025-01-01",
                "end_date": "2024-12-31",
                "universe": "NIFTY500",
                "timeframe": "1D",
                "initial_capital": 100000,
                "commission": 0.0005,
                "slippage": None,
                "position_type": "LONG",
            },
        ]
    )
    fields = {w["field"] for w in warnings}
    assert "start_date" in fields
    assert "universe" in fields
    assert "commission" in fields
    assert "timeframe" not in fields
    assert "position_type" not in fields


def test_signal_comparison_overlap_and_only_sets():
    payload = signal_comparison(
        [
            {
                "slot_id": "s0",
                "signals": [
                    {"symbol": "RELIANCE", "signal": "BUY"},
                    {"symbol": "TCS", "signal": "BUY"},
                    {"symbol": "INFY", "signal": "WATCH"},
                    {"symbol": "WIPRO", "signal": "REJECT"},
                ],
            },
            {
                "slot_id": "s1",
                "signals": [
                    {"symbol": "RELIANCE", "signal": "BUY"},
                    {"symbol": "HDFCBANK", "signal": "BUY"},
                    {"symbol": "INFY", "signal": "BUY"},
                ],
            },
        ]
    )
    assert payload["available"] is True
    pair = payload["pairwise"][0]
    assert pair["shared_buy"] == ["RELIANCE"]
    assert pair["left_only_buy"] == ["TCS"]
    assert "HDFCBANK" in pair["right_only_buy"]
    assert pair["overlap_pct"] is not None
    by_symbol = {row["symbol"]: row["signals"] for row in payload["symbols"]}
    assert by_symbol["RELIANCE"]["s0"] == "BUY"
    assert by_symbol["RELIANCE"]["s1"] == "BUY"
    assert by_symbol["INFY"]["s0"] == "WATCH"
    assert by_symbol["INFY"]["s1"] == "BUY"


def test_signal_comparison_unavailable_with_one_slot():
    payload = signal_comparison([{"slot_id": "s0", "signals": [{"symbol": "RELIANCE", "signal": "BUY"}]}])
    assert payload["available"] is False
    assert payload["pairwise"] == []


def test_monthly_yearly_from_equity_uses_only_provided_session_points():
    equity = [
        {"date": "2024-01-02", "equity": 100000},
        {"date": "2024-01-31", "equity": 101000},
        {"date": "2024-02-01", "equity": 101000},
        {"date": "2024-02-29", "equity": 99000},
        {"date": "2025-01-02", "equity": 110000},
    ]
    periods = monthly_yearly_from_equity(equity)
    months = {row["period"]: row["return_pct"] for row in periods["monthly"]}
    assert "2024-01" in months
    assert months["2024-01"] == 1.0
    years = {row["period"] for row in periods["yearly"]}
    assert "2024" in years
    assert "2025" in years
    # No Saturday/Sunday invented — only the five supplied session dates.
    assert len(periods["monthly"]) == 3


def test_trade_distribution_buckets_real_returns_only():
    dist = trade_distribution([12.0, 6.0, 1.0, 0.0, -3.0, -8.0, -15.0, None])
    by_key = {row["bucket"]: row["count"] for row in dist}
    assert by_key["gt_10"] == 1
    assert by_key["pos5_10"] == 1
    assert by_key["pos0_5"] == 1
    assert by_key["eq_0"] == 1
    assert by_key["neg5_0"] == 1
    assert by_key["neg10_neg5"] == 1
    assert by_key["lt_neg10"] == 1


class _FakeRun:
    summary = {"win_rate": 40.0, "average_return": 1.5, "top_return": 12.0, "worst_return": -8.0}
    buy_count = 2
    initial_capital = 100000.0
    strategy_snapshot = {"position_rules": {"side": "LONG"}}


class _FakeResult:
    def __init__(self, symbol, return_pct):
        self.symbol = symbol
        self.return_pct = return_pct
        self.entry_price = 100.0
        self.exit_price = 100.0 + return_pct
        self.status = "ok"
        self.signal = "BUY"


def test_strategy_tester_metrics_do_not_invent_sharpe_or_cagr():
    results = [_FakeResult("AAA", 12.0), _FakeResult("BBB", -8.0)]
    metrics = metrics_from_strategy_run(_FakeRun(), results)
    assert metrics["metrics_source"] == "strategy_tester"
    assert metrics["win_rate"] == 40.0
    assert metrics["average_trade"] == 1.5
    assert metrics["cagr"] is None
    assert metrics["sharpe_ratio"] is None
    assert metrics["sortino_ratio"] is None
    assert metrics["net_profit"] is None
    assert metrics["final_equity"] is None
    assert metrics["max_drawdown"] is None
    assert metrics["profit_factor"] is None
    assert metrics["best_trade"]["symbol"] == "AAA"
    assert metrics["worst_trade"]["symbol"] == "BBB"


def test_radar_uses_scan_metrics_without_inventing_sharpe():
    profile = radar_profile(
        [
            {
                "slot_id": "s0",
                "strategy_name": "A",
                "metrics": {"win_rate": 40.0, "total_return_pct": 1.5, "sharpe_ratio": None},
            },
            {
                "slot_id": "s1",
                "strategy_name": "B",
                "metrics": {"win_rate": 55.0, "total_return_pct": 3.0, "sharpe_ratio": None},
            },
        ]
    )
    keys = {axis["key"] for axis in profile["axes"]}
    assert "win_rate" in keys
    assert "total_return_pct" in keys
    assert "sharpe_ratio" not in keys
    assert "not a ranking" in profile["note"].lower()
    raw_a = profile["series"][0]["raw"]
    assert raw_a["win_rate"] == 40.0
    assert raw_a["sharpe_ratio"] is None


def test_radar_builds_hexagon_from_scan_summary():
    profile = radar_profile(
        [
            {
                "slot_id": "s0",
                "strategy_name": "A",
                "metrics": {
                    "win_rate": 40.0,
                    "total_return_pct": 1.5,
                    "average_trade": 1.5,
                    "total_trades": 12,
                    "sharpe_ratio": None,
                    "profit_factor": None,
                    "cagr": None,
                    "max_drawdown_pct": None,
                    "best_trade": {"symbol": "AAA", "return_pct": 12.0},
                },
                "scan_summary": {"buy": 8, "watch": 3, "reject": 40},
            },
            {
                "slot_id": "s1",
                "strategy_name": "B",
                "metrics": {
                    "win_rate": 55.0,
                    "total_return_pct": 3.0,
                    "average_trade": 3.0,
                    "total_trades": 6,
                    "sharpe_ratio": None,
                    "profit_factor": None,
                    "cagr": None,
                    "max_drawdown_pct": None,
                    "best_trade": {"symbol": "BBB", "return_pct": 8.0},
                },
                "scan_summary": {"buy": 4, "watch": 6, "reject": 20},
            },
        ]
    )
    keys = [axis["key"] for axis in profile["axes"]]
    assert keys == ["win_rate", "total_return_pct", "best_trade", "total_trades", "buy_count", "watch_count"]
    assert "sharpe_ratio" not in keys
    assert "average_trade" not in keys
    assert profile["series"][0]["raw"]["buy_count"] == 8.0
    assert profile["series"][0]["values"]["buy_count"] == 100.0
    assert profile["series"][1]["values"]["buy_count"] == 50.0


def test_lean_metrics_keep_calmar_and_equity_averages():
    class _Summary:
        def model_dump(self):
            return {
                "netProfitPct": 12.0,
                "cagr": 8.0,
                "winRate": 55.0,
                "totalTrades": 10,
                "profitFactor": 1.4,
                "averageTrade": 1.1,
                "maximumDrawdownPct": 10.0,
                "calmarRatio": 0.8,
                "finalEquity": 112000,
                "initialCapital": 100000,
            }

    metrics = metrics_from_lean(_Summary(), [])
    assert metrics["calmar_ratio"] == 0.8
    filled = _apply_equity_averages(
        metrics,
        [
            {"cash": 90000, "invested": 10000},
            {"cash": 70000, "invested": 30000},
        ],
    )
    assert filled["avg_cash"] == 80000.0
    assert filled["avg_exposure_pct"] == 20.0


def test_extract_indicator_logic():
    class DummyIndicator:
        source_code = "//@version=6\nindicator('52W')\nbuy = close > ta.highest(high, 252)"
        parsed_definition = {
            "entry_conditions": ["close > ta.highest(high, 252)"],
            "inputs": [{"name": "lookback", "type": "int"}],
            "outputs": [{"name": "signal", "type": "bool"}],
        }

    logic = extract_indicator_logic(DummyIndicator())
    assert logic["source_type"] == "pine"
    assert logic["entry_conditions"] == ["close > ta.highest(high, 252)"]
    assert "lookback" in logic["indicators"]
    assert "signal" in logic["indicators"]
    assert logic["position_type"] == "LONG"


def test_detect_source_for_indicator_scan():
    assert _detect_source("IND-20260922-001", None) == SOURCE_INDICATOR
    assert _detect_source("STR-20260922-001", None) == "strategy_tester"
    assert _detect_source("LEAN-12345", None) == "lean"
    assert _detect_source("custom-1", SOURCE_INDICATOR) == SOURCE_INDICATOR

