from datetime import date, timedelta

from app.services.strategies.ltm.book_engine import evaluate_session, replay_book
from app.services.strategies.ltm.scan_service import build_payload


def test_failed_gate_history_valid_has_backtest_object_never_selected():
    start = date(2020, 1, 1)
    dates = [start + timedelta(days=i) for i in range(260)]
    matrix = {"WEAK": {d: 100.0 for d in dates}}  # 0% momentum
    ev = evaluate_session(
        session_index=259,
        last_rebalance_index=252,
        closes_t={"WEAK": 100.0},
        closes_t_minus_252={"WEAK": 100.0},
        universe={"WEAK"},
    )
    replay = replay_book(dates, matrix, {"WEAK"})
    payload = build_payload(
        scan_id="s",
        evaluation_date=dates[-1],
        ev=ev,
        replay=replay,
        dates=dates,
        matrix=matrix,
        index={},
        universe={"WEAK"},
        mode="A",
        survivorship_biased=True,
        initial_capital=100000,
    )
    row = payload["recommendations"][0]
    assert row["first_failure"] == "failed_momentum_gate"
    assert row["backtest_1y"] is not None
    assert row["backtest_1y"]["never_selected_in_window"] is True
    assert payload["top5_positive"] == []


def test_insufficient_history_has_no_backtest():
    d0 = date(2026, 8, 1)
    ev = evaluate_session(
        session_index=10,
        last_rebalance_index=None,
        closes_t={"NEW": 50.0},
        closes_t_minus_252={"NEW": None},
        universe={"NEW"},
    )
    replay = {"state": replay_book([d0], {"NEW": {d0: 50.0}}, {"NEW"})["state"], "trades": [], "equity_curve": [], "cohorts": []}
    payload = build_payload(
        scan_id="s",
        evaluation_date=d0,
        ev=ev,
        replay=replay,
        dates=[d0],
        matrix={"NEW": {d0: 50.0}},
        index={},
        universe={"NEW"},
        mode="A",
        survivorship_biased=True,
        initial_capital=100000,
    )
    assert payload["recommendations"][0]["backtest_1y"] is None
    assert payload["recommendations"][0]["first_failure"] == "insufficient_history"
