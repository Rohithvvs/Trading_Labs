"""Local-Postgres fingerprint repair for daily_ohlcv / index_ohlcv.

Uses LOCAL_POSTGRES_DATABASE_URL only. Never DATABASE_URL, Turso, or ACS.
Dry-run is read-only. Execute updates only matching manifest keys in one
transaction and rolls back on mismatch. No DELETE.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from ...db.urls import is_local_postgres_url, public_db_target
from .repair_manifest import (
    FINGERPRINT_VERSION,
    FingerprintError,
    fingerprint_ohlcv,
)
from .source_policy import classify_daily_index_source
from .validators.ohlcv_gate import validate_ohlcv_bar

ALLOWED_TABLES = frozenset({"daily_ohlcv", "index_ohlcv"})
FORBIDDEN_TABLES = frozenset({"historical_candles"})


class RepairError(RuntimeError):
    pass


class RepairStore(Protocol):
    def fetch_row(self, table: str, symbol: str, trade_date: str) -> dict[str, Any] | None:
        ...

    def update_row(self, table: str, symbol: str, trade_date: str, values: dict[str, Any]) -> int:
        ...

    def begin(self) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...

    def close(self) -> None:
        ...


def _sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )


def _row_vals(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume": row.get("volume"),
        "source": row.get("source"),
    }


def _validate_replacement(item: dict[str, Any]) -> list[str]:
    new = item.get("proposed_new_values") or {}
    reasons = []
    src = classify_daily_index_source(new.get("source"))
    if src["decision"] != "accept" or str(new.get("source") or "") != "FYERS":
        reasons.append("replacement_source_not_fyers")
    bar = {
        "trade_date": item.get("trade_date"),
        "symbol": item.get("symbol"),
        "open": new.get("open"),
        "high": new.get("high"),
        "low": new.get("low"),
        "close": new.get("close"),
        "volume": new.get("volume"),
        "source": "FYERS",
    }
    reasons.extend(validate_ohlcv_bar(bar))
    return reasons


SUPPORTED_FINGERPRINT_VERSIONS = frozenset({FINGERPRINT_VERSION, None, "v1", 1, "1"})


def expected_fingerprint_for_item(item: dict[str, Any], manifest: dict[str, Any]) -> str:
    """Compare using v2 canonicalization of explicit old fields.

    A stored v1 fingerprint string is never used. Unknown versions are rejected.
    """
    version = item.get("fingerprint_version") or manifest.get("fingerprint_version")
    if version not in SUPPORTED_FINGERPRINT_VERSIONS:
        raise RepairError("MANIFEST_FINGERPRINT_VERSION_UNSUPPORTED")
    old = item.get("expected_old_values") or {}
    try:
        return fingerprint_ohlcv(old)
    except FingerprintError as exc:
        raise RepairError(f"invalid expected_old_values: {exc}") from exc


def plan_limited_items(manifest: dict[str, Any], *, limit: int | None = None) -> list[dict[str, Any]]:
    items = list(manifest.get("items") or [])
    if limit is not None:
        items = items[: max(int(limit), 0)]
    return items


def apply_manifest_repairs(
    manifest: dict[str, Any],
    *,
    local_postgres_url: str | None,
    approved_run_id: str,
    confirm_local_backup: bool,
    execute: bool,
    limit: int | None = None,
    store: RepairStore | None = None,
) -> dict[str, Any]:
    if execute:
        if not confirm_local_backup:
            raise RepairError("Refusing: --confirm-local-backup is required")
        if not (approved_run_id or "").strip():
            raise RepairError("Refusing: --approved-repair-run-id is required")
    approved_run_id = (approved_run_id or "").strip() or "DRY-RUN"
    url = (local_postgres_url or "").strip()
    if not url:
        raise RepairError(
            "Refusing: LOCAL_POSTGRES_DATABASE_URL is not set. DATABASE_URL will not be used."
        )
    if not is_local_postgres_url(url):
        raise RepairError(
            f"Refusing non-local source {public_db_target(url)}. Repair is localhost only."
        )
    version = manifest.get("fingerprint_version")
    if version not in SUPPORTED_FINGERPRINT_VERSIONS:
        raise RepairError("MANIFEST_FINGERPRINT_VERSION_UNSUPPORTED")
    items = plan_limited_items(manifest, limit=limit)
    if not items:
        raise RepairError("Manifest has no items to repair")

    owned = store is not None
    if store is None:
        store = _SqlAlchemyLocalStore(url)
    results: list[dict[str, Any]] = []
    wrote = False
    try:
        if execute:
            store.begin()
        for item in items:
            table = str(item.get("table") or "")
            symbol = str(item.get("symbol") or "")
            trade_date = str(item.get("trade_date") or "")
            rec: dict[str, Any] = {
                "table": table,
                "symbol": symbol,
                "trade_date": trade_date,
                "run_id": approved_run_id,
                "updated": False,
            }
            if table in FORBIDDEN_TABLES or table not in ALLOWED_TABLES:
                rec["status"] = "REFUSED_TABLE"
                rec["reason"] = f"table {table} is not eligible"
                results.append(rec)
                if execute:
                    store.rollback()
                    raise RepairError(rec["reason"])
                continue
            gate_reasons = _validate_replacement(item)
            if gate_reasons:
                rec["status"] = "REPLACEMENT_REJECTED"
                rec["reason"] = gate_reasons
                results.append(rec)
                if execute:
                    store.rollback()
                    raise RepairError(f"replacement failed gate: {gate_reasons}")
                continue
            current = store.fetch_row(table, symbol, trade_date)
            if current is None:
                rec["status"] = "MISSING_ROW"
                rec["reason"] = "target row not found"
                results.append(rec)
                if execute:
                    store.rollback()
                    raise RepairError(rec["reason"])
                continue
            try:
                current_fp = fingerprint_ohlcv(_row_vals(current))
                expected_fp = expected_fingerprint_for_item(item, manifest)
            except (FingerprintError, RepairError) as exc:
                rec["status"] = "FINGERPRINT_INVALID"
                rec["reason"] = str(exc)
                results.append(rec)
                if execute:
                    store.rollback()
                    raise RepairError(str(exc)) from exc
                continue
            expected_source = item.get("expected_current_source")
            rec["before"] = {
                "open": current.get("open"),
                "high": current.get("high"),
                "low": current.get("low"),
                "close": current.get("close"),
                "volume": current.get("volume"),
                "source": current.get("source"),
                "fingerprint": current_fp,
                "fingerprint_version": FINGERPRINT_VERSION,
            }
            rec["after_proposed"] = item.get("proposed_new_values")
            rec["expected_fingerprint"] = expected_fp
            proposed = item.get("proposed_new_values") or {}
            try:
                proposed_fp = fingerprint_ohlcv(
                    {
                        "open": proposed.get("open"),
                        "high": proposed.get("high"),
                        "low": proposed.get("low"),
                        "close": proposed.get("close"),
                        "volume": proposed.get("volume"),
                        "source": proposed.get("source") or "FYERS",
                    }
                )
            except FingerprintError:
                proposed_fp = None
            if (
                str(current.get("source") or "") == "FYERS"
                and proposed_fp is not None
                and current_fp == proposed_fp
            ):
                rec["status"] = "ALREADY_REPAIRED"
                rec["reason"] = "current row already matches FYERS replacement; skipped"
                rec["updated"] = False
                results.append(rec)
                continue
            if str(current.get("source") or "") != str(expected_source or "") or current_fp != expected_fp:
                rec["status"] = "FINGERPRINT_MISMATCH"
                rec["reason"] = "old row changed since manifest; no update"
                results.append(rec)
                if execute:
                    store.rollback()
                    raise RepairError("fingerprint mismatch; transaction rolled back")
                continue
            if execute:
                new = item["proposed_new_values"]
                n = store.update_row(
                    table,
                    symbol,
                    trade_date,
                    {
                        "open": new["open"],
                        "high": new["high"],
                        "low": new["low"],
                        "close": new["close"],
                        "volume": new["volume"],
                        "source": "FYERS",
                        "loaded_at": datetime.now(timezone.utc),
                    },
                )
                if n != 1:
                    store.rollback()
                    raise RepairError(f"expected 1 row updated, got {n}")
                rec["updated"] = True
                rec["status"] = "UPDATED"
                wrote = True
            else:
                rec["status"] = "MATCHED_FOR_REPAIR"
                rec["updated"] = False
            results.append(rec)
        if execute:
            store.commit()
    except Exception:
        if execute:
            try:
                store.rollback()
            except Exception:
                pass
        raise
    finally:
        if not owned:
            store.close()

    matched = sum(1 for r in results if r["status"] in {"MATCHED_FOR_REPAIR", "DRY_RUN_MATCH", "UPDATED"})
    return {
        "wrote": wrote,
        "db_connected": True,
        "turso_connected": False,
        "dry_run": not execute,
        "target": public_db_target(url),
        "run_id": approved_run_id,
        "item_count": len(results),
        "matched": matched,
        "updated": sum(1 for r in results if r.get("updated")),
        "results": results,
        "final_line": (
            "REPAIR APPLIED — LOCAL POSTGRES ONLY"
            if execute
            else "REPAIR DRY-RUN — NO DATA WAS WRITTEN"
        ),
    }


class MemoryRepairStore:
    """In-memory store for unit tests. No Postgres."""

    def __init__(self, rows: dict[tuple[str, str, str], dict[str, Any]] | None = None) -> None:
        self.rows = rows or {}
        self.in_tx = False
        self.committed = False
        self.rolled_back = False

    def fetch_row(self, table: str, symbol: str, trade_date: str) -> dict[str, Any] | None:
        return self.rows.get((table, symbol, trade_date))

    def update_row(self, table: str, symbol: str, trade_date: str, values: dict[str, Any]) -> int:
        key = (table, symbol, trade_date)
        if key not in self.rows:
            return 0
        self.rows[key] = {**self.rows[key], **values}
        return 1

    def begin(self) -> None:
        self.in_tx = True

    def commit(self) -> None:
        self.committed = True
        self.in_tx = False

    def rollback(self) -> None:
        self.rolled_back = True
        self.in_tx = False

    def close(self) -> None:
        return None


class _SqlAlchemyLocalStore:
    def __init__(self, url: str) -> None:
        from sqlalchemy import create_engine

        self._engine = create_engine(
            _sync_url(url),
            isolation_level="READ COMMITTED",
            connect_args={"connect_timeout": 10},
        )
        self._conn = None

    def begin(self) -> None:
        from sqlalchemy import text

        self._conn = self._engine.connect()
        self._conn.execute(text("BEGIN"))

    def fetch_row(self, table: str, symbol: str, trade_date: str) -> dict[str, Any] | None:
        from sqlalchemy import text

        if table not in ALLOWED_TABLES:
            raise RepairError("refusing non-allowlisted table")
        sql = (
            f"SELECT trade_date, symbol, open, high, low, close, volume, source, loaded_at "
            f"FROM {table} WHERE symbol = :symbol AND trade_date = :trade_date"
        )
        if self._conn is None:
            with self._engine.connect() as conn:
                row = conn.execute(text(sql), {"symbol": symbol, "trade_date": trade_date}).mappings().first()
                return dict(row) if row else None
        row = self._conn.execute(text(sql), {"symbol": symbol, "trade_date": trade_date}).mappings().first()
        return dict(row) if row else None

    def update_row(self, table: str, symbol: str, trade_date: str, values: dict[str, Any]) -> int:
        from sqlalchemy import text

        if table not in ALLOWED_TABLES:
            raise RepairError("refusing non-allowlisted table")
        if self._conn is None:
            raise RepairError("update requires an open transaction")
        sql = (
            f"UPDATE {table} SET open=:open, high=:high, low=:low, close=:close, "
            f"volume=:volume, source=:source, loaded_at=:loaded_at "
            f"WHERE symbol=:symbol AND trade_date=:trade_date"
        )
        result = self._conn.execute(
            text(sql),
            {
                "open": values["open"],
                "high": values["high"],
                "low": values["low"],
                "close": values["close"],
                "volume": values["volume"],
                "source": values["source"],
                "loaded_at": values["loaded_at"],
                "symbol": symbol,
                "trade_date": trade_date,
            },
        )
        return int(result.rowcount or 0)

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()
            self._conn.close()
            self._conn = None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._engine.dispose()
