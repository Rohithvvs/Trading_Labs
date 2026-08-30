"""Built-in strategy templates. Users can clone and edit; evaluation is config-driven."""

from __future__ import annotations

from typing import Any

from .schema import DEFAULT_UNIVERSE, parse_strategy_config

PRESETS: list[dict[str, Any]] = [
    {
        "preset_id": "momentum",
        "name": "Momentum Strategy",
        "description": "Momentum based strategy using trend, momentum and volume filters.",
        "universe": DEFAULT_UNIVERSE,
        "timeframe": "1D",
        "side": "LONG",
        "filters": [
            {"id": "close_sma50", "field": "close", "operator": ">", "value": {"indicator": "SMA", "period": 50}},
            {"id": "sma50_sma200", "field": "SMA_50", "operator": ">", "value": {"indicator": "SMA", "period": 200}},
            {"id": "rsi_55", "field": "RSI", "operator": ">", "value": 55},
            {"id": "vol_avg", "field": "volume", "operator": ">", "value": {"indicator": "AVG_VOLUME", "period": 20}},
        ],
    },
    {
        "preset_id": "breakout",
        "name": "Breakout Strategy",
        "description": "Close above the prior 20-day high with expanding volume and moderate RSI.",
        "universe": DEFAULT_UNIVERSE,
        "timeframe": "1D",
        "side": "LONG",
        "filters": [
            {"id": "close_high20", "field": "close", "operator": ">", "value": {"indicator": "HIGH", "period": 20}},
            {
                "id": "vol_1_5",
                "field": "REL_VOLUME",
                "operator": ">",
                "value": 1.5,
                "label": "Volume > 1.5 × Average Volume",
            },
            {"id": "rsi_band", "field": "RSI", "operator": "between", "low": 50, "high": 70},
            {"id": "close_ema50", "field": "close", "operator": ">", "value": {"indicator": "EMA", "period": 50}},
        ],
        "signal_rules": {"buy_requires_all": True, "watch_min_passed": 2, "watch_min_pass_ratio": 0.5},
    },
    {
        "preset_id": "mean_reversion",
        "name": "Mean Reversion",
        "description": "Oversold bounce: RSI below 30, close below the lower Bollinger Band, volume confirmation.",
        "universe": DEFAULT_UNIVERSE,
        "timeframe": "1D",
        "side": "LONG",
        "filters": [
            {"id": "rsi_30", "field": "RSI", "operator": "<", "value": 30},
            {"id": "close_bb", "field": "close", "operator": "<", "value": {"indicator": "BB_LOWER", "period": 20}},
            {"id": "vol_avg", "field": "volume", "operator": ">", "value": {"indicator": "AVG_VOLUME", "period": 20}},
        ],
    },
]


def preset_by_id(preset_id: str) -> dict[str, Any] | None:
    for item in PRESETS:
        if item["preset_id"] == preset_id:
            return dict(item)
    return None


def catalog() -> dict[str, Any]:
    return {
        "universes": [
            {"code": DEFAULT_UNIVERSE, "label": "755 Stocks", "description": "Complete NIFTY 500 membership universe (755 names)."},
            {"code": "NIFTY500", "label": "NIFTY 500", "description": "Active NIFTY 500 membership."},
        ],
        "timeframes": [{"code": "1D", "label": "Daily"}],
        "operators": [
            {"code": ">", "label": ">"},
            {"code": "<", "label": "<"},
            {"code": ">=", "label": ">="},
            {"code": "<=", "label": "<="},
            {"code": "==", "label": "="},
            {"code": "!=", "label": "≠"},
            {"code": "cross_above", "label": "Cross Above"},
            {"code": "cross_below", "label": "Cross Below"},
            {"code": "between", "label": "Between"},
            {"code": "outside", "label": "Outside"},
        ],
        "fields": [
            {"code": "OPEN", "label": "Open", "group": "price"},
            {"code": "HIGH", "label": "High", "group": "price"},
            {"code": "LOW", "label": "Low", "group": "price"},
            {"code": "CLOSE", "label": "Close", "group": "price"},
            {"code": "PREV_CLOSE", "label": "Previous Close", "group": "price"},
            {"code": "PREV_HIGH", "label": "Previous Day High", "group": "price"},
            {"code": "DAILY_RETURN", "label": "Daily Return", "group": "price"},
            {"code": "GAP_PCT", "label": "Gap %", "group": "price"},
            {"code": "VWAP", "label": "VWAP", "group": "price", "periods": [14, 20]},
            {"code": "ATR", "label": "ATR", "group": "price", "periods": [14]},
            {"code": "SMA", "label": "SMA", "group": "moving_average", "periods": [20, 50, 100, 200]},
            {"code": "EMA", "label": "EMA", "group": "moving_average", "periods": [9, 20, 50, 200]},
            {"code": "WMA", "label": "WMA", "group": "moving_average", "periods": [20, 50]},
            {"code": "RSI", "label": "RSI", "group": "momentum", "periods": [14]},
            {"code": "MACD", "label": "MACD", "group": "momentum"},
            {"code": "MACD_SIGNAL", "label": "MACD Signal", "group": "momentum"},
            {"code": "MACD_HISTOGRAM", "label": "MACD Histogram", "group": "momentum"},
            {"code": "STOCH_K", "label": "Stochastic %K", "group": "momentum", "periods": [14]},
            {"code": "ROC", "label": "ROC", "group": "momentum", "periods": [12]},
            {"code": "BB_UPPER", "label": "Upper Bollinger Band", "group": "volatility", "periods": [20]},
            {"code": "BB_LOWER", "label": "Lower Bollinger Band", "group": "volatility", "periods": [20]},
            {"code": "BB_MIDDLE", "label": "Middle Bollinger Band", "group": "volatility", "periods": [20]},
            {"code": "BB_WIDTH", "label": "Bollinger Band Width", "group": "volatility", "periods": [20]},
            {"code": "HV", "label": "Historical Volatility", "group": "volatility", "periods": [20]},
            {"code": "VOLUME", "label": "Volume", "group": "volume"},
            {"code": "AVG_VOLUME", "label": "Average Volume", "group": "volume", "periods": [20]},
            {"code": "REL_VOLUME", "label": "Relative Volume", "group": "volume", "periods": [20]},
            {"code": "VOLUME_CHANGE_PCT", "label": "Volume Change %", "group": "volume"},
            {"code": "HIGH", "label": "N-Day High (prior)", "group": "trend", "periods": [20, 52]},
            {"code": "BENCHMARK_CLOSE", "label": "NIFTY 500 Close (market gate)", "group": "benchmark"},
        ],
        "presets": PRESETS,
        "sides": ["LONG", "SHORT"],
        "calculation_version": "strategy_tester.v1",
        "lookahead": "Indicators at bar t use only bars with index <= t. Prior N-day high/low exclude the current bar.",
    }


def validated_presets() -> list[dict[str, Any]]:
    out = []
    for item in PRESETS:
        parse_strategy_config(item)
        out.append(item)
    return out
