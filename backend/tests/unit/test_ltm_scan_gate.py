import inspect

from app.services.strategies.ltm import scan_service


def test_scan_service_does_not_import_production_scan_store():
    src = inspect.getsource(scan_service)
    assert "scan_store" not in src
    assert "load_latest_scan" not in src


def test_completed_payload_flags_recommendations_final():
    from datetime import date

    from app.services.strategies.ltm.book_engine import BookState, evaluate_session, replay_book
    from app.services.strategies.ltm.scan_service import build_payload

    dates = [date(2020, 1, 1)]
    # Tiny warmup-only matrix: still produces a payload with final=true only via build_payload
    ev = evaluate_session(
        session_index=0,
        last_rebalance_index=None,
        closes_t={"AAA": 10.0},
        closes_t_minus_252={"AAA": None},
        universe={"AAA"},
    )
    replay = {"state": BookState(), "trades": [], "equity_curve": [], "cohorts": []}
    payload = build_payload(
        scan_id="x",
        evaluation_date=dates[0],
        ev=ev,
        replay=replay,
        dates=dates,
        matrix={"AAA": {dates[0]: 10.0}},
        index={},
        universe={"AAA"},
        mode="A",
        survivorship_biased=True,
        initial_capital=100000,
    )
    assert payload["recommendations_final"] is True
    assert payload["warmup"] is True
    assert payload["strategy_id"] == "17_long_term_mom"
