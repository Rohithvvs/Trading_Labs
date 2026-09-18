"""Deterministic Strategy Tester: indicators, filters, signals, returns, isolation."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.strategy_tester.analytics import independent_filter_stats, sequential_funnel, summarize_results
from app.services.strategy_tester.engine import evaluate_stock
from app.services.strategy_tester.filter_engine import evaluate_tree
from app.services.strategy_tester.indicators import BarSeries, atr, ema, macd_components, rsi, sma
from app.services.strategy_tester.presets import PRESETS
from app.services.strategy_tester.returns import simple_return
from app.services.strategy_tester.schema import PositionRules, parse_strategy_config
from app.services.strategy_tester.signals import BUY, REJECT, WATCH


def _dates(n: int, start: date = date(2024, 1, 2)) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _series(
    n: int = 250,
    *,
    start_px: float = 100.0,
    step: float = 0.4,
    volume: float = 1000.0,
) -> BarSeries:
    dates = _dates(n)
    close = [start_px + i * step for i in range(n)]
    high = [c + 1 for c in close]
    low = [c - 1 for c in close]
    open_px = list(close)
    vol = [volume + (i % 5) * 10 for i in range(n)]
    return BarSeries(dates=dates, open=open_px, high=high, low=low, close=close, volume=vol)


def test_sma_ema_rsi_macd_atr_are_deterministic_and_have_no_lookahead():
    values = [float(i) for i in range(1, 21)]
    s = sma(values, 5)
    assert s[3] is None
    assert s[4] == 3.0  # (1+2+3+4+5)/5
    assert s[5] == 4.0
    # Look-ahead: later spike must not change earlier SMA
    spiked = list(values)
    spiked[-1] = 10_000.0
    s2 = sma(spiked, 5)
    assert s2[4] == s[4]
    e = ema(values, 3)
    assert e[2] is not None
    assert e[-1] is not None
    r = rsi(values, 5)
    assert r[5] is not None
    assert 0 <= r[-1] <= 100
    line, signal, hist = macd_components(values + [x * 1.01 for x in values])
    assert any(v is not None for v in line)
    highs = [v + 1 for v in values]
    lows = [v - 1 for v in values]
    a = atr(highs, lows, values, 5)
    assert a[-1] is not None and a[-1] > 0


def test_parse_frontend_builder_and_pine_filter_shapes():
    cfg = parse_strategy_config(
        {
            "name": "Momentum Strategy",
            "filters": [
                {
                    "id": "f1",
                    "field": "CLOSE",
                    "left": "CLOSE",
                    "operator": ">",
                    "value": {"indicator": "SMA", "period": 50},
                },
                {
                    "id": "f2",
                    "field": "SMA_50",
                    "left": {"indicator": "SMA", "period": 50},
                    "operator": ">",
                    "value": {"indicator": "SMA", "period": 200},
                },
                {"id": "f3", "field": "RSI_14", "left": {"indicator": "RSI", "period": 14}, "operator": ">", "value": 55},
                {
                    "id": "f4",
                    "field": "VOLUME",
                    "operator": ">",
                    "value": {"indicator": "AVG_VOLUME", "period": 20},
                },
            ],
        }
    )
    labels = [leaf.display_label() for leaf in cfg.root.leaf_nodes()]
    assert labels == [
        "Close > SMA 50",
        "SMA 50 > SMA 200",
        "Rsi 14 > 55",
        "Volume > Average Volume 20",
    ]

    pine = parse_strategy_config(
        {
            "name": "52-Week High Breakout",
            "filters": [
                {
                    "id": "b",
                    "field": "BENCHMARK_CLOSE",
                    "operator": ">",
                    "value": {"indicator": "SMA", "period": 50},
                },
                {"id": "h", "field": "CLOSE", "operator": ">=", "value": {"indicator": "HIGH", "period": 252}},
                {"id": "v", "field": "VOLUME", "operator": ">", "value": {"indicator": "AVG_VOLUME", "period": 20}},
            ],
        }
    )
    pine_labels = [leaf.display_label() for leaf in pine.root.leaf_nodes()]
    assert pine_labels[0].startswith("NIFTY 500 Close")
    assert "252 Day High" in pine_labels[1]

    rel = parse_strategy_config(
        {"name": "Rel vol", "filters": [{"id": "r", "field": "REL_VOLUME_20", "operator": ">", "value": 1.5}]}
    )
    assert rel.root.leaf_nodes()[0].left and rel.root.leaf_nodes()[0].left.period == 20


def test_high_without_period_is_todays_high_not_prior_252():
    """CLOSE >= HIGH with no period is today's high (the Pine input.int bug).

    TradingView `ta.highest(high, 252)[1]` is the prior 252-session high.
    Sending HIGH with no period made Labs require close == session high, which
    is why a 52-week scan returned 1 name instead of the TV screener's 14.
    """
    n = 270
    dates = _dates(n)
    close = [100.0] * n
    high = [101.0] * n
    low = [99.0] * n
    close[-1] = 105.0
    high[-1] = 108.0
    series = BarSeries(dates=dates, open=list(close), high=high, low=low, close=close, volume=[1_000.0] * n)
    t = n - 1

    todays_high = parse_strategy_config(
        {
            "name": "broken-high",
            "filters": [{"id": "h", "field": "CLOSE", "operator": ">=", "value": {"indicator": "HIGH"}}],
        }
    )
    prior_252 = parse_strategy_config(
        {
            "name": "tv-high",
            "filters": [{"id": "h", "field": "CLOSE", "operator": ">=", "value": {"indicator": "HIGH", "period": 252}}],
        }
    )
    assert evaluate_tree(todays_high.root, series, t).passed is False
    assert evaluate_tree(prior_252.root, series, t).passed is True
    assert series.value_at(prior_252.root.leaf_nodes()[0].right, t) == 101.0

    bench = BarSeries(
        dates=list(dates),
        open=[24000.0] * n,
        high=[24100.0] * n,
        low=[23900.0] * n,
        close=[24050.0] * n,
        volume=[0.0] * n,
    )
    row = evaluate_stock(
        symbol="AAA",
        company="Aaa",
        series=series,
        strategy=prior_252,
        start_date=dates[0],
        end_date=dates[-1],
        benchmark=bench,
    )
    assert row.signal == BUY
    assert row.evaluation_date == dates[-1]
    assert row.indicators.get("high_252") == 101.0
    assert row.indicators.get("close") == 105.0
    assert row.indicators.get("nifty500_close") == 24050.0
    assert row.exit_price == 105.0


def test_filter_operators_and_groups():
    series = _series(30, start_px=50, step=1)
    cfg = parse_strategy_config(
        {
            "name": "ops",
            "filters": {
                "op": "AND",
                "children": [
                    {"id": "gt", "field": "close", "operator": ">", "value": 10},
                    {
                        "id": "or_group",
                        "op": "OR",
                        "children": [
                            {"id": "rsi_hi", "field": "RSI", "operator": ">", "value": 90},
                            {"id": "close_sma", "field": "close", "operator": ">", "value": {"indicator": "SMA", "period": 5}},
                        ],
                    },
                    {
                        "id": "not_low",
                        "op": "NOT",
                        "children": [{"id": "lt", "field": "close", "operator": "<", "value": 1}],
                    },
                    {"id": "between", "field": "RSI", "operator": "between", "low": 0, "high": 100},
                ],
            },
        }
    )
    ev = evaluate_tree(cfg.root, series, len(series) - 1)
    assert ev.passed is True
    labels = {leaf.filter_id: leaf.passed for leaf in ev.leaves}
    assert labels["gt"] is True
    assert labels["lt"] is False


def test_cross_above_requires_prior_bar():
    dates = _dates(6)
    close = [10.0, 10.0, 10.0, 10.0, 12.0, 13.0]
    sma_flat = [11.0, 11.0, 11.0, 11.0, 11.0, 11.0]
    series = BarSeries(dates=dates, open=close, high=close, low=close, close=close, volume=[1] * 6)
    series.cache["SMA_3"] = sma_flat
    cfg = parse_strategy_config(
        {
            "name": "cross",
            "filters": [{"id": "x", "field": "close", "operator": "cross_above", "value": {"indicator": "SMA", "period": 3}}],
        }
    )
    before = evaluate_tree(cfg.root, series, 3)
    assert before.leaves[0].passed is False
    after = evaluate_tree(cfg.root, series, 4)
    assert after.leaves[0].passed is True


def test_signal_buy_watch_reject():
    series = _series(220)
    buy_cfg = parse_strategy_config(
        {
            "name": "Momentum Strategy",
            "filters": [
                {"field": "close", "operator": ">", "value": {"indicator": "SMA", "period": 50}},
                {"field": "SMA_50", "operator": ">", "value": {"indicator": "SMA", "period": 200}},
            ],
        }
    )
    result = evaluate_stock(
        symbol="AAA-EQ",
        company="Aaa",
        series=series,
        strategy=buy_cfg,
        start_date=series.dates[10],
        end_date=series.dates[-1],
    )
    assert result.signal == BUY
    assert result.status == "ok"
    assert result.return_pct is not None and result.return_pct > 0

    reject_cfg = parse_strategy_config(
        {
            "name": "Impossible",
            "filters": [
                {"field": "close", "operator": "<", "value": 0},
                {"field": "RSI", "operator": "<", "value": 0},
            ],
        }
    )
    rejected = evaluate_stock(
        symbol="BBB-EQ",
        company="Bbb",
        series=series,
        strategy=reject_cfg,
        start_date=series.dates[10],
        end_date=series.dates[-1],
    )
    assert rejected.signal == REJECT
    assert rejected.failed_filters

    mixed = parse_strategy_config(
        {
            "name": "Partial",
            "filters": [
                {"id": "a", "field": "close", "operator": ">", "value": 0},
                {"id": "b", "field": "close", "operator": "<", "value": 0},
            ],
            "signal_rules": {"watch_min_passed": 1, "watch_min_pass_ratio": 0.4},
        }
    )
    watched = evaluate_stock(
        symbol="CCC-EQ",
        company="Ccc",
        series=series,
        strategy=mixed,
        start_date=series.dates[10],
        end_date=series.dates[-1],
    )
    assert watched.signal == WATCH


def test_returns_long_short_zero():
    rules = PositionRules(side="LONG")
    pos = simple_return(100, 135, rules)
    assert pos.return_pct == 35.0
    assert pos.bucket == "POSITIVE"
    short = simple_return(100, 80, PositionRules(side="SHORT"))
    assert abs((short.return_pct or 0) - 20.0) < 1e-9
    flat = simple_return(50, 50, rules)
    assert flat.return_pct == 0.0
    assert flat.bucket == "FLAT"
    missing = simple_return(None, 10, rules)
    assert missing.return_pct is None


def test_insufficient_data_is_not_a_signal():
    series = _series(10)
    cfg = parse_strategy_config(
        {"name": "Need SMA200", "filters": [{"field": "close", "operator": ">", "value": {"indicator": "SMA", "period": 200}}]}
    )
    result = evaluate_stock(
        symbol="THIN-EQ",
        company=None,
        series=series,
        strategy=cfg,
        start_date=series.dates[0],
        end_date=series.dates[-1],
    )
    assert result.status == "insufficient_data"
    assert result.signal is None


def test_one_stock_failure_does_not_stop_universe():
    cfg = parse_strategy_config({"name": "Simple", "filters": [{"field": "close", "operator": ">", "value": 0}]})
    dates = _dates(30)
    good = _series(30)
    results = []
    for symbol, series in [
        ("GOOD-EQ", good),
        ("BAD-EQ", None),
        ("EMPTY-EQ", BarSeries(dates=[], open=[], high=[], low=[], close=[], volume=[])),
        ("OK2-EQ", good),
    ]:
        results.append(
            evaluate_stock(
                symbol=symbol,
                company=symbol,
                series=series,
                strategy=cfg,
                start_date=dates[0],
                end_date=dates[-1],
            )
        )
    assert results[0].status == "ok"
    assert results[1].status == "insufficient_data"
    assert results[2].status == "insufficient_data"
    assert results[3].status == "ok"
    assert len(results) == 4


def test_ten_and_many_stocks_evaluate():
    cfg = parse_strategy_config({"name": "Scan", "filters": [{"field": "close", "operator": ">", "value": {"indicator": "SMA", "period": 5}}]})
    results = []
    for i in range(10):
        series = _series(40, start_px=50 + i, step=0.2)
        results.append(
            evaluate_stock(
                symbol=f"S{i}-EQ",
                company=f"S{i}",
                series=series,
                strategy=cfg,
                start_date=series.dates[5],
                end_date=series.dates[-1],
            )
        )
    assert len(results) == 10
    assert all(r.signal in {BUY, WATCH, REJECT} or r.status != "ok" for r in results)

    many = []
    for i in range(80):
        series = _series(30, start_px=20 + i * 0.1, step=0.05)
        many.append(
            evaluate_stock(
                symbol=f"M{i}-EQ",
                company=None,
                series=series,
                strategy=cfg,
                start_date=series.dates[2],
                end_date=series.dates[-1],
            )
        )
    assert len(many) == 80


def test_755_stocks_complete_even_if_one_fails():
    cfg = parse_strategy_config({"name": "Universe", "filters": [{"field": "close", "operator": ">", "value": 0}]})
    results = []
    for i in range(755):
        if i == 17:
            series = None
        else:
            series = _series(24, start_px=10 + (i % 9), step=0.1)
        results.append(
            evaluate_stock(
                symbol=f"U{i}-EQ",
                company=None,
                series=series,
                strategy=cfg,
                start_date=date(2024, 1, 2),
                end_date=date(2024, 2, 29),
            )
        )
    assert len(results) == 755
    assert results[17].status == "insufficient_data"
    assert sum(1 for r in results if r.status == "ok") == 754


def test_top_five_sort_and_filter_analytics_not_mixed_with_funnel():
    cfg = parse_strategy_config(
        {
            "name": "Two filters",
            "filters": [
                {"id": "f1", "field": "close", "operator": ">", "value": 0},
                {"id": "f2", "field": "close", "operator": ">", "value": 10000},
            ],
        }
    )
    results = []
    for i, step in enumerate([1.0, 2.0, -3.0, 4.0, -5.0, 0.5, -0.2]):
        series = _series(40, start_px=100, step=step)
        results.append(
            evaluate_stock(
                symbol=f"R{i}-EQ",
                company=None,
                series=series,
                strategy=cfg,
                start_date=series.dates[2],
                end_date=series.dates[-1],
            )
        )
    summary = summarize_results(results, cfg, universe_size=len(results))
    pos = summary["top_positive"]
    neg = summary["top_negative"]
    if len(pos) >= 2:
        assert pos[0]["return_pct"] >= pos[1]["return_pct"]
    if len(neg) >= 2:
        assert neg[0]["return_pct"] <= neg[1]["return_pct"]
    independent = independent_filter_stats([r for r in results if r.status == "ok"], cfg.root)
    funnel = sequential_funnel([r for r in results if r.status == "ok"], cfg.root, universe_size=len(results))
    assert independent[0]["passed"] >= independent[1]["passed"]
    assert funnel[0]["remaining"] == len(results)
    assert funnel[-1]["label"] == "Final BUY signals"
    # Independent pass count for filter 1 is not the sequential remainder after filter 2
    assert independent[0]["label"] != funnel[-1]["label"]


def test_presets_parse_and_name_persists():
    for preset in PRESETS:
        cfg = parse_strategy_config(preset)
        assert cfg.name == preset["name"]
        assert cfg.root.leaf_nodes()
    momentum = parse_strategy_config(PRESETS[0])
    assert momentum.name == "Momentum Strategy"


def test_short_return_is_not_mixed_with_long():
    series = _series(40, start_px=200, step=-1.0)
    cfg = parse_strategy_config(
        {
            "name": "Short",
            "side": "SHORT",
            "filters": [{"field": "close", "operator": "<", "value": {"indicator": "SMA", "period": 5}}],
        }
    )
    result = evaluate_stock(
        symbol="SHORT-EQ",
        company=None,
        series=series,
        strategy=cfg,
        start_date=series.dates[5],
        end_date=series.dates[-1],
    )
    assert result.position_side == "SHORT"
    assert result.return_pct is not None and result.return_pct > 0
