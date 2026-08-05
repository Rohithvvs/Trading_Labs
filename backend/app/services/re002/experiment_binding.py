"""Long-lived RE-002 experiment binding (settings + optional governance)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("app.re002")

# Optional env override for ops without full ExperimentService round-trip in scan path
_ENV_EXPERIMENT_ID = "RE002_EXPERIMENT_ID"
_ENV_EXPERIMENT_PAUSED = "RE002_EXPERIMENT_PAUSED"

# Stable long-lived default when RE-002 is lab-enabled without an explicit experiment id.
# Ensures FR-028 attribution always has a non-null experiment_id without blocking evaluation.
_DEFAULT_LONG_LIVED_EXPERIMENT_ID = "re002-long-lived"


def resolve_active_experiment_id() -> str | None:
    """Return active long-lived RE-002 experiment id (explicit or default lab binding)."""
    raw = (os.environ.get(_ENV_EXPERIMENT_ID) or "").strip()
    if raw:
        return raw
    # Settings field if present
    try:
        from ...config.settings import settings

        eid = getattr(settings, "re002_experiment_id", None)
        if eid:
            return str(eid).strip() or None
        # Auto-bind when engine is in a lab stage so ENABLED+STAGE alone (like RE-001 ops)
        # still produces attributed decisions. Explicit RE002_EXPERIMENT_ID always wins.
        if bool(getattr(settings, "re002_enabled", False)):
            stage = str(getattr(settings, "re002_stage", "OFF") or "OFF").strip().upper()
            if stage in {"LAB_SHADOW", "PAPER_LINKED"}:
                return _DEFAULT_LONG_LIVED_EXPERIMENT_ID
    except Exception:
        pass
    return None


def _is_paused() -> bool:
    raw = (os.environ.get(_ENV_EXPERIMENT_PAUSED) or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    try:
        from ...config.settings import settings

        return bool(getattr(settings, "re002_experiment_paused", False))
    except Exception:
        return False


def side_effects_allowed() -> bool:
    """
    Gate new RE-002 evaluation side effects (FR-028).
    - Requires a resolvable long-lived experiment id (explicit or default lab binding)
    - If experiment is paused → False
    """
    if _is_paused():
        return False
    if not resolve_active_experiment_id():
        return False
    return True


def stamp_experiment_id(payload: dict[str, Any]) -> dict[str, Any]:
    eid = resolve_active_experiment_id()
    if eid:
        payload = dict(payload)
        payload["experiment_id"] = eid
    return payload
