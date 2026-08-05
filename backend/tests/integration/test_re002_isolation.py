"""RE-002 fail-open isolation and inactive / experiment gates."""

import asyncio

from app.services.re002.runner import run_re002_isolated_async


def _force_settings(**kwargs):
    from app.config import settings as settings_mod

    for k, v in kwargs.items():
        object.__setattr__(settings_mod, k, v)


def test_inactive_returns_none(monkeypatch):
    monkeypatch.setenv("RE002_ENABLED", "false")
    monkeypatch.setenv("RE002_STAGE", "OFF")
    monkeypatch.delenv("RE002_EXPERIMENT_ID", raising=False)
    _force_settings(re002_enabled=False, re002_stage="OFF", re002_experiment_id=None)

    result = asyncio.run(run_re002_isolated_async(symbol="X"))
    assert result is None


def test_enabled_without_explicit_experiment_uses_default_and_evaluates(monkeypatch):
    monkeypatch.setenv("RE002_ENABLED", "true")
    monkeypatch.setenv("RE002_STAGE", "LAB_SHADOW")
    monkeypatch.delenv("RE002_EXPERIMENT_ID", raising=False)
    monkeypatch.delenv("RE002_EXPERIMENT_PAUSED", raising=False)
    _force_settings(
        re002_enabled=True,
        re002_stage="LAB_SHADOW",
        re002_experiment_id=None,
        re002_experiment_paused=False,
        re002_persist_decisions=False,
        re002_timeout_ms=3000.0,
    )

    class _MR:
        market_state = "FAVORABLE"
        trend_state = "BULLISH"
        new_entry_allowed = True

    class _Tech:
        score = 40
        signal = "neutral"

    class C:
        def __init__(self, i):
            self.close = 50 + i * 0.1
            self.volume = 900_000

    result = asyncio.run(
        run_re002_isolated_async(
            symbol="X",
            candles=[C(i) for i in range(60)],
            technical_results=[_Tech()],
            market_regime=_MR(),
            sector_overlay=type("SO", (), {"sector_rs_20": -1.0})(),
            db_session_factory=None,
        )
    )
    assert result is not None
    assert result.engine_id == "RE-002"
    assert result.experiment_id == "re002-long-lived"
    assert result.recommendation_state in {"BUY", "WATCH", "REJECT"}


def test_timeout_emits_diagnostic_reject_not_raise(monkeypatch):
    """Timeout path must not raise into caller; returns diagnostic REJECT."""
    monkeypatch.setenv("RE002_ENABLED", "true")
    monkeypatch.setenv("RE002_STAGE", "LAB_SHADOW")
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-timeout-test")
    _force_settings(
        re002_enabled=True,
        re002_stage="LAB_SHADOW",
        re002_experiment_id="exp-timeout-test",
        re002_experiment_paused=False,
        re002_timeout_ms=200.0,
        re002_persist_decisions=False,
    )

    def _slow(*_a, **_k):
        import time

        time.sleep(2.0)
        raise AssertionError("should not complete")

    monkeypatch.setattr(
        "app.services.re002.runner._evaluate_sync",
        _slow,
    )

    result = asyncio.run(
        run_re002_isolated_async(
            symbol="TIMEOUT",
            candles=[],
            technical_results=[],
            production_recommendation=None,
            market_regime=None,
            db_session_factory=None,
        )
    )
    assert result is not None
    assert result.recommendation_state == "REJECT"
    assert result.evaluation_status == "timeout"
    assert "re002_timeout" in (result.reason_codes or [])
