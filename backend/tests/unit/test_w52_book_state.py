from app.services.strategies.breakout52w.trail import reconstruct_tsl, update_trail


def test_reload_does_not_lower_tsl():
    hwm, tsl = update_trail(hwm=110.0, tsl=101.0, close=105.0, atr=3.0, is_entry_bar=False)
    restored = reconstruct_tsl(last_known_tsl=tsl, hwm=hwm, atr=3.0)
    assert restored >= tsl


def test_market_ok_false_no_new_buys_via_evaluate():
    from datetime import date, timedelta

    from app.services.strategies.breakout52w.book_engine import BookState, evaluate_session

    n = 260
    dates = []
    d = date(2020, 1, 2)
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    bench = [100.0] * n  # equal to SMA → market off
    highs = {"AAA": [100.0 + i for i in range(n)]}
    ev = evaluate_session(
        session_index=n - 1,
        dates=dates,
        highs=highs,
        lows={"AAA": [99.0] * n},
        closes={"AAA": [100.0 + i for i in range(n)]},
        volumes={"AAA": [2.0] * n},
        benchmark=bench,
        universe={"AAA"},
        state=BookState(),
    )
    assert ev["book_status"] in {"MARKET_OFF", "WARMUP"}
    assert ev["selected"] == []
    assert ev["market_ok"] is False
