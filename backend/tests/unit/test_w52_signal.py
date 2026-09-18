from app.services.strategies.breakout52w.signal import (
    buy_signal,
    first_failure,
    rank_candidates,
    screener_pass,
)


def test_close_equals_prior_high_passes():
    assert buy_signal(
        market_ok_flag=True, close=100.0, prior_high=100.0, volume=2.0, vol_sma=1.0
    )


def test_close_one_tick_below_fails():
    assert not buy_signal(
        market_ok_flag=True, close=99.99, prior_high=100.0, volume=2.0, vol_sma=1.0
    )


def test_volume_equal_fails():
    assert not buy_signal(
        market_ok_flag=True, close=101.0, prior_high=100.0, volume=1.0, vol_sma=1.0
    )


def test_first_failure_precedence():
    assert (
        first_failure(
            in_universe=True,
            prior_high=None,
            close=10.0,
            high=11.0,
            volume=2.0,
            vol_sma=1.0,
            market_ok_flag=True,
        )
        == "insufficient_history"
    )
    assert (
        first_failure(
            in_universe=True,
            prior_high=100.0,
            close=90.0,
            high=91.0,
            volume=2.0,
            vol_sma=1.0,
            market_ok_flag=True,
        )
        == "close_below_prior_high"
    )


def test_held_has_no_first_failure():
    assert first_failure(in_universe=True, held=True, prior_high=None) is None


def test_screener_pass_ignores_book_state():
    kwargs = dict(
        market_ok_flag=True, close=2005.2, prior_high=1984.0, volume=748_752.0, vol_sma=748_153.75
    )
    assert screener_pass(**kwargs) is True
    assert buy_signal(**kwargs, sold_today=True) is False
    assert buy_signal(**kwargs, held=True) is False


def test_rank_undefined_last_then_ticker():
    ranked = rank_candidates([("BBB", 0.1), ("AAA", None), ("CCC", 0.2)])
    assert [s for s, _m, _r in ranked] == ["CCC", "BBB", "AAA"]
