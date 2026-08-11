"""RE-002 Relative Strength Momentum Engine (lab / non-production).

Standalone engine: receives the scan's full stage universe via independent
lab orchestration (its own data validation from shared OHLCV — never gated by
the screener data_valid set, never Production top-N shortlist as a selection
gate). Production RecommendationService labels remain authoritative for
Production.
"""

from .registry import is_re002_active, get_re002_registration
from .runner import run_re002_isolated, run_re002_isolated_async

__all__ = [
    "is_re002_active",
    "get_re002_registration",
    "run_re002_isolated",
    "run_re002_isolated_async",
]
