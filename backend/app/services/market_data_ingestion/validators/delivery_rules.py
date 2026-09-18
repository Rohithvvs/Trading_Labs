"""Delivery field validation — never invent values."""
from __future__ import annotations

from typing import Any

from ..derived import compute_delivery_pct


def validate_delivery_fields(
    delivery_qty: Any,
    traded_qty: Any,
) -> dict[str, Any]:
    """Return normalized delivery_qty and delivery_pct (null-safe)."""
    dq: int | None
    tq: int | None
    try:
        dq = int(delivery_qty) if delivery_qty is not None and str(delivery_qty).strip() != "" else None
    except (TypeError, ValueError):
        dq = None
    try:
        tq = int(traded_qty) if traded_qty is not None and str(traded_qty).strip() != "" else None
    except (TypeError, ValueError):
        tq = None
    pct = compute_delivery_pct(dq, tq)
    return {
        "delivery_qty": dq,
        "traded_qty": tq,
        "delivery_pct": float(pct) if pct is not None else None,
        "valid": pct is not None,
    }
