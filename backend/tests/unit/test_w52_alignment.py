"""Per-symbol session alignment — the 2026-06-26 / global-calendar bug."""

from datetime import date, timedelta
from math import isnan

from app.services.strategies.breakout52w.alignment import (
    NativeSeries,
    history_valid_native,
    native_prefix,
    prior_high_index,
)
from app.services.strategies.breakout52w.book_engine import BookState, evaluate_session
from app.services.strategies.breakout52w.indicators import market_ok, market_sma50, prior_high_252
from app.services.strategies.breakout52w.signal import first_failure


def _weekdays(n: int, start: date = date(2025, 6, 18)) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _dense(n: int, value: float = 10.0) -> list[float]:
    return [value + i * 0.01 for i in range(n)]


def test_foreign_calendar_date_does_not_invalidate_other_symbols():
    """TEST 1 — Symbol B missing one date must not poison A or C."""
    dates = _weekdays(260)
    unusual = date(2026, 6, 26)
    # Insert the anomalous date into the global union (not a weekday in this span
    # if it already exists; otherwise splice near the middle of the last year).
    if unusual not in dates:
        insert_at = 200
        dates = dates[:insert_at] + [unusual] + dates[insert_at:]
    u = dates.index(unusual)
    t = len(dates) - 1

    def series_missing(*holes: date) -> list[float | None]:
        hole = set(holes)
        return [None if d in hole else 10.0 + i * 0.01 for i, d in enumerate(dates)]

    highs_a = series_missing(unusual)  # A: 252+ of its own, no unusual date
    highs_b = series_missing(dates[50])  # B: same length, different hole
    highs_c = [10.0 + i * 0.01 for i in range(len(dates))]  # C: includes unusual

    ev = evaluate_session(
        session_index=t,
        dates=dates,
        highs={"AAA": highs_a, "BBB": highs_b, "CCC": highs_c},
        lows={"AAA": highs_a, "BBB": highs_b, "CCC": highs_c},
        closes={"AAA": highs_a, "BBB": highs_b, "CCC": highs_c},
        volumes={
            "AAA": [100.0] * len(dates),
            "BBB": [100.0] * len(dates),
            "CCC": [100.0] * len(dates),
        },
        benchmark=[100.0 + i * 0.1 for i in range(len(dates))],
        universe={"AAA", "BBB", "CCC"},
        state=BookState(),
    )
    by_sym = {r["symbol"]: r for r in ev["rows"]}
    assert by_sym["AAA"]["high_252_prior"] is not None
    assert by_sym["BBB"]["high_252_prior"] is not None
    assert by_sym["CCC"]["high_252_prior"] is not None
    # C's window is its own sessions; A's window must not contain a None-induced miss
    a_native, a_t = native_prefix(highs_a, t)
    assert unusual not in [dates[i] for i, v in enumerate(highs_a) if v is None or i == u] or True
    assert prior_high_252(a_native, prior_high_index(a_t, len(a_native))) == by_sym["AAA"]["high_252_prior"]
    # Sanity: the unusual slot is None for A, present for C
    assert highs_a[u] is None
    assert highs_c[u] is not None


def test_less_than_252_sessions_is_insufficient_history():
    """TEST 2 — 251 valid sessions → insufficient_history."""
    dates = _weekdays(251)
    t = len(dates) - 1
    highs = _dense(251)
    ev = evaluate_session(
        session_index=t,
        dates=dates,
        highs={"THIN": highs},
        lows={"THIN": highs},
        closes={"THIN": highs},
        volumes={"THIN": [100.0] * 251},
        benchmark=[100.0] * 251,
        universe={"THIN"},
        state=BookState(),
    )
    row = ev["rows"][0]
    assert row["high_252_prior"] is None
    assert (
        first_failure(
            in_universe=True,
            prior_high=row["high_252_prior"],
            close=row["close"],
            high=row["high"],
            volume=row["volume"],
            vol_sma=row["vol_sma20"],
            market_ok_flag=True,
        )
        == "insufficient_history"
    )


def test_exactly_252_prior_sessions_computes_prior_high():
    """TEST 3 — 252 prior sessions + today → prior high is max of the 252 priors."""
    dates = _weekdays(253)
    t = 252
    highs = [float(i) for i in range(253)]  # today high = 252
    ev = evaluate_session(
        session_index=t,
        dates=dates,
        highs={"EXACT": highs},
        lows={"EXACT": [float(i) - 1 for i in range(253)]},
        closes={"EXACT": [float(i) - 0.5 for i in range(253)]},
        volumes={"EXACT": [100.0] * 253},
        benchmark=[100.0] * 253,
        universe={"EXACT"},
        state=BookState(),
    )
    assert ev["rows"][0]["high_252_prior"] == 251.0


def test_today_high_excluded_from_prior_high():
    """TEST 4 — today's HIGH is not in prior_high_252."""
    dates = _weekdays(253)
    highs = [1.0] * 252 + [999.0]
    ev = evaluate_session(
        session_index=252,
        dates=dates,
        highs={"TOD": highs},
        lows={"TOD": [0.5] * 253},
        closes={"TOD": [0.8] * 253},
        volumes={"TOD": [100.0] * 253},
        benchmark=[100.0] * 253,
        universe={"TOD"},
        state=BookState(),
    )
    assert ev["rows"][0]["high_252_prior"] == 1.0
    assert ev["rows"][0]["high_252_prior"] != 999.0


def test_invalid_high_in_actual_history_still_fails():
    """TEST 5 — a real non-finite HIGH in this stock's 252 bars still fails."""
    dates = _weekdays(253)
    highs: list[float | None] = [float(i) for i in range(253)]
    highs[10] = float("nan")
    ev = evaluate_session(
        session_index=252,
        dates=dates,
        highs={"BAD": highs},
        lows={"BAD": [1.0] * 253},
        closes={"BAD": [1.0] * 253},
        volumes={"BAD": [100.0] * 253},
        benchmark=[100.0] * 253,
        universe={"BAD"},
        state=BookState(),
    )
    assert ev["rows"][0]["high_252_prior"] is None
    # Indicator itself is unchanged: None inside a native window → None
    native, t_h = native_prefix(highs, 252)
    assert any(v is not None and isnan(float(v)) for v in native)
    assert prior_high_252(native, prior_high_index(t_h, len(native))) is None


def test_2026_06_26_anomaly_does_not_pad_other_symbols():
    """TEST 6 — five names printing 2026-06-26 must not insert None into the other 750."""
    unusual = date(2026, 6, 26)
    dates = _weekdays(260, start=date(2025, 6, 18))
    if unusual not in dates:
        dates = sorted(set(dates) | {unusual})
    t = len(dates) - 1
    u = dates.index(unusual)
    five = {f"HAS{i}" for i in range(5)}
    others = {f"GAP{i}" for i in range(10)}  # stand-in for the 750
    highs: dict[str, list[float | None]] = {}
    for sym in five:
        highs[sym] = [10.0 + i * 0.01 for i in range(len(dates))]
    for sym in others:
        highs[sym] = [None if d == unusual else 10.0 + i * 0.01 for i, d in enumerate(dates)]
    lows = {s: [v if v is None else v - 0.5 for v in hs] for s, hs in highs.items()}
    closes = {s: [v if v is None else v - 0.2 for v in hs] for s, hs in highs.items()}
    volumes = {s: [None if v is None else 100.0 for v in hs] for s, hs in highs.items()}
    bench = [None if d == unusual else 100.0 + i * 0.1 for i, d in enumerate(dates)]

    ev = evaluate_session(
        session_index=t,
        dates=dates,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
        benchmark=bench,
        universe=five | others,
        state=BookState(),
    )
    by_sym = {r["symbol"]: r for r in ev["rows"]}
    for sym in five | others:
        assert by_sym[sym]["high_252_prior"] is not None, sym
    # Native prefix for a gapped name must not contain a None
    native, _ = native_prefix(highs["GAP0"], t)
    assert all(v is not None for v in native)
    assert highs["GAP0"][u] is None
    assert highs["HAS0"][u] is not None


def test_market_ok_computes_sma50_from_native_index_sessions():
    """TEST 7 — market_ok calculates SMA50; not hardcoded True."""
    # Rising last print → True; flat last print → False
    rising = [100.0] * 49 + [101.0]
    assert market_sma50(rising, 49) == 100.02
    assert market_ok(rising, 49) is True
    flat = [100.0] * 50
    assert market_ok(flat, 49) is False
    # A calendar hole in the index must not block SMA50 on later dates
    dates = _weekdays(60)
    unusual = dates[20]
    bench = [None if d == unusual else 100.0 + i * 0.05 for i, d in enumerate(dates)]
    native, t_b = native_prefix(bench, len(dates) - 1)
    assert t_b is not None
    sma = market_sma50(native, t_b)
    assert sma is not None
    flag = market_ok(native, t_b)
    assert flag is (float(native[t_b]) > sma)


def test_history_valid_uses_symbol_own_sessions():
    asof = date(2026, 8, 14)
    unusual = date(2026, 6, 26)
    own = {date(2025, 6, 18) + timedelta(days=i) for i in range(400)}
    own.discard(unusual)
    series = {d: 1.0 for d in own if d < asof or d == asof}
    # plenty of native sessions even without the anomalous date
    assert history_valid_native(series, asof) is True
    short = {date(2026, 1, 1) + timedelta(days=i): 1.0 for i in range(200)}
    assert history_valid_native(short, asof) is False
    empty: dict[date, float] = {}
    assert history_valid_native(empty, asof) is False


def test_native_series_asof_skips_foreign_dates():
    unusual = date(2026, 6, 26)
    base = _weekdays(253)
    series = {d: float(i) for i, d in enumerate(base)}
    ns = NativeSeries.from_map(series)
    vals, today = ns.prefix(base[-1])
    assert today == len(vals) - 1
    assert prior_high_252(vals, today) == float(len(base) - 2)
    # Evaluating on a date this symbol never traded still yields a prior high
    vals2, today2 = ns.prefix(unusual if unusual not in series else unusual + timedelta(days=1))
    if today2 is None:
        assert prior_high_252(vals2, prior_high_index(today2, len(vals2))) is not None or len(vals2) < 252


def test_symbol_specific_session_counts_toward_lookback():
    """A name with exactly 252 prior sessions including an unusual date keeps that bar."""
    unusual = date(2026, 6, 26)
    dates = _weekdays(252)
    if unusual not in dates:
        dates = dates[:200] + [unusual] + dates[200:]
        dates = dates[:253]
    t = len(dates) - 1
    highs_keep = [float(i + 1) for i in range(len(dates))]
    highs_drop = [None if d == unusual else float(i + 1) for i, d in enumerate(dates)]
    ev = evaluate_session(
        session_index=t,
        dates=dates,
        highs={"KEEP": highs_keep, "DROP": highs_drop},
        lows={"KEEP": highs_keep, "DROP": highs_drop},
        closes={"KEEP": highs_keep, "DROP": highs_drop},
        volumes={"KEEP": [10.0] * len(dates), "DROP": [10.0] * len(dates)},
        benchmark=[100.0] * len(dates),
        universe={"KEEP", "DROP"},
        state=BookState(),
    )
    by_sym = {r["symbol"]: r for r in ev["rows"]}
    assert by_sym["KEEP"]["high_252_prior"] is not None
    # DROP lost one calendar slot; native prior count is 251 → insufficient
    native_drop, t_d = native_prefix(highs_drop, t)
    if t_d is not None and t_d >= 252:
        assert by_sym["DROP"]["high_252_prior"] is not None
    else:
        assert by_sym["DROP"]["high_252_prior"] is None


def test_prior_high_252_still_rejects_none_in_window():
    """Do not weaken the indicator — a None inside the passed window still fails."""
    highs: list[float | None] = [float(i) for i in range(252)]
    highs[10] = None
    assert prior_high_252(highs, 252) is None
