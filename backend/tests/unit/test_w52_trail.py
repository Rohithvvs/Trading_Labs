from app.services.strategies.breakout52w.trail import (
    initial_tsl,
    reconstruct_tsl,
    should_exit,
    update_trail,
)


def test_entry_100_atr_2():
    assert initial_tsl(100.0, 2.0) == 94.0


def test_no_ratchet_without_new_hwm():
    hwm, tsl = update_trail(hwm=100.0, tsl=94.0, close=99.0, atr=2.0, is_entry_bar=False)
    assert (hwm, tsl) == (100.0, 94.0)


def test_ratchet_on_new_close_high():
    hwm, tsl = update_trail(hwm=100.0, tsl=94.0, close=110.0, atr=3.0, is_entry_bar=False)
    assert hwm == 110.0
    assert tsl == 101.0


def test_atr_expansion_does_not_lower_stop():
    hwm, tsl = update_trail(hwm=110.0, tsl=101.0, close=112.0, atr=6.0, is_entry_bar=False)
    assert hwm == 112.0
    assert tsl == 101.0


def test_exit_strict_below():
    assert not should_exit(close=101.0, tsl=101.0, is_entry_bar=False)
    assert should_exit(close=100.99, tsl=101.0, is_entry_bar=False)


def test_no_exit_on_entry_bar():
    assert not should_exit(close=50.0, tsl=94.0, is_entry_bar=True)
    hwm, tsl = update_trail(hwm=100.0, tsl=94.0, close=120.0, atr=1.0, is_entry_bar=True)
    assert (hwm, tsl) == (100.0, 94.0)


def test_nan_atr_fallback():
    assert initial_tsl(100.0, None) == 90.0


def test_reconstruct_never_lowers():
    assert reconstruct_tsl(last_known_tsl=101.0, hwm=112.0, atr=6.0) == 101.0
