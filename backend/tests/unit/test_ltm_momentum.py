from app.services.strategies.ltm.momentum import is_eligible, momentum_252, rank_eligible, select_top


def test_exact_50_percent_ineligible():
    mom = momentum_252(150.0, 100.0)
    assert mom == 0.50
    assert is_eligible(mom) is False


def test_just_over_50_percent_eligible():
    mom = momentum_252(150.01, 100.0)
    assert mom is not None and mom > 0.50
    assert is_eligible(mom) is True


def test_missing_lookback_undefined():
    assert momentum_252(150.0, None) is None
    assert is_eligible(None) is False


def test_zero_prior_close_undefined():
    assert momentum_252(150.0, 0.0) is None


def test_ticker_tie_break_and_top_10():
    pairs = [(f"S{i:02d}", 1.0) for i in range(15)]
    ranked = rank_eligible(pairs)
    assert len(ranked) == 15
    assert [s for s, _m, _r in ranked] == sorted(f"S{i:02d}" for i in range(15))
    selected = select_top(ranked, 10)
    assert len(selected) == 10
    assert selected[0][0] == "S00"
