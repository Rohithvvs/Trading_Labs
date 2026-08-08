"""Experiment binding pause gate and required experiment id (FR-028)."""

from app.services.re002 import experiment_binding as eb


def test_side_effects_blocked_when_engine_off(monkeypatch):
    monkeypatch.delenv("RE002_EXPERIMENT_PAUSED", raising=False)
    monkeypatch.delenv("RE002_EXPERIMENT_ID", raising=False)
    from app.config import settings as settings_mod

    object.__setattr__(settings_mod, "re002_enabled", False)
    object.__setattr__(settings_mod, "re002_stage", "OFF")
    object.__setattr__(settings_mod, "re002_experiment_id", None)
    object.__setattr__(settings_mod, "re002_experiment_paused", False)
    assert eb.side_effects_allowed() is False


def test_side_effects_allowed_with_lab_default_experiment(monkeypatch):
    """ENABLED + LAB_SHADOW without explicit id still binds default long-lived experiment."""
    monkeypatch.delenv("RE002_EXPERIMENT_PAUSED", raising=False)
    monkeypatch.delenv("RE002_EXPERIMENT_ID", raising=False)
    from app.config import settings as settings_mod

    object.__setattr__(settings_mod, "re002_enabled", True)
    object.__setattr__(settings_mod, "re002_stage", "LAB_SHADOW")
    object.__setattr__(settings_mod, "re002_experiment_id", None)
    object.__setattr__(settings_mod, "re002_experiment_paused", False)
    assert eb.resolve_active_experiment_id() == "re002-long-lived"
    assert eb.side_effects_allowed() is True


def test_side_effects_allowed_with_experiment(monkeypatch):
    monkeypatch.delenv("RE002_EXPERIMENT_PAUSED", raising=False)
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-re002-1")
    assert eb.side_effects_allowed() is True


def test_paused_blocks(monkeypatch):
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-re002-1")
    monkeypatch.setenv("RE002_EXPERIMENT_PAUSED", "true")
    assert eb.side_effects_allowed() is False


def test_resolve_experiment_id(monkeypatch):
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-re002-1")
    assert eb.resolve_active_experiment_id() == "exp-re002-1"
