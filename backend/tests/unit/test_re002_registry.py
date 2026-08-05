"""Registry stage/enabled matrix and experiment gate."""

from app.services.re002.registry import get_re002_registration, is_re002_active


def _force(**kwargs):
    from app.config import settings as settings_mod

    for k, v in kwargs.items():
        object.__setattr__(settings_mod, k, v)


def test_registration_identity():
    reg = get_re002_registration()
    assert reg.engine_id == "RE-002"
    assert reg.name


def test_inactive_when_disabled(monkeypatch):
    monkeypatch.delenv("RE002_EXPERIMENT_ID", raising=False)
    _force(re002_enabled=False, re002_stage="LAB_SHADOW", re002_experiment_id="exp")
    assert is_re002_active() is False


def test_active_with_lab_default_experiment(monkeypatch):
    """Lab stage without explicit experiment still active via default long-lived binding."""
    monkeypatch.delenv("RE002_EXPERIMENT_ID", raising=False)
    monkeypatch.delenv("RE002_EXPERIMENT_PAUSED", raising=False)
    _force(
        re002_enabled=True,
        re002_stage="LAB_SHADOW",
        re002_experiment_id=None,
        re002_experiment_paused=False,
    )
    assert is_re002_active() is True
    reg = get_re002_registration()
    assert reg.active is True
    assert reg.experiment_id == "re002-long-lived"


def test_active_with_explicit_experiment(monkeypatch):
    monkeypatch.setenv("RE002_EXPERIMENT_ID", "exp-ok")
    monkeypatch.delenv("RE002_EXPERIMENT_PAUSED", raising=False)
    _force(
        re002_enabled=True,
        re002_stage="LAB_SHADOW",
        re002_experiment_id="exp-ok",
        re002_experiment_paused=False,
    )
    assert is_re002_active() is True
    reg = get_re002_registration()
    assert reg.experiment_id == "exp-ok"
