"""Overlay native last-bar Darvas buys onto Pine scanner results."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .catalog import LAB_BY_TITLE, LabStrategy, strategy_id_from_indicator_name
from .darvas import calculate_darvas_signals
from .darvas_breakeven import calculate_darvas_signals_breakeven


def _spec_from_title(title: str | None) -> LabStrategy | None:
    if not title:
        return None
    if title in LAB_BY_TITLE:
        return LAB_BY_TITLE[title]
    sid = strategy_id_from_indicator_name(title)
    from .catalog import LAB_BY_ID

    return LAB_BY_ID.get(sid or "")


def _bars_to_frame(bars: Any) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(list(bars.dates)).tz_localize(None).normalize(),
            "open": list(bars.open),
            "high": list(bars.high),
            "low": list(bars.low),
            "close": list(bars.close),
            "volume": list(bars.volume),
        }
    )


def _market_ok_series(bars: Any, benchmark: Any | None) -> pd.Series | None:
    if benchmark is None or len(getattr(benchmark, "close", []) or []) == 0:
        return None
    bench = pd.Series(list(benchmark.close), index=pd.to_datetime(list(benchmark.dates)).tz_localize(None).normalize())
    sma = bench.rolling(50).mean()
    ok = bench > sma
    stock_idx = pd.to_datetime(list(bars.dates)).tz_localize(None).normalize()
    return ok.reindex(stock_idx).fillna(False)


def overlay_native_last_bar(compiled: Any, bars: Any, result: Any, benchmark: Any | None = None) -> Any:
    if getattr(result, "status", None) != "ok":
        return result
    spec = _spec_from_title(getattr(compiled, "title", None))
    if spec is None or spec.pine_kind != "stateful":
        return result
    df = _bars_to_frame(bars)
    if len(df) < 253:
        return result
    market = _market_ok_series(bars, benchmark)
    if spec.strategy_id == "01_darvas_classic":
        df["market_filter_ok"] = True
        res = calculate_darvas_signals(df, sl_type="2close", vol_multiplier=2)
    elif spec.strategy_id == "05_darvas_breakeven":
        df["market_filter_ok"] = True if market is None else market.to_numpy()
        res = calculate_darvas_signals_breakeven(df, sl_type="atr", vol_multiplier=5, be_trigger="profit_10")
    else:
        df["market_filter_ok"] = True if market is None else market.to_numpy()
        res = calculate_darvas_signals(df, sl_type="atr", vol_multiplier=5)
        buy = bool(res["buy_signal"].iloc[-1])
        close = float(df["close"].iloc[-1])
        sma50 = df["close"].rolling(50).mean().iloc[-1]
        sma200 = df["close"].rolling(200).mean().iloc[-1]
        mom126 = df["close"].iloc[-1] / df["close"].iloc[-127] - 1 if len(df) > 126 else float("nan")
        if spec.strategy_id == "03_super_trend_align":
            buy = buy and pd.notna(sma50) and pd.notna(sma200) and close > float(sma50) and float(sma50) > float(sma200)
        elif spec.strategy_id == "04_rs_darvas":
            nifty_mom = None
            if benchmark is not None and len(benchmark.close) > 126:
                nifty_mom = float(benchmark.close[-1]) / float(benchmark.close[-127]) - 1
            buy = buy and pd.notna(mom126) and mom126 > 0 and (nifty_mom is None or mom126 > nifty_mom)
        _apply_buy(result, spec, buy)
        return result
    buy = bool(res["buy_signal"].iloc[-1])
    _apply_buy(result, spec, buy)
    return result


def _apply_buy(result: Any, spec: LabStrategy, buy: bool) -> None:
    outputs = dict(result.outputs or {})
    for key, value in list(outputs.items()):
        lowered = key.lower()
        if lowered in {"signal", "buy"} or "signal" in lowered:
            if isinstance(value, bool):
                outputs[key] = buy
            else:
                outputs[key] = 1.0 if buy else 0.0
    result.outputs = outputs
    result.conditions = [
        {
            "id": "c1",
            "name": f"{spec.name} native Darvas buy",
            "passed": buy,
            "left_value": 1 if buy else 0,
            "right_value": 1,
            "operator": "=",
        }
    ]
