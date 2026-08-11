"""RE-001 core logic correction — mandatory gates, composite, risk, decision wiring."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from app.services.re001.context import build_lab_context
from app.services.re001.engine import evaluate_re001
from app.services.re001.technicals import (
    COMPOSITE_BUY_THRESHOLD,
    advance_trailing_stop,
    composite_score,
    compute_risk_plan,
    evaluate_mandatory_gates,
    ha_lower_wick_pct,
    score_ha,
    score_rsi,
    score_trend,
    score_volume,
)


class _Bull:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


class _C:
    def __init__(self, close, volume=200_000, open_=None, high=None, low=None):
        self.close = close
        self.volume = volume
        self.open = open_ if open_ is not None else close
        self.high = high if high is not None else close + 1
        self.low = low if low is not None else close - 1
        self.timestamp = close  # sortable


class _T:
    def __init__(self, score, signal="bullish"):
        self.score = score
        self.signal = signal


def _candles(n=220, base=100.0):
    return [_C(base + i * 0.5, volume=200_000 + i * 1000) for i in range(n)]


def _portfolio():
    return {"open_positions_count": 0, "max_positions": 10, "available_cash": 1_000_000.0}


def _tech_payload(
    *,
    keltner=True,
    rvol=True,
    ha=True,
    wick=True,
    rsi=True,
    earnings=True,
    composite=80.0,
    final=None,
):
    gates = {
        "keltner_breakout": keltner,
        "relative_volume": rvol,
        "ha_bullish": ha,
        "ha_lower_wick": wick,
        "rsi": rsi,
        "earnings_clear": earnings,
    }
    all_pass = all(gates.values())
    failed = [k for k, v in gates.items() if not v]
    score_ok = composite > COMPOSITE_BUY_THRESHOLD
    if final is None:
        if all_pass and score_ok:
            final = "BUY"
        elif all_pass:
            final = "WATCH"
        else:
            final = "REJECT"
    return {
        "gates": gates,
        "mandatory_gates_pass": all_pass,
        "composite_score": composite,
        "final_decision": final,
        "decision": {
            "failed_gates": failed,
            "keltner_gate": keltner,
            "volume_gate": rvol,
            "ha_gate": ha,
            "wick_gate": wick,
            "rsi_gate": rsi,
            "earnings_gate": earnings,
            "all_mandatory_gates_pass": all_pass,
            "composite_score": composite,
            "composite_pass": score_ok,
            "final_decision": final,
        },
        "scoring": {
            "s_volume": 80,
            "s_trend": 80,
            "s_ha": 80,
            "s_rsi": 80,
            "composite_score": composite,
            "buy_threshold": COMPOSITE_BUY_THRESHOLD,
        },
        "risk": {
            "entry": 100.0,
            "atr_stop": 97.0,
            "ema_stop": 96.0,
            "selected_sl": 97.0,
            "risk_per_share": 3.0,
            "position_size": 10,
            "take_profit": 109.0,
            "risk_reward": 3.0,
            "breakeven_trigger": 103.0,
            "current_ema_trailing_stop": 97.0,
            "valid": True,
        },
        "baseline": {},
        "interpretation": {},
    }


# ---------------------------------------------------------------------------
# Pure gate / score / risk units
# ---------------------------------------------------------------------------


def test_case1_keltner_fail_is_no_buy():
    g = evaluate_mandatory_gates(
        close=100.0,
        upper_keltner=100.0,  # close == upper → fail (must be >)
        relative_volume=2.0,
        ha_close=101.0,
        ha_open=100.0,
        ha_lower_wick_ratio_pct=0.0,
        rsi14=60.0,
        earnings_clear=True,
    )
    assert g["gates"]["keltner_breakout"] is False
    assert g["all_pass"] is False


def test_case2_rvol_1_30_fails():
    g = evaluate_mandatory_gates(
        close=110.0,
        upper_keltner=100.0,
        relative_volume=1.30,
        ha_close=101.0,
        ha_open=100.0,
        ha_lower_wick_ratio_pct=0.0,
        rsi14=60.0,
        earnings_clear=True,
    )
    assert g["gates"]["relative_volume"] is False
    assert g["all_pass"] is False


def test_case3_ha_bearish_fails():
    g = evaluate_mandatory_gates(
        close=110.0,
        upper_keltner=100.0,
        relative_volume=2.0,
        ha_close=99.0,
        ha_open=100.0,
        ha_lower_wick_ratio_pct=0.0,
        rsi14=60.0,
        earnings_clear=True,
    )
    assert g["gates"]["ha_bullish"] is False
    assert g["all_pass"] is False


def test_case4_rsi_48_fails():
    g = evaluate_mandatory_gates(
        close=110.0,
        upper_keltner=100.0,
        relative_volume=2.0,
        ha_close=101.0,
        ha_open=100.0,
        ha_lower_wick_ratio_pct=0.0,
        rsi14=48.0,
        earnings_clear=True,
    )
    assert g["gates"]["rsi"] is False
    assert g["all_pass"] is False


def test_all_gates_pass():
    g = evaluate_mandatory_gates(
        close=110.0,
        upper_keltner=100.0,
        relative_volume=2.0,
        ha_close=101.0,
        ha_open=100.0,
        ha_lower_wick_ratio_pct=0.005,
        rsi14=55.0,
        earnings_clear=True,
    )
    assert g["all_pass"] is True


def test_ha_wick_threshold_0_01_pct():
    # Exactly at 0.01% → pass
    g = evaluate_mandatory_gates(
        close=110.0,
        upper_keltner=100.0,
        relative_volume=2.0,
        ha_close=101.0,
        ha_open=100.0,
        ha_lower_wick_ratio_pct=0.01,
        rsi14=55.0,
        earnings_clear=True,
    )
    assert g["gates"]["ha_lower_wick"] is True
    # Above 0.01% → fail
    g2 = evaluate_mandatory_gates(
        close=110.0,
        upper_keltner=100.0,
        relative_volume=2.0,
        ha_close=101.0,
        ha_open=100.0,
        ha_lower_wick_ratio_pct=0.011,
        rsi14=55.0,
        earnings_clear=True,
    )
    assert g2["gates"]["ha_lower_wick"] is False


def test_ha_lower_wick_uses_ha_open_not_range():
    # HA_Open=1000, HA_Low=999.9 → wick=0.1, pct=0.01%
    pct = ha_lower_wick_pct(1000.0, 999.9)
    assert abs(pct - 0.01) < 1e-9


def test_composite_weights_35_30_20_15():
    # Perfect components → 100
    c = composite_score(100, 100, 100, 100)
    assert abs(c - 100.0) < 1e-9
    # Only volume: 0.35 * 100
    assert abs(composite_score(100, 0, 0, 0) - 35.0) < 1e-9
    assert abs(composite_score(0, 100, 0, 0) - 30.0) < 1e-9
    assert abs(composite_score(0, 0, 100, 0) - 20.0) < 1e-9
    assert abs(composite_score(0, 0, 0, 100) - 15.0) < 1e-9


def test_case5_composite_74_99_no_buy(monkeypatch):
    payload = _tech_payload(composite=74.99)
    monkeypatch.setattr(
        "app.services.re001.engine.build_re001_technicals",
        lambda *a, **k: payload,
    )
    monkeypatch.setattr(
        "app.services.re001.engine._resolve_earnings",
        lambda ctx: {"earnings_clear": True},
    )
    ctx = build_lab_context(
        symbol="C5",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(90, "bullish")],
        user_portfolio=_portfolio(),
        earnings_info={"earnings_clear": True},
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] != "BUY"
    assert r["recommendation_state"] in {"WATCH", "REJECT"}


def test_case6_composite_75_01_buy(monkeypatch):
    payload = _tech_payload(composite=75.01)
    monkeypatch.setattr(
        "app.services.re001.engine.build_re001_technicals",
        lambda *a, **k: payload,
    )
    monkeypatch.setattr(
        "app.services.re001.engine._resolve_earnings",
        lambda ctx: {"earnings_clear": True},
    )
    ctx = build_lab_context(
        symbol="C6",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(90, "bullish")],
        user_portfolio=_portfolio(),
        earnings_info={"earnings_clear": True},
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] == "BUY"
    assert r["evidence"]["re001_composite_score"] == pytest.approx(75.01)
    # production tech_score must not be the decision threshold field
    assert r["evidence"].get("technical_score") is None


def test_case1_engine_keltner_fail_no_buy_even_if_high_prod_score(monkeypatch):
    payload = _tech_payload(keltner=False, composite=99.0)
    monkeypatch.setattr(
        "app.services.re001.engine.build_re001_technicals",
        lambda *a, **k: payload,
    )
    monkeypatch.setattr(
        "app.services.re001.engine._resolve_earnings",
        lambda ctx: {"earnings_clear": True},
    )
    ctx = build_lab_context(
        symbol="C1",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(99, "bullish")],
        user_portfolio=_portfolio(),
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] == "REJECT"
    assert "keltner_breakout_failed" in r["reason_codes"]


def test_case2_engine_rvol_fail(monkeypatch):
    payload = _tech_payload(rvol=False, composite=90.0)
    monkeypatch.setattr(
        "app.services.re001.engine.build_re001_technicals",
        lambda *a, **k: payload,
    )
    monkeypatch.setattr(
        "app.services.re001.engine._resolve_earnings",
        lambda ctx: {"earnings_clear": True},
    )
    ctx = build_lab_context(
        symbol="C2",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(90)],
        user_portfolio=_portfolio(),
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] == "REJECT"
    assert "relative_volume_failed" in r["reason_codes"]


def test_case3_engine_ha_fail(monkeypatch):
    payload = _tech_payload(ha=False, composite=90.0)
    monkeypatch.setattr(
        "app.services.re001.engine.build_re001_technicals",
        lambda *a, **k: payload,
    )
    monkeypatch.setattr(
        "app.services.re001.engine._resolve_earnings",
        lambda ctx: {"earnings_clear": True},
    )
    ctx = build_lab_context(
        symbol="C3",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(90)],
        user_portfolio=_portfolio(),
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] == "REJECT"
    assert "ha_not_bullish" in r["reason_codes"]


def test_case4_engine_rsi_fail(monkeypatch):
    payload = _tech_payload(rsi=False, composite=90.0)
    monkeypatch.setattr(
        "app.services.re001.engine.build_re001_technicals",
        lambda *a, **k: payload,
    )
    monkeypatch.setattr(
        "app.services.re001.engine._resolve_earnings",
        lambda ctx: {"earnings_clear": True},
    )
    ctx = build_lab_context(
        symbol="C4",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(90)],
        user_portfolio=_portfolio(),
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] == "REJECT"
    assert "rsi_below_threshold" in r["reason_codes"]


def test_earnings_blackout_no_buy(monkeypatch):
    payload = _tech_payload(earnings=False, composite=90.0)
    monkeypatch.setattr(
        "app.services.re001.engine.build_re001_technicals",
        lambda *a, **k: payload,
    )
    monkeypatch.setattr(
        "app.services.re001.engine._resolve_earnings",
        lambda ctx: {"earnings_clear": False, "trading_days_until_earnings": 2},
    )
    ctx = build_lab_context(
        symbol="EARN",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(90)],
        user_portfolio=_portfolio(),
        earnings_info={"earnings_clear": False, "trading_days_until_earnings": 2},
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] == "REJECT"
    assert "earnings_blackout" in r["reason_codes"]


# ---------------------------------------------------------------------------
# CASE 7 — risk math
# ---------------------------------------------------------------------------


def test_case7_risk_closer_stop_and_levels():
    entry = 2540.0
    atr14 = 42.15
    ema20 = 2450.50
    capital = 1_000_000.0

    plan = compute_risk_plan(entry=entry, atr14=atr14, ema20=ema20, capital=capital)

    atr_stop = entry - (1.5 * atr14)  # 2476.775
    assert plan["atr_stop"] == pytest.approx(atr_stop)
    assert plan["ema_stop"] == pytest.approx(ema20)
    # Closer valid stop = max(ATR stop, EMA stop) for long
    assert plan["selected_sl"] == pytest.approx(atr_stop)
    assert plan["selected_sl"] > ema20

    risk_ps = entry - atr_stop  # 63.225
    assert plan["risk_per_share"] == pytest.approx(risk_ps)
    assert plan["risk_amount"] == pytest.approx(capital * 0.01)
    assert plan["position_size"] == math.floor((capital * 0.01) / risk_ps)
    assert plan["take_profit"] == pytest.approx(entry + 3 * risk_ps)
    assert plan["breakeven_trigger"] == pytest.approx(entry + 1.5 * atr14)
    assert plan["risk_reward"] == pytest.approx(3.0)
    # At signal: trailing stop starts at selected SL
    assert plan["current_ema_trailing_stop"] == pytest.approx(atr_stop)


def test_trailing_stop_never_worsens():
    entry = 2540.0
    atr = 42.15
    ema = 2450.50
    initial = entry - 1.5 * atr  # ATR stop
    # Price reaches breakeven trigger → stop moves to at least entry, then max with EMA
    be_price = entry + 1.5 * atr
    stop1 = advance_trailing_stop(
        current_stop=initial, entry=entry, price=be_price, atr14=atr, ema20=ema
    )
    assert stop1 >= entry
    # Later, lower EMA must not pull stop down
    stop2 = advance_trailing_stop(
        current_stop=stop1, entry=entry, price=be_price + 10, atr14=atr, ema20=entry - 50
    )
    assert stop2 >= stop1
    # Higher EMA ratchets stop up
    stop3 = advance_trailing_stop(
        current_stop=stop2, entry=entry, price=be_price + 20, atr14=atr, ema20=entry + 5
    )
    assert stop3 >= stop2
    assert stop3 == pytest.approx(entry + 5)


def test_score_helpers_bounded():
    assert 0 <= score_volume(2.0) <= 100
    assert 0 <= score_trend(110, 100, 5) <= 100
    assert 0 <= score_ha(True, 0.0) <= 100
    assert score_ha(False, 0.0) == 0.0
    assert 0 <= score_rsi(55) <= 100


def test_build_re001_technicals_exposes_decision_fields():
    from app.services.re001.technicals import build_re001_technicals

    # Strong uptrend-ish series with volume spike on last bar
    candles = []
    for i in range(80):
        c = 100 + i * 0.8
        candles.append(
            SimpleNamespace(
                timestamp=i,
                open=c - 0.2,
                high=c + 1.0,
                low=c - 0.5,
                close=c,
                volume=100_000,
            )
        )
    # Last bar: push close and volume for breakout-ish shape
    last = candles[-1]
    candles[-1] = SimpleNamespace(
        timestamp=last.timestamp,
        open=last.close - 0.1,
        high=last.close + 3,
        low=last.close - 0.05,
        close=last.close + 2.5,
        volume=400_000,
    )
    tech = build_re001_technicals(
        candles,
        earnings_info={"earnings_clear": True},
        capital=1_000_000,
    )
    assert "error" not in tech or tech.get("baseline")
    assert "baseline" in tech
    assert "decision" in tech
    assert "scoring" in tech
    assert "risk" in tech
    assert "gates" in tech
    sc = tech["scoring"]
    assert abs(sc["weights"]["volume"] - 0.35) < 1e-9
    assert abs(sc["weights"]["trend"] - 0.30) < 1e-9
    assert abs(sc["weights"]["ha"] - 0.20) < 1e-9
    assert abs(sc["weights"]["rsi"] - 0.15) < 1e-9
    # HA wick must use HA values (field present)
    assert "ha_lower_wick_pct" in tech["baseline"]
    assert tech["baseline"]["rsi_threshold"] == 50.0
    assert tech["scoring"]["buy_threshold"] == COMPOSITE_BUY_THRESHOLD


def test_decision_builder_uses_engine_technicals(monkeypatch):
    from app.services.re001.decision_builder import build_decision_object

    payload = _tech_payload(composite=80.0)
    result = {
        "recommendation_state": "BUY",
        "market_regime": "Bull",
        "confidence_score": 0.8,
        "strategy_family": "Breakout Continuation",
        "strategy_name": "Breakout Continuation",
        "reason_codes": [],
        "evidence": {},
        "explanation": "ok",
        "portfolio_decision": {"status": "ok"},
        "risk_profile": {},
        "primary_strategy": "Breakout Continuation",
        "supporting_strategies": [],
        "rejected_strategies": [],
        "evaluation_status": "success",
        "technical_analysis": payload,
        "trade_guidance_payload": {
            "entry_low": 100.0,
            "entry_high": 100.0,
            "stop_loss": 97.0,
            "target_1": 109.0,
            "risk_reward_ratio": 3.0,
        },
    }
    ctx = build_lab_context(symbol="DB", market_regime=_Bull(), candles=_candles())
    obj = build_decision_object(ctx, result)
    assert obj.technical_analysis == payload
    assert obj.trade_guidance is not None
    assert obj.trade_guidance.complete is True
    assert obj.trade_guidance.stop_loss == 97.0
