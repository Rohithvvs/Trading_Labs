"""HWM / TSL ratchet. Stop never decreases. No exit on the entry bar."""

from __future__ import annotations

import math

from .identity import ATR_MULT, NAN_ATR_STOP_FRAC


def initial_tsl(fill: float, atr: float | None) -> float:
    if atr is None or not math.isfinite(float(atr)):
        return float(fill) * NAN_ATR_STOP_FRAC
    return float(fill) - ATR_MULT * float(atr)


def reconstruct_tsl(*, last_known_tsl: float | None, hwm: float, atr: float | None) -> float:
    """If state was lost, rebuild from HWM without lowering the last known stop."""
    candidate = initial_tsl(hwm, atr)
    if last_known_tsl is None:
        return candidate
    return max(float(last_known_tsl), candidate)


def update_trail(
    *,
    hwm: float,
    tsl: float,
    close: float,
    atr: float | None,
    is_entry_bar: bool,
) -> tuple[float, float]:
    """Return (new_hwm, new_tsl). TSL never decreases. Entry bar does not ratchet/exit."""
    if is_entry_bar:
        return hwm, tsl
    if close > hwm and atr is not None and math.isfinite(float(atr)):
        hwm = float(close)
        tsl = max(float(tsl), float(close) - ATR_MULT * float(atr))
    return hwm, tsl


def should_exit(*, close: float, tsl: float, is_entry_bar: bool) -> bool:
    if is_entry_bar:
        return False
    return float(close) < float(tsl)
