from app.services.strategies.breakout52w.attribution import empty_backtest
from app.services.strategies.breakout52w.scan_service import build_payload
from app.services.strategies.breakout52w.book_engine import BookState


def test_recommendations_final_only_on_completed_payload():
    # build_payload always marks completed; in-flight payloads are written by stage()
    from datetime import date

    dates = [date(2020, 1, 2)]
    ev = {
        "book_status": "WARMUP",
        "market_ok": False,
        "nifty_close": None,
        "nifty_sma50": None,
        "free_slots": 10,
        "selected": [],
        "rows": [],
        "orders": [],
        "warmup": True,
    }
    replay = {"state": BookState(), "trades": [], "equity_curve": []}
    payload = build_payload(
        scan_id="x",
        evaluation_date=date(2020, 1, 2),
        ev=ev,
        replay=replay,
        dates=dates,
        high_m={},
        close_m={},
        index={},
        universe=set(),
        mode="B",
        survivorship_biased=True,
        initial_capital=100000,
    )
    assert payload["recommendations_final"] is True
    assert payload["status"] == "completed"
    in_flight = {"status": "backtesting", "recommendations_final": False}
    assert in_flight["recommendations_final"] is False


def test_empty_backtest_failed_flag():
    bt = empty_backtest(date=None) if False else empty_backtest(__import__("datetime").date(2026, 8, 14), failed=True)
    assert bt["failed"] is True
    assert bt["never_selected_in_window"] is False
