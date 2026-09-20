"""Proposed rejection-audit row shape. Not a live SQLAlchemy table.

The physical table is defined in
``backend/app/db/proposed_migrations/market_data_rejections.sql``.
Do not import this into ``models/__init__.py`` and do not run Alembic until
explicitly approved. Rejected bars must never be written to daily_ohlcv.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


SECRET_KEYS = ("token", "password", "secret", "authorization", "database_url", "auth")


def strip_secrets(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if any(part in lowered for part in SECRET_KEYS):
            continue
        out[key] = value
    return out


@dataclass
class MarketDataRejectionRecord:
    context: str
    table_name: str
    symbol: str
    trade_date: date | str | None
    source: str | None
    material_reasons: list[str]
    rounding_reasons: list[str] = field(default_factory=list)
    provider: str | None = None
    request_id: str | None = None
    open: str | None = None
    high: str | None = None
    low: str | None = None
    close: str | None = None
    volume: str | None = None
    payload_json: dict[str, Any] = field(default_factory=dict)
    attempted_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "context": self.context,
            "table_name": self.table_name,
            "symbol": self.symbol,
            "trade_date": str(self.trade_date) if self.trade_date is not None else None,
            "source": self.source,
            "provider": self.provider,
            "request_id": self.request_id,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "payload_json": strip_secrets(self.payload_json),
            "material_reasons": list(self.material_reasons),
            "rounding_reasons": list(self.rounding_reasons),
        }
