from datetime import date, timedelta

from app.services.strategies.ltm.book_engine import evaluate_session, replay_book
from app.services.strategies.ltm.portfolio import target_notionals


def test_zero_eligible_all_cash_signal_reject():
    ev = evaluate_session(
        session_index=252,
        last_rebalance_index=None,
        closes_t={"AAA": 100.0},
        closes_t_minus_252={"AAA": 90.0},
        universe={"AAA"},
    )
    assert ev["selected"] == []
    assert ev["fire"] is True
    assert ev["rows"][0]["signal"] == "REJECT"
    assert ev["rows"][0]["first_failure"] == "failed_momentum_gate"


def test_fifteen_eligible_selects_ten():
    closes_t = {f"S{i:02d}": 200.0 + i for i in range(15)}
    closes_prev = {f"S{i:02d}": 100.0 for i in range(15)}
    ev = evaluate_session(
        session_index=252,
        last_rebalance_index=None,
        closes_t=closes_t,
        closes_t_minus_252=closes_prev,
        universe=set(closes_t),
    )
    assert len(ev["selected"]) == 10
    # Highest momentum is largest close / 100
    assert ev["selected"][0][0] == "S14"


def test_mode_a_three_names_split_cash():
    n = target_notionals(
        selected=["A", "B", "C"],
        cash_after_sells=90_000,
        equity=90_000,
        mode="A",
    )
    assert n == {"A": 30_000.0, "B": 30_000.0, "C": 30_000.0}


def test_mode_b_three_names_leave_cash():
    n = target_notionals(
        selected=["A", "B", "C"],
        cash_after_sells=100_000,
        equity=100_000,
        mode="B",
    )
    assert n == {"A": 10_000.0, "B": 10_000.0, "C": 10_000.0}


def test_unbuyable_redistribute_mode_a():
    n = target_notionals(
        selected=["A", "B", "C"],
        cash_after_sells=90_000,
        equity=90_000,
        mode="A",
        skip={"B"},
    )
    assert set(n) == {"A", "C"}
    assert n["A"] == 45_000.0


def test_replay_first_rebalance_and_eod_liq():
    start = date(2020, 1, 1)
    dates = [start + timedelta(days=i) for i in range(260)]
    # Constant 2x after bar 252 so everyone is eligible
    matrix = {
        "AAA": {d: (100.0 if i < 1 else 220.0) for i, d in enumerate(dates)},
        "BBB": {d: (80.0 if i < 1 else 200.0) for i, d in enumerate(dates)},
    }
    # Need lookback 252: set first print and last print
    for i, d in enumerate(dates):
        matrix["AAA"][d] = 100.0 if i == 0 else 100.0 * (1.6 if i >= 252 else 1.0)
        matrix["BBB"][d] = 80.0 if i == 0 else 80.0 * (1.6 if i >= 252 else 1.0)
    out = replay_book(dates, matrix, {"AAA", "BBB"}, initial_capital=100_000)
    assert out["cohorts"], "expected a rebalance cohort"
    assert out["cohorts"][0]["date"] == dates[252].isoformat()
    assert {t.reason for t in out["trades"]} & {"eod_liquidation", "REBALANCE"}
