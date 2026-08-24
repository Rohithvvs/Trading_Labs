from app.services.score_recommendation_service import (
    BUY_SCORE_THRESHOLD,
    WATCH_SCORE_THRESHOLD,
    classify_signal_from_score,
)
from app.services.strategies.breakout52w.scan_service import (
    published_trade_levels as w52_levels,
)
from app.services.strategies.breakout52w.trail import initial_tsl
from app.services.strategies.ltm.scan_service import published_trade_levels as ltm_levels


def test_composite_thresholds_are_68_and_55():
    assert BUY_SCORE_THRESHOLD == 68.0
    assert WATCH_SCORE_THRESHOLD == 55.0
    assert classify_signal_from_score(68.0) == "BUY"
    assert classify_signal_from_score(67.99) == "WATCH"
    assert classify_signal_from_score(55.0) == "WATCH"
    assert classify_signal_from_score(54.99) == "REJECT"


def test_ltm_watch_publishes_entry_but_never_invents_sl_or_target():
    levels = ltm_levels(signal="WATCH", close_t=293.88)
    assert levels["entry"] == 293.88
    assert levels["stop_loss"] is None
    assert levels["target"] is None
    assert levels["risk_reward"] is None


def test_ltm_reject_has_no_trade_plan():
    levels = ltm_levels(signal="REJECT", close_t=100.0)
    assert levels == {"entry": None, "stop_loss": None, "target": None, "risk_reward": None}


def test_w52_watch_uses_existing_initial_tsl_formula():
    levels = w52_levels(signal="WATCH", close=100.0, atr14=2.0, holding_tsl=None)
    assert levels["entry"] == 100.0
    assert levels["stop_loss"] == initial_tsl(100.0, 2.0)
    assert levels["target"] is None
    assert levels["risk_reward"] is None


def test_w52_hold_prefers_book_tsl():
    levels = w52_levels(signal="HOLD", close=110.0, atr14=2.0, holding_tsl=101.0)
    assert levels["entry"] == 110.0
    assert levels["stop_loss"] == 101.0
    assert levels["target"] is None


def test_w52_reject_has_no_trade_plan():
    levels = w52_levels(signal="REJECT", close=100.0, atr14=2.0, holding_tsl=None)
    assert levels == {"entry": None, "stop_loss": None, "target": None, "risk_reward": None}
