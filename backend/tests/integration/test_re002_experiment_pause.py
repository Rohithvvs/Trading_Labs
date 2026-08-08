"""Pause or missing experiment blocks runner side effects."""

import asyncio

from app.services.re002.runner import run_re002_isolated_async


def _force(**kwargs):
    from app.config import settings as settings_mod

    for k, v in kwargs.items():
        object.__setattr__(settings_mod, k, v)


def test_pause_blocks(monkeypatch):
    monkeypatch.setenv("RE002_ENABLED", "true")
    monkeypatch.setenv("RE002_STAGE", "LAB_SHADOW")
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-pause")
    monkeypatch.setenv("RE002_EXPERIMENT_PAUSED", "true")
    _force(
        re002_enabled=True,
        re002_stage="LAB_SHADOW",
        re002_experiment_id="exp-pause",
        re002_experiment_paused=True,
    )
    assert asyncio.run(run_re002_isolated_async(symbol="P")) is None


def test_unpause_allows_eval(monkeypatch):
    monkeypatch.setenv("RE002_ENABLED", "true")
    monkeypatch.setenv("RE002_STAGE", "LAB_SHADOW")
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-run")
    monkeypatch.delenv("RE002_EXPERIMENT_PAUSED", raising=False)
    _force(
        re002_enabled=True,
        re002_stage="LAB_SHADOW",
        re002_experiment_id="exp-run",
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
            symbol="P",
            candles=[C(i) for i in range(60)],
            technical_results=[_Tech()],
            market_regime=_MR(),
            sector_overlay=type("SO", (), {"sector_rs_20": -1.0})(),
            experiment_id="exp-run",
            db_session_factory=None,
        )
    )
    assert result is not None
    assert result.engine_id == "RE-002"
    assert result.experiment_id == "exp-run"
