"""Engine-specific Technical Analysis for RE-001 (Trend Continuation).

Single source of truth for:
- Indicator values used by RE-001 (EMA20, ATR14, Keltner, RVOL, HA, RSI)
- Mandatory BUY gates
- 35/30/20/15 composite score components
- Risk management (entry / SL / TP / size / breakeven / trailing)

Decision wiring lives in engine.py; this module only computes values.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import ta

from ...utils.financial_math import calculate_position_size, calculate_risk_reward_ratio

# ---------------------------------------------------------------------------
# Constants (approved RE-001 parameters — not tunable knobs)
# ---------------------------------------------------------------------------
KELTNER_ATR_MULT = 2.0
RVOL_THRESHOLD = 1.5
HA_LOWER_WICK_MAX_PCT = 0.01  # percent of HA_Open
RSI_THRESHOLD = 50.0
COMPOSITE_BUY_THRESHOLD = 75.0
COMPOSITE_WEIGHTS = {
    "volume": 0.35,
    "trend": 0.30,
    "ha": 0.20,
    "rsi": 0.15,
}
ATR_STOP_MULT = 1.5
TP_R_MULT = 3.0
BREAKEVEN_ATR_MULT = 1.5
RISK_PCT_OF_CAPITAL = 1.0  # percent
DEFAULT_CAPITAL = 1_000_000.0


def _candle_field(c: Any, name: str, default: Any = None) -> Any:
    if isinstance(c, dict):
        return c.get(name, default)
    return getattr(c, name, default)


def candles_to_dataframe(candles: list[Any]) -> pd.DataFrame:
    """Convert candle objects/dicts to a sorted OHLCV DataFrame."""
    rows: list[dict[str, Any]] = []
    for i, c in enumerate(candles or []):
        try:
            rows.append(
                {
                    "timestamp": _candle_field(c, "timestamp", i),
                    "open": float(_candle_field(c, "open")),
                    "high": float(_candle_field(c, "high")),
                    "low": float(_candle_field(c, "low")),
                    "close": float(_candle_field(c, "close")),
                    "volume": float(_candle_field(c, "volume") or 0),
                }
            )
        except (TypeError, ValueError):
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    try:
        df = df.sort_values("timestamp").reset_index(drop=True)
    except Exception:
        df = df.reset_index(drop=True)
    return df


def compute_heikin_ashi(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Standard Heikin-Ashi OHLC series (existing mathematically correct method)."""
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    ha_open = pd.Series(np.zeros(len(df)), index=df.index, dtype=float)
    ha_open.iloc[0] = (float(df["open"].iloc[0]) + float(df["close"].iloc[0])) / 2.0
    for i in range(1, len(df)):
        ha_open.iloc[i] = (float(ha_open.iloc[i - 1]) + float(ha_close.iloc[i - 1])) / 2.0

    ha_high = pd.concat([df["high"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open, ha_close], axis=1).min(axis=1)
    return ha_open, ha_high, ha_low, ha_close


def ha_lower_wick_pct(ha_open: float, ha_low: float) -> float:
    """HA lower wick as percent of HA_Open: (HA_Open - HA_Low) / HA_Open × 100."""
    if ha_open is None or ha_low is None or ha_open <= 0:
        return 0.0
    wick = max(0.0, float(ha_open) - float(ha_low))
    return (wick / float(ha_open)) * 100.0


def score_volume(relative_volume: float | None) -> float:
    """S_volume ∈ [0, 100]. Scales with RVOL (1.5 → 75, 2.0 → 100)."""
    if relative_volume is None or relative_volume <= 0:
        return 0.0
    return max(0.0, min(100.0, 50.0 * float(relative_volume)))


def score_trend(
    close: float | None,
    upper_keltner: float | None,
    atr14: float | None,
) -> float:
    """S_trend ∈ [0, 100]. Breakout extension beyond upper Keltner in ATR units."""
    if close is None or upper_keltner is None or atr14 is None or atr14 <= 0:
        return 0.0
    excess_atr = (float(close) - float(upper_keltner)) / float(atr14)
    # Just at band ≈ 75; stronger extension scales toward 100
    return max(0.0, min(100.0, 75.0 + excess_atr * 25.0))


def score_ha(ha_bullish: bool, ha_lower_wick_ratio_pct: float | None) -> float:
    """S_HA ∈ [0, 100]. Bullish HA with minimal lower wick scores highest."""
    if not ha_bullish:
        return 0.0
    wick = max(0.0, float(ha_lower_wick_ratio_pct or 0.0))
    # 0% wick → 100; 0.01% wick → 80; worse → lower
    return max(0.0, min(100.0, 100.0 - (wick / HA_LOWER_WICK_MAX_PCT) * 20.0))


def score_rsi(rsi14: float | None) -> float:
    """S_RSI ∈ [0, 100]. RSI 50 → 50, 60 → 75, 70 → 100."""
    if rsi14 is None:
        return 0.0
    return max(0.0, min(100.0, 50.0 + (float(rsi14) - 50.0) * 2.5))


def composite_score(
    s_volume: float,
    s_trend: float,
    s_ha: float,
    s_rsi: float,
) -> float:
    """0.35·S_volume + 0.30·S_trend + 0.20·S_HA + 0.15·S_RSI."""
    return (
        COMPOSITE_WEIGHTS["volume"] * float(s_volume)
        + COMPOSITE_WEIGHTS["trend"] * float(s_trend)
        + COMPOSITE_WEIGHTS["ha"] * float(s_ha)
        + COMPOSITE_WEIGHTS["rsi"] * float(s_rsi)
    )


def compute_risk_plan(
    *,
    entry: float,
    atr14: float,
    ema20: float,
    capital: float = DEFAULT_CAPITAL,
) -> dict[str, Any]:
    """RE-001 risk management at trigger candle close (long only)."""
    if entry is None or entry <= 0 or atr14 is None or atr14 <= 0 or ema20 is None:
        return {
            "entry": entry,
            "atr_stop": None,
            "ema_stop": ema20,
            "selected_sl": None,
            "risk_per_share": None,
            "position_size": 0,
            "take_profit": None,
            "risk_reward": None,
            "breakeven_trigger": None,
            "current_ema_trailing_stop": None,
            "risk_amount": None,
            "capital": capital,
            "risk_pct": RISK_PCT_OF_CAPITAL,
            "valid": False,
        }

    entry_f = float(entry)
    atr_f = float(atr14)
    ema_f = float(ema20)

    atr_stop = entry_f - (ATR_STOP_MULT * atr_f)
    ema_stop = ema_f

    # Long: valid stop must be below entry; closer stop = higher price = max(valid)
    valid: list[float] = []
    if atr_stop < entry_f:
        valid.append(atr_stop)
    if ema_stop < entry_f:
        valid.append(ema_stop)

    if not valid:
        return {
            "entry": entry_f,
            "atr_stop": atr_stop,
            "ema_stop": ema_stop,
            "selected_sl": None,
            "risk_per_share": None,
            "position_size": 0,
            "take_profit": None,
            "risk_reward": None,
            "breakeven_trigger": entry_f + (BREAKEVEN_ATR_MULT * atr_f),
            "current_ema_trailing_stop": None,
            "risk_amount": float(capital) * (RISK_PCT_OF_CAPITAL / 100.0),
            "capital": float(capital),
            "risk_pct": RISK_PCT_OF_CAPITAL,
            "valid": False,
        }

    selected_sl = max(valid)  # closer to entry
    risk_per_share = entry_f - selected_sl
    risk_amount = float(capital) * (RISK_PCT_OF_CAPITAL / 100.0)
    pos = int(
        calculate_position_size(
            account_equity=float(capital),
            risk_per_trade_pct=RISK_PCT_OF_CAPITAL,
            entry_price=entry_f,
            stop_loss=selected_sl,
        )
    )
    take_profit = entry_f + (TP_R_MULT * risk_per_share)
    breakeven_trigger = entry_f + (BREAKEVEN_ATR_MULT * atr_f)
    # At signal time trailing has not advanced; never below selected SL.
    # After price >= breakeven: stop = max(entry, ema20); never move downward.
    current_trailing = selected_sl
    rr = calculate_risk_reward_ratio(entry_f, selected_sl, take_profit)

    return {
        "entry": entry_f,
        "atr_stop": atr_stop,
        "ema_stop": ema_stop,
        "selected_sl": selected_sl,
        "risk_per_share": risk_per_share,
        "position_size": pos,
        "take_profit": take_profit,
        "risk_reward": rr,
        "breakeven_trigger": breakeven_trigger,
        "current_ema_trailing_stop": current_trailing,
        "risk_amount": risk_amount,
        "capital": float(capital),
        "risk_pct": RISK_PCT_OF_CAPITAL,
        "valid": risk_per_share > 0 and pos >= 0,
    }


def advance_trailing_stop(
    *,
    current_stop: float,
    entry: float,
    price: float,
    atr14: float,
    ema20: float,
) -> float:
    """After entry: breakeven at entry+1.5·ATR, then trail with EMA20; never worsen."""
    stop = float(current_stop)
    be = float(entry) + (BREAKEVEN_ATR_MULT * float(atr14))
    if float(price) >= be:
        stop = max(stop, float(entry))
        # After breakeven: new_stop = max(current_stop, EMA20)
        stop = max(stop, float(ema20))
    return stop


def evaluate_mandatory_gates(
    *,
    close: float | None,
    upper_keltner: float | None,
    relative_volume: float | None,
    ha_close: float | None,
    ha_open: float | None,
    ha_lower_wick_ratio_pct: float | None,
    rsi14: float | None,
    earnings_clear: bool,
) -> dict[str, Any]:
    """Mandatory RE-001 BUY gates. Any fail ⇒ NO-BUY."""
    keltner_ok = (
        close is not None
        and upper_keltner is not None
        and float(close) > float(upper_keltner)
    )
    rvol_ok = relative_volume is not None and float(relative_volume) > RVOL_THRESHOLD
    ha_bullish = (
        ha_close is not None
        and ha_open is not None
        and float(ha_close) > float(ha_open)
    )
    wick_ok = (
        ha_lower_wick_ratio_pct is not None
        and float(ha_lower_wick_ratio_pct) <= HA_LOWER_WICK_MAX_PCT
    )
    rsi_ok = rsi14 is not None and float(rsi14) > RSI_THRESHOLD
    earn_ok = bool(earnings_clear)

    gates = {
        "keltner_breakout": bool(keltner_ok),
        "relative_volume": bool(rvol_ok),
        "ha_bullish": bool(ha_bullish),
        "ha_lower_wick": bool(wick_ok),
        "rsi": bool(rsi_ok),
        "earnings_clear": bool(earn_ok),
    }
    all_pass = all(gates.values())
    failed = [name for name, ok in gates.items() if not ok]
    return {
        "gates": gates,
        "all_pass": all_pass,
        "failed": failed,
        "thresholds": {
            "keltner": "close > upper_keltner",
            "relative_volume": RVOL_THRESHOLD,
            "ha_bullish": "ha_close > ha_open",
            "ha_lower_wick_pct": HA_LOWER_WICK_MAX_PCT,
            "rsi": RSI_THRESHOLD,
            "earnings_trading_days": 3,
            "composite_buy": COMPOSITE_BUY_THRESHOLD,
        },
    }


def build_re001_technicals(
    candles: list[Any],
    tech_results: list[Any] | None = None,
    *,
    earnings_info: dict[str, Any] | None = None,
    capital: float | None = None,
) -> dict[str, Any]:
    """Build full RE-001 technical analysis payload (display + decision inputs).

    ``tech_results`` is accepted for API compatibility; RE-001 decision values
    are computed from candles (not production tech_score).
    """
    del tech_results  # unused — production TA score must not drive RE-001 values
    if not candles:
        return {}

    try:
        df = candles_to_dataframe(candles)
        if df.empty or len(df) < 20:
            return {"error": "insufficient_history", "min_bars": 20, "bars": len(df)}

        # ---- Existing correct indicator calculations (reuse) ----
        ema20 = ta.trend.ema_indicator(df["close"], window=20)
        atr14 = ta.volatility.average_true_range(
            df["high"], df["low"], df["close"], window=14
        )
        rsi14 = ta.momentum.rsi(df["close"], window=14)
        sma20_vol = df["volume"].rolling(window=20).mean()

        upper_keltner = ema20 + (atr14 * KELTNER_ATR_MULT)
        lower_keltner = ema20 - (atr14 * KELTNER_ATR_MULT)
        keltner_width = ((upper_keltner - lower_keltner) / ema20) * 100.0

        ha_open_s, ha_high_s, ha_low_s, ha_close_s = compute_heikin_ashi(df)

        idx = -1
        close = float(df["close"].iloc[idx])
        current_vol = float(df["volume"].iloc[idx])
        ema20_v = float(ema20.iloc[idx]) if not pd.isna(ema20.iloc[idx]) else None
        atr14_v = float(atr14.iloc[idx]) if not pd.isna(atr14.iloc[idx]) else None
        rsi14_v = float(rsi14.iloc[idx]) if not pd.isna(rsi14.iloc[idx]) else None
        upper_k = float(upper_keltner.iloc[idx]) if not pd.isna(upper_keltner.iloc[idx]) else None
        lower_k = float(lower_keltner.iloc[idx]) if not pd.isna(lower_keltner.iloc[idx]) else None
        k_width = float(keltner_width.iloc[idx]) if not pd.isna(keltner_width.iloc[idx]) else None
        vol_sma20 = float(sma20_vol.iloc[idx]) if not pd.isna(sma20_vol.iloc[idx]) else None
        rvol = (current_vol / vol_sma20) if vol_sma20 and vol_sma20 > 0 else None

        ha_o = float(ha_open_s.iloc[idx])
        ha_h = float(ha_high_s.iloc[idx])
        ha_l = float(ha_low_s.iloc[idx])
        ha_c = float(ha_close_s.iloc[idx])
        ha_bullish = ha_c > ha_o
        ha_direction = "Bullish" if ha_bullish else "Bearish"
        ha_wick = max(0.0, ha_o - ha_l)
        ha_wick_pct = ha_lower_wick_pct(ha_o, ha_l)

        # Earnings (from caller; default clear when unknown)
        earn = earnings_info or {}
        earnings_clear = bool(earn.get("earnings_clear", True))
        next_earnings_date = earn.get("next_earnings_date")
        trading_days_until = earn.get("trading_days_until_earnings")

        gate_eval = evaluate_mandatory_gates(
            close=close,
            upper_keltner=upper_k,
            relative_volume=rvol,
            ha_close=ha_c,
            ha_open=ha_o,
            ha_lower_wick_ratio_pct=ha_wick_pct,
            rsi14=rsi14_v,
            earnings_clear=earnings_clear,
        )

        s_vol = score_volume(rvol)
        s_tr = score_trend(close, upper_k, atr14_v)
        s_ha = score_ha(ha_bullish, ha_wick_pct)
        s_rsi = score_rsi(rsi14_v)
        comp = composite_score(s_vol, s_tr, s_ha, s_rsi)
        score_ok = comp > COMPOSITE_BUY_THRESHOLD

        cap = float(capital) if capital is not None and capital > 0 else DEFAULT_CAPITAL
        risk = compute_risk_plan(
            entry=close,
            atr14=atr14_v if atr14_v is not None else 0.0,
            ema20=ema20_v if ema20_v is not None else 0.0,
            capital=cap,
        )

        # Final RE-001 technical decision (gates + composite only)
        if gate_eval["all_pass"] and score_ok:
            final_decision = "BUY"
        elif gate_eval["all_pass"] and not score_ok:
            final_decision = "WATCH"  # setup present, score below threshold
        else:
            final_decision = "REJECT"

        baseline = {
            "ema_20": ema20_v,
            "atr_14": atr14_v,
            "upper_keltner_band": upper_k,
            "lower_keltner_band": lower_k,
            "keltner_width": k_width,
            "current_close": close,
            "current_volume": int(current_vol) if math.isfinite(current_vol) else None,
            "volume_sma_20": vol_sma20,
            "avg_volume_20d": vol_sma20,  # alias for existing UI
            "relative_volume": rvol,
            "volume_ratio": rvol,  # alias
            "volume_condition": bool(gate_eval["gates"]["relative_volume"]),
            "heikin_ashi_state": ha_direction,
            "ha_open": ha_o,
            "ha_high": ha_h,
            "ha_low": ha_l,
            "ha_close": ha_c,
            "ha_direction": ha_direction,
            "ha_lower_wick": ha_wick,
            "ha_lower_wick_pct": ha_wick_pct,
            "lower_wick_percentage": ha_wick_pct,  # alias; now HA-based
            "ha_condition": bool(
                gate_eval["gates"]["ha_bullish"] and gate_eval["gates"]["ha_lower_wick"]
            ),
            "rsi_14": rsi14_v,
            "rsi_threshold": RSI_THRESHOLD,
            "rsi_condition": bool(gate_eval["gates"]["rsi"]),
            "price_vs_ema": ((close / ema20_v) - 1.0) * 100.0 if ema20_v else None,
            "next_earnings_date": next_earnings_date,
            "trading_days_until_earnings": trading_days_until,
            "earnings_condition": earnings_clear,
        }

        scoring = {
            "s_volume": s_vol,
            "s_trend": s_tr,
            "s_ha": s_ha,
            "s_rsi": s_rsi,
            "weights": dict(COMPOSITE_WEIGHTS),
            "composite_score": comp,
            "buy_threshold": COMPOSITE_BUY_THRESHOLD,
            "score_pass": score_ok,
            "components": [
                {
                    "component": "Volume",
                    "key": "s_volume",
                    "weight": COMPOSITE_WEIGHTS["volume"],
                    "raw": s_vol,
                    "contribution": COMPOSITE_WEIGHTS["volume"] * s_vol,
                },
                {
                    "component": "Trend",
                    "key": "s_trend",
                    "weight": COMPOSITE_WEIGHTS["trend"],
                    "raw": s_tr,
                    "contribution": COMPOSITE_WEIGHTS["trend"] * s_tr,
                },
                {
                    "component": "Heikin-Ashi",
                    "key": "s_ha",
                    "weight": COMPOSITE_WEIGHTS["ha"],
                    "raw": s_ha,
                    "contribution": COMPOSITE_WEIGHTS["ha"] * s_ha,
                },
                {
                    "component": "RSI",
                    "key": "s_rsi",
                    "weight": COMPOSITE_WEIGHTS["rsi"],
                    "raw": s_rsi,
                    "contribution": COMPOSITE_WEIGHTS["rsi"] * s_rsi,
                },
            ],
        }

        decision = {
            "keltner_gate": gate_eval["gates"]["keltner_breakout"],
            "volume_gate": gate_eval["gates"]["relative_volume"],
            "ha_gate": gate_eval["gates"]["ha_bullish"],
            "wick_gate": gate_eval["gates"]["ha_lower_wick"],
            "rsi_gate": gate_eval["gates"]["rsi"],
            "earnings_gate": gate_eval["gates"]["earnings_clear"],
            "all_mandatory_gates_pass": gate_eval["all_pass"],
            "failed_gates": gate_eval["failed"],
            "composite_score": comp,
            "composite_pass": score_ok,
            "final_decision": final_decision,
            "thresholds": gate_eval["thresholds"],
        }

        interpretation = {
            "price_structure": (
                "Uptrend" if ema20_v and close > ema20_v else "Downtrend"
            ),
            "trend_strength": (
                "Strong" if rsi14_v is not None and rsi14_v > 60 else "Neutral"
            ),
            "pullback_quality": "n/a",
            "momentum_resumption": (
                "Yes" if ha_bullish and (rvol or 0) > 1 else "No"
            ),
            "keltner_breakout": gate_eval["gates"]["keltner_breakout"],
            "rvol_ok": gate_eval["gates"]["relative_volume"],
        }

        return {
            "baseline": baseline,
            "scoring": scoring,
            "decision": decision,
            "risk": risk,
            "interpretation": interpretation,
            "gates": gate_eval["gates"],
            "mandatory_gates_pass": gate_eval["all_pass"],
            "composite_score": comp,
            "final_decision": final_decision,
        }
    except Exception as exc:
        return {"error": str(exc)}
