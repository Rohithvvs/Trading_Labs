"""Session completeness for strategy-grade daily data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class CompletenessResult:
    trade_date: date
    active_count: int
    present_count: int
    coverage_ratio: float
    index_present: bool
    missing_symbols: list[str] = field(default_factory=list)
    success: bool = False
    threshold: float = 0.99

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date.isoformat(),
            "active_count": self.active_count,
            "present_count": self.present_count,
            "coverage_ratio": self.coverage_ratio,
            "index_present": self.index_present,
            "missing_symbol_count": len(self.missing_symbols),
            "missing_symbols_sample": self.missing_symbols[:25],
            "success": self.success,
            "threshold": self.threshold,
        }


def session_completeness(
    trade_date: date,
    active_symbols: list[str],
    present_symbols: set[str],
    index_present: bool,
    threshold: float = 0.99,
) -> CompletenessResult:
    active = list(dict.fromkeys(active_symbols))
    active_count = len(active)
    present_count = sum(1 for s in active if s in present_symbols)
    coverage = (present_count / active_count) if active_count else 0.0
    missing = [s for s in active if s not in present_symbols]
    ok = active_count > 0 and coverage >= threshold and index_present
    return CompletenessResult(
        trade_date=trade_date,
        active_count=active_count,
        present_count=present_count,
        coverage_ratio=coverage,
        index_present=index_present,
        missing_symbols=missing,
        success=ok,
        threshold=threshold,
    )
