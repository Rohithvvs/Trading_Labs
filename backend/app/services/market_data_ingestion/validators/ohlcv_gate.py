"""Reject material-invalid daily/index bars before upsert.

Rules (required OHLCV only; delivery/turnover/ADTV may be missing):
  high >= low
  low  <= min(open, close)
  high >= max(open, close)
  volume >= 0

Tolerance: NSE cash tick 0.05. A discrepancy of at most one tick is classified
as rounding and does **not** block persist. Larger breaks are material and are
rejected. Values are never clamped or rewritten.

Comparisons use Decimal. Optional fields are ignored.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ....models.market_data_rejection import MarketDataRejectionRecord, strip_secrets

logger = logging.getLogger("app.market_data.ohlcv_gate")

NSE_TICK = Decimal("0.05")
REQUIRED_FIELDS = ("trade_date", "symbol", "open", "high", "low", "close")


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def classify_ohlcv_bar(
    row: dict[str, Any],
    *,
    tick: Decimal = NSE_TICK,
) -> dict[str, Any]:
    """Classify a bar. decision is accept or reject. Never mutates OHLC."""
    material: list[str] = []
    rounding: list[str] = []
    tick = tick if tick >= 0 else Decimal("0")

    for field in REQUIRED_FIELDS:
        if row.get(field) in (None, ""):
            material.append(f"missing_{field}")
    trade_date = row.get("trade_date")
    if trade_date is not None and not isinstance(trade_date, (date, datetime, str)):
        material.append("invalid_trade_date")
    if not str(row.get("symbol") or "").strip():
        material.append("missing_symbol")

    open_px = _dec(row.get("open"))
    high = _dec(row.get("high"))
    low = _dec(row.get("low"))
    close = _dec(row.get("close"))
    if open_px is None:
        material.append("non_finite_open")
    if high is None:
        material.append("non_finite_high")
    if low is None:
        material.append("non_finite_low")
    if close is None:
        material.append("non_finite_close")

    volume = row.get("volume")
    if volume is None:
        vol = Decimal("0")
    else:
        vol = _dec(volume)
        if vol is None:
            material.append("non_finite_volume")
        elif vol < 0:
            material.append("negative_volume")

    if None not in (open_px, high, low, close):
        if high < low:
            material.append("high_lt_low")
        else:
            for px, name in ((open_px, "open"), (close, "close")):
                if px < low:
                    delta = low - px
                    code = f"{name}_below_low"
                    if delta <= tick:
                        rounding.append(f"rounding_{code}")
                    else:
                        material.append(code)
                if px > high:
                    delta = px - high
                    code = f"{name}_above_high"
                    if delta <= tick:
                        rounding.append(f"rounding_{code}")
                    else:
                        material.append(code)

    material = list(dict.fromkeys(material))
    rounding = list(dict.fromkeys(rounding))
    reject = bool(material)
    return {
        "decision": "reject" if reject else "accept",
        "severity": "material" if reject else ("rounding" if rounding else "ok"),
        "material_reasons": material,
        "rounding_reasons": rounding,
        "reasons": material,  # persist-blocking codes only
    }


def validate_ohlcv_bar(
    row: dict[str, Any],
    *,
    tick_epsilon: float | Decimal | None = None,
) -> list[str]:
    """Material rejection codes only. Empty list → bar may be persisted."""
    tick = NSE_TICK if tick_epsilon is None else _dec(tick_epsilon) or NSE_TICK
    return classify_ohlcv_bar(row, tick=tick)["reasons"]


def rejection_audit_record(
    row: dict[str, Any],
    classified: dict[str, Any],
    *,
    context: str = "ohlcv_upsert",
    table_name: str = "daily_ohlcv",
    provider: str | None = None,
) -> dict[str, Any]:
    """In-memory audit payload for a later market_data_rejections insert. No secrets."""
    payload = strip_secrets(
        {
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("volume"),
            "delivery_qty": row.get("delivery_qty"),
            "delivery_pct": row.get("delivery_pct"),
            "turnover": row.get("turnover"),
            "adtv_20": row.get("adtv_20"),
            "source": row.get("source"),
        }
    )
    record = MarketDataRejectionRecord(
        context=context,
        table_name=table_name,
        symbol=str(row.get("symbol") or ""),
        trade_date=row.get("trade_date"),
        source=row.get("source"),
        material_reasons=list(classified.get("material_reasons") or []),
        rounding_reasons=list(classified.get("rounding_reasons") or []),
        provider=provider,
        open=None if row.get("open") is None else str(row.get("open")),
        high=None if row.get("high") is None else str(row.get("high")),
        low=None if row.get("low") is None else str(row.get("low")),
        close=None if row.get("close") is None else str(row.get("close")),
        volume=None if row.get("volume") is None else str(row.get("volume")),
        payload_json=payload,
    )
    return record.as_dict()


def filter_valid_ohlcv_rows(
    rows: list[dict[str, Any]],
    *,
    tick_epsilon: float | Decimal | None = None,
    log_context: str = "ohlcv_upsert",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split into (accepted, rejected). Rejected OHLC values are not mutated."""
    tick = NSE_TICK if tick_epsilon is None else _dec(tick_epsilon) or NSE_TICK
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        classified = classify_ohlcv_bar(row, tick=tick)
        if classified["decision"] == "reject":
            record = {**row, "_reject_reasons": classified["reasons"], "_gate": classified}
            rejected.append(record)
        else:
            accepted.append(row)
    if rejected:
        sample = [
            rejection_audit_record(r, r["_gate"], context=log_context)
            for r in rejected[:10]
        ]
        logger.warning(
            "OHLCV_GATE_REJECTED | context=%s | rejected=%s | accepted=%s | sample=%s",
            log_context,
            len(rejected),
            len(accepted),
            sample,
        )
    return accepted, rejected
