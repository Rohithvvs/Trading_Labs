from app.services.strategies.ltm.calendar import clock_status


def test_clock_survives_reload_of_last_rebalance_index():
    """Persisted last_rebalance_index must not reset the 252-session clock."""
    last = 252
    status, since, fire = clock_status(300, last)
    assert fire is False
    assert status == "MID_CYCLE"
    assert since == 48
    # Same inputs after "reload" — identical clock
    status2, since2, fire2 = clock_status(300, last)
    assert (status2, since2, fire2) == (status, since, fire)
