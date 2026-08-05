"""RE-002 Relative Strength Momentum Engine (lab / non-production).

Production shortlists and RecommendationService labels remain authoritative.
RE-002 runs isolated after production recommendation when enabled.
"""

from .registry import is_re002_active, get_re002_registration
from .runner import run_re002_isolated, run_re002_isolated_async

__all__ = [
    "is_re002_active",
    "get_re002_registration",
    "run_re002_isolated",
    "run_re002_isolated_async",
]
