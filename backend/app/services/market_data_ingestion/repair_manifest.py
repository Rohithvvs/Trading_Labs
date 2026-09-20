"""Build a future-only repair manifest from a preview JSON report. No DB I/O."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

MANIFEST_VERSION = 2
FINGERPRINT_VERSION = "v2_decimal_8"
PRICE_QUANTUM = Decimal("0.00000001")  # Numeric(18, 8)
MANIFEST_REASON = "replace_invalid_acs_derived_daily_bar"
PRICE_FIELDS = ("open", "high", "low", "close")


class ManifestError(ValueError):
    pass


class FingerprintError(ValueError):
    pass


def _decimal_from_text(value: Any) -> Decimal:
    """Decimal from textual form only. Never Decimal(float)."""
    if value is None or value == "":
        raise FingerprintError("missing numeric value")
    if isinstance(value, bool):
        raise FingerprintError("boolean is not a numeric value")
    if isinstance(value, Decimal):
        number = value
    else:
        number = Decimal(str(value))
    if not number.is_finite():
        raise FingerprintError("non-finite numeric value")
    return number


def canonical_price(value: Any) -> str:
    quantized = _decimal_from_text(value).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
    return format(quantized, "f")


def canonical_volume(value: Any) -> int:
    number = _decimal_from_text(value)
    integral = number.to_integral_value(rounding=ROUND_HALF_EVEN)
    if number != integral:
        raise FingerprintError("volume is not an integer")
    return int(integral)


def fingerprint_ohlcv(ohlcv: dict[str, Any] | None) -> str:
    """v2 canonical fingerprint. Raises FingerprintError on invalid input."""
    if not ohlcv:
        raise FingerprintError("missing ohlcv")
    prices = [canonical_price(ohlcv.get(field)) for field in PRICE_FIELDS]
    volume = canonical_volume(ohlcv.get("volume"))
    source = ohlcv.get("source")
    if source is None:
        raise FingerprintError("missing source")
    source_text = str(source)
    return "|".join([FINGERPRINT_VERSION, *prices, str(volume), source_text])


def canonical_old_values(original: dict[str, Any]) -> dict[str, Any]:
    return {
        "open": canonical_price(original.get("open")),
        "high": canonical_price(original.get("high")),
        "low": canonical_price(original.get("low")),
        "close": canonical_price(original.get("close")),
        "volume": canonical_volume(original.get("volume")),
        "source": original.get("source"),
        "loaded_at": original.get("loaded_at"),
    }


def _stable_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("table") or ""),
        str(row.get("symbol") or ""),
        str(row.get("trade_date") or ""),
    )


def build_repair_manifest(
    preview: dict[str, Any],
    *,
    source_checksum: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(preview, dict):
        raise ManifestError("preview report must be a JSON object")
    rows = preview.get("rows")
    if not isinstance(rows, list):
        raise ManifestError("preview report missing rows[]")

    items: list[dict[str, Any]] = []
    for row in rows:
        if row.get("verdict") != "REPAIRABLE":
            continue
        if row.get("verdict") == "NON_TRADING_DAY_PHANTOM":
            continue
        fyers = row.get("fyers_bar") or {}
        original = row.get("original") or {}
        if str(fyers.get("source") or "") != "FYERS":
            continue
        if not row.get("matching_date"):
            continue
        gate = row.get("ohlc_gate") or {}
        if gate.get("decision") == "reject":
            continue
        if not row.get("source_policy_allows_replacement", True):
            continue
        items.append(
            {
                "table": row.get("table"),
                "symbol": row.get("symbol"),
                "trade_date": row.get("trade_date"),
                "expected_current_source": original.get("source"),
                "expected_old_values": canonical_old_values(original),
                "expected_old_fingerprint": fingerprint_ohlcv(original),
                "fingerprint_version": FINGERPRINT_VERSION,
                "proposed_new_values": {
                    "open": fyers.get("open"),
                    "high": fyers.get("high"),
                    "low": fyers.get("low"),
                    "close": fyers.get("close"),
                    "volume": fyers.get("volume"),
                    "source": "FYERS",
                    "trade_date": fyers.get("trade_date"),
                    "symbol": fyers.get("symbol"),
                },
                "reason": MANIFEST_REASON,
                "validation": {
                    "ohlc_gate": gate,
                    "matching_date": row.get("matching_date"),
                    "source_policy_allows_replacement": row.get("source_policy_allows_replacement"),
                    "verdict": row.get("verdict"),
                },
                "repair_status": "PENDING_APPROVAL",
            }
        )
    items.sort(key=_stable_sort_key)
    if not items:
        raise ManifestError("preview report has no REPAIRABLE rows that meet manifest rules")
    created = created_at or datetime.now(timezone.utc)
    return {
        "manifest_version": MANIFEST_VERSION,
        "fingerprint_version": FINGERPRINT_VERSION,
        "created_at": created.replace(microsecond=0).isoformat(),
        "source_preview_checksum": source_checksum,
        "wrote": False,
        "db_connected": False,
        "item_count": len(items),
        "items": items,
        "note": (
            "PENDING_APPROVAL. Do not UPDATE daily_ohlcv until an explicit repair "
            "execution is approved. This file contains no credentials."
        ),
    }


def checksum_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_phantom_delete_review(
    preview: dict[str, Any],
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Review-only list of weekend/holiday phantom rows. Never deletes."""
    if not isinstance(preview, dict) or not isinstance(preview.get("rows"), list):
        raise ManifestError("preview report missing rows[]")
    items = []
    for row in preview["rows"]:
        if row.get("verdict") != "NON_TRADING_DAY_PHANTOM":
            continue
        original = row.get("original") or {}
        items.append(
            {
                "table": row.get("table"),
                "symbol": row.get("symbol"),
                "trade_date": row.get("trade_date"),
                "day_of_week": row.get("day_of_week"),
                "calendar_status": row.get("calendar_status"),
                "original": {
                    "open": original.get("open"),
                    "high": original.get("high"),
                    "low": original.get("low"),
                    "close": original.get("close"),
                    "volume": original.get("volume"),
                    "source": original.get("source"),
                    "loaded_at": original.get("loaded_at"),
                },
                "reason": row.get("reason")
                or "non-trading-day phantom; FYERS not called",
                "proposed_action": "EXCLUDE_FROM_PROVIDER_REPAIR_AND_MARK_FOR_DELETE_REVIEW",
                "delete_status": "REVIEW_ONLY_NO_DELETE",
            }
        )
    items.sort(key=_stable_sort_key)
    created = created_at or datetime.now(timezone.utc)
    return {
        "report_type": "phantom_rows_delete_review",
        "created_at": created.replace(microsecond=0).isoformat(),
        "wrote": False,
        "deleted": False,
        "item_count": len(items),
        "items": items,
        "note": (
            "Review only. Do not DELETE these rows until a separate explicit approval. "
            "They are excluded from the FYERS UPDATE repair manifest."
        ),
    }
