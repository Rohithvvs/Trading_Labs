"""Simple long/short period returns. Stop/target/trail are reserved, not mixed in."""

from __future__ import annotations

from dataclasses import dataclass

from .schema import PositionRules


@dataclass
class ReturnBreakdown:
    entry_price: float | None
    exit_price: float | None
    return_pct: float | None
    method: str
    side: str
    formula: str | None
    bucket: str | None  # POSITIVE | NEGATIVE | FLAT


def simple_return(entry: float | None, exit_px: float | None, rules: PositionRules) -> ReturnBreakdown:
    if entry is None or exit_px is None or entry == 0:
        return ReturnBreakdown(
            entry_price=entry,
            exit_price=exit_px,
            return_pct=None,
            method=rules.return_method,
            side=rules.side,
            formula=None,
            bucket=None,
        )
    if rules.side == "SHORT":
        pct = (entry - exit_px) / entry * 100.0
        formula = f"(({_fmt(entry)} - {_fmt(exit_px)}) / {_fmt(entry)}) × 100"
    else:
        pct = (exit_px - entry) / entry * 100.0
        formula = f"(({_fmt(exit_px)} - {_fmt(entry)}) / {_fmt(entry)}) × 100"
    if pct > 0:
        bucket = "POSITIVE"
    elif pct < 0:
        bucket = "NEGATIVE"
    else:
        bucket = "FLAT"
    return ReturnBreakdown(
        entry_price=entry,
        exit_price=exit_px,
        return_pct=pct,
        method="SIMPLE",
        side=rules.side,
        formula=formula,
        bucket=bucket,
    )


def _fmt(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4g}"
