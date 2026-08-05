"""RE-002 engine registration from settings."""

from __future__ import annotations

from ...config.settings import settings
from ...schemas.re002 import Re002Registration, Re002Stage


def get_re002_registration() -> Re002Registration:
    stage = (settings.re002_stage or "OFF").strip().upper()
    if stage not in {"OFF", "LAB_SHADOW", "PAPER_LINKED"}:
        stage = "OFF"
    experiment_id = None
    try:
        from .experiment_binding import resolve_active_experiment_id

        experiment_id = resolve_active_experiment_id()
    except Exception:
        experiment_id = None
    active = False
    try:
        active = bool(is_re002_active())
    except Exception:
        active = False
    return Re002Registration(
        engine_id="RE-002",
        name="Relative Strength Momentum Engine",
        engine_version=settings.re002_version or "1.0",
        stage=stage,  # type: ignore[arg-type]
        enabled=bool(settings.re002_enabled),
        experiment_id=experiment_id,
        active=active,
    )


def is_re002_active() -> bool:
    """True when RE-002 should evaluate (enabled and stage is a lab stage)."""
    if hasattr(settings, "is_re002_active"):
        try:
            if not settings.is_re002_active():
                return False
        except Exception:
            if not bool(settings.re002_enabled):
                return False
            stage = str(settings.re002_stage or "OFF").strip().upper()
            if stage not in {"LAB_SHADOW", "PAPER_LINKED"}:
                return False
    else:
        if not bool(settings.re002_enabled):
            return False
        stage = str(settings.re002_stage or "OFF").strip().upper()
        if stage not in {"LAB_SHADOW", "PAPER_LINKED"}:
            return False
    try:
        from .experiment_binding import side_effects_allowed

        return side_effects_allowed()
    except Exception:
        return True
