"""Flag OFF / pause produces zero runner side effects."""

import asyncio

from app.services.re002.runner import run_re002_isolated_async


def _force(**kwargs):
    from app.config import settings as settings_mod

    for k, v in kwargs.items():
        object.__setattr__(settings_mod, k, v)


def test_stage_off_zero_decisions(monkeypatch):
    monkeypatch.setenv("RE002_ENABLED", "true")
    monkeypatch.setenv("RE002_STAGE", "OFF")
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-1")
    _force(re002_enabled=True, re002_stage="OFF", re002_experiment_id="exp-1")
    assert asyncio.run(run_re002_isolated_async(symbol="ABC")) is None


def test_enabled_paused_zero_decisions(monkeypatch):
    monkeypatch.setenv("RE002_ENABLED", "true")
    monkeypatch.setenv("RE002_STAGE", "LAB_SHADOW")
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-1")
    monkeypatch.setenv("RE002_EXPERIMENT_PAUSED", "true")
    _force(
        re002_enabled=True,
        re002_stage="LAB_SHADOW",
        re002_experiment_id="exp-1",
        re002_experiment_paused=True,
    )
    assert asyncio.run(run_re002_isolated_async(symbol="ABC")) is None
