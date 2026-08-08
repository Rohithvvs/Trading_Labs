"""Regime strategy priority tables."""

from app.services.re002.strategy_config import PRIMARY_FAMILIES, REGIME_PRIMARY_PRIORITY


def test_all_regimes_have_priorities():
    for r in ("Bull", "Sideways", "Bear"):
        assert r in REGIME_PRIMARY_PRIORITY
        assert len(REGIME_PRIMARY_PRIORITY[r]) == len(PRIMARY_FAMILIES)


def test_bull_prefers_momentum():
    assert REGIME_PRIMARY_PRIORITY["Bull"][0] == "Relative Strength Momentum Continuation"
