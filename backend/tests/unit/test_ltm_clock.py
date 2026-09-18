from app.services.strategies.ltm.calendar import clock_status, sessions_to_rebalance


def test_warmup_before_252():
    status, since, fire = clock_status(251, None)
    assert status == "WARMUP"
    assert fire is False
    assert since == 0
    assert sessions_to_rebalance(251, None) == 1


def test_first_rebalance_at_252():
    status, since, fire = clock_status(252, None)
    assert status == "REBALANCE"
    assert fire is True
    assert since == 0


def test_mid_cycle_not_calendar_year():
    status, since, fire = clock_status(300, 252)
    assert status == "MID_CYCLE"
    assert fire is False
    assert since == 48
    assert sessions_to_rebalance(300, 252) == 204


def test_next_rebalance_252_sessions_later():
    status, _since, fire = clock_status(504, 252)
    assert status == "REBALANCE"
    assert fire is True
