"""RE-001 Trend Continuation Recommendation Engine (lab / non-production).

Standalone engine: receives the scan's full stage universe via independent
lab orchestration (its own data validation from shared OHLCV — never gated by
the screener data_valid set, never Production top-N shortlist as a selection
gate). Production RecommendationService labels remain authoritative for
Production.
"""

from .registry import is_re001_active, get_re001_registration
from .runner import run_re001_isolated, run_re001_isolated_async

__all__ = [
    "is_re001_active",
    "get_re001_registration",
    "run_re001_isolated",
    "run_re001_isolated_async",
]
