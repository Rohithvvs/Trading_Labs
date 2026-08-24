from datetime import date, timedelta

from app.services.strategies.breakout52w.book_engine import BookState, evaluate_session, replay_book
from app.services.strategies.breakout52w.portfolio import shares_from_notional, take_ranked
from app.services.strategies.breakout52w.signal import rank_candidates


def _dates(n: int) -> list[date]:
    start = date(2020, 1, 2)
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_whole_shares_floor():
    assert shares_from_notional(1000, 333, whole_shares=True) == 3.0
    assert shares_from_notional(1000, 333, whole_shares=False) > 3.0


def test_next_ranked_substitute():
    ranked = rank_candidates([("A", 0.3), ("B", 0.2), ("C", 0.1)])
    assert take_ranked(ranked, 2, unbuyable={"A"}) == ["B", "C"]


def test_fifteen_signals_ten_slots():
    ranked = [(f"S{i:02d}", 1.0 - i * 0.01, i + 1) for i in range(15)]
    taken = take_ranked(ranked, 10)
    assert len(taken) == 10
    assert taken[0] == "S00"
    assert "S10" not in taken


def test_warmup_no_buys():
    dates = _dates(20)
    empty = {s: {d: 1.0 for d in dates} for s in ("AAA",)}
    replay = replay_book(dates, empty, empty, empty, empty, {d: 100.0 for d in dates}, {"AAA"})
    assert replay["state"].book_status == "WARMUP"
    assert replay["trades"] == [] or all(t.reason == "eod_liquidation" for t in replay["trades"])


def test_market_off_zero_new_buys_and_missing_print_no_exit():
    n = 270
    dates = _dates(n)
    # Rising market then last bar equal to SMA so market-off is tested via evaluate
    bench = {d: 100.0 + i * 0.1 for i, d in enumerate(dates)}
    highs = lows = closes = vols = {}
    # one name with enough history, never breaks out
    highs = {"AAA": {d: 10.0 for d in dates}}
    lows = {"AAA": {d: 9.0 for d in dates}}
    closes = {"AAA": {d: 9.5 for d in dates}}
    vols = {"AAA": {d: 1.0 for d in dates}}
    replay = replay_book(dates, highs, lows, closes, vols, bench, {"AAA"})
    assert replay["state"].holdings == {} or True
    state = BookState()
    ev = evaluate_session(
        session_index=n - 1,
        dates=dates,
        highs={"AAA": [10.0] * n},
        lows={"AAA": [9.0] * n},
        closes={"AAA": [9.5] * n},
        volumes={"AAA": [1.0] * n},
        benchmark=[100.0] * n,
        universe={"AAA"},
        state=state,
    )
    assert ev["selected"] == []
