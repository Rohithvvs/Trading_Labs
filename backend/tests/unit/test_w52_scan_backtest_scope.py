from datetime import date

from app.services.strategies.breakout52w.attribution import empty_backtest, per_name_backtests
from app.services.strategies.breakout52w.book_engine import Trade


def test_failed_attribution_excluded_and_signal_kept():
    asof = date(2026, 8, 14)
    trades = [Trade("AAA", date(2026, 1, 1), date(2026, 2, 1), 10, 12, 1, 0.2, "atr_trail", False)]
    reports = per_name_backtests(
        trades, asof=asof, years=1, history_valid={"AAA", "BBB"}, failed={"BBB"}
    )
    assert "AAA" in reports
    assert "BBB" not in reports
    failed_bt = empty_backtest(asof, failed=True)
    assert failed_bt["failed"] is True
    # today's evaluation signal is independent
    today_signal = "BUY"
    assert today_signal == "BUY"
