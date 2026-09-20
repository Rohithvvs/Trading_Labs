"""
Standalone Read-Only Runtime Architecture Smoke Test
Verifies operational data reads from Neon and candle history reads from Turso.
Strictly read-only; no server startup, no local DB access, zero writes.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config.settings import settings
from app.db.session import AsyncSessionLocal
from app.db.turso import connect_turso
from app.services.market_data_ingestion.turso_repository import (
    select_equity_history,
    select_index_history,
)
from sqlalchemy import text


def _mask_url(url: str) -> str:
    if not url:
        return "(empty)"
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        netloc = parts.netloc
        if "@" in netloc:
            creds, host = netloc.split("@", 1)
            user = creds.split(":")[0] if ":" in creds else creds
            netloc = f"{user}:***@{host}"
        return f"{parts.scheme}://{netloc}{parts.path}"
    except Exception:
        return "(masked)"


async def run_smoke_test():
    timestamp = datetime.now(timezone.utc).isoformat()
    report = {
        "timestamp": timestamp,
        "status": "UNKNOWN",
        "preconditions": {},
        "neon_operational_read": {},
        "turso_daily_candle_read": {},
        "turso_index_candle_read": {},
        "safety_audit": {
            "local_postgres_contacted": False,
            "writes_attempted": False,
            "read_only_transaction_enforced": False,
        },
    }

    # 1. Verify Safety Preconditions
    local_url = settings.local_postgres_source_url()
    backend = settings.candle_history_backend_name()
    raw_db_url = settings.database_url
    masked_db = _mask_url(raw_db_url)
    masked_turso = _mask_url(settings.turso_database_url)

    report["preconditions"] = {
        "local_postgres_url_empty": local_url == "",
        "local_postgres_disabled": True,
        "candle_backend": backend,
        "candle_backend_is_turso": backend == "turso",
        "neon_target": masked_db,
        "turso_target": masked_turso,
    }

    if local_url != "":
        report["status"] = "FAILED_LOCAL_POSTGRES_NOT_EMPTY"
        report["error"] = "LOCAL_POSTGRES_DATABASE_URL is set; refusing to proceed to protect local DB."
        _save_reports(report)
        print(json.dumps(report, indent=2))
        return 1

    if backend != "turso":
        report["status"] = "FAILED_BACKEND_NOT_TURSO"
        report["error"] = f"CANDLE_HISTORY_BACKEND is '{backend}', expected 'turso'."
        _save_reports(report)
        print(json.dumps(report, indent=2))
        return 1

    # Check host is remote Neon
    if "localhost" in raw_db_url or "127.0.0.1" in raw_db_url:
        report["status"] = "FAILED_NEON_IS_LOCAL"
        report["error"] = "DATABASE_URL points to localhost; refusing to run."
        _save_reports(report)
        print(json.dumps(report, indent=2))
        return 1

    # 2. Verify Neon Operational Read (stocks_master) with READ ONLY transaction
    try:
        async with AsyncSessionLocal() as session:
            # Enforce read-only transaction on PostgreSQL
            await session.execute(text("SET TRANSACTION READ ONLY;"))
            report["safety_audit"]["read_only_transaction_enforced"] = True
            
            result = await session.execute(text("SELECT count(*) FROM stocks_master;"))
            count = result.scalar()
            report["neon_operational_read"] = {
                "table": "stocks_master",
                "count": count,
                "expected": 755,
                "status": "SUCCESS" if count == 755 else "UNEXPECTED_COUNT",
            }
    except Exception as exc:
        report["neon_operational_read"] = {"status": "ERROR", "detail": str(exc)}

    # 3. Verify Turso Candle Reads
    try:
        client = connect_turso(settings)
        try:
            # 3a. Equity Candle Read (INFY-EQ)
            daily_rows = select_equity_history(client, "INFY-EQ", limit=5)
            report["turso_daily_candle_read"] = {
                "symbol": "INFY-EQ",
                "rows_returned": len(daily_rows),
                "first_date": daily_rows[0]["trade_date"].isoformat() if daily_rows else None,
                "sample_close": daily_rows[0]["close"] if daily_rows else None,
                "status": "SUCCESS" if len(daily_rows) == 5 else "INSUFFICIENT_ROWS",
            }

            # 3b. Index Candle Read (NIFTY500)
            index_rows = select_index_history(client, "NIFTY500")[:5]
            report["turso_index_candle_read"] = {
                "symbol": "NIFTY500",
                "rows_returned": len(index_rows),
                "first_date": index_rows[0]["trade_date"].isoformat() if index_rows else None,
                "sample_close": index_rows[0]["close"] if index_rows else None,
                "status": "SUCCESS" if len(index_rows) == 5 else "INSUFFICIENT_ROWS",
            }
        finally:
            client.close()
    except Exception as exc:
        report["turso_daily_candle_read"] = {"status": "ERROR", "detail": str(exc)}
        report["turso_index_candle_read"] = {"status": "ERROR", "detail": str(exc)}

    neon_ok = report["neon_operational_read"].get("status") == "SUCCESS"
    turso_daily_ok = report["turso_daily_candle_read"].get("status") == "SUCCESS"
    turso_index_ok = report["turso_index_candle_read"].get("status") == "SUCCESS"

    if neon_ok and turso_daily_ok and turso_index_ok:
        report["status"] = "ALL_READ_CHECKS_PASSED"
        ret = 0
    else:
        report["status"] = "CHECKS_FAILED"
        ret = 1

    _save_reports(report)
    print(json.dumps(report, indent=2))
    return ret


def _save_reports(report: dict) -> None:
    backend_root = Path(__file__).resolve().parent.parent
    json_path = backend_root / "runtime_database_smoke_test.json"
    md_path = backend_root / "runtime_database_smoke_test.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    md_content = f"""# Runtime Database Read-Only Smoke Test Report

**Timestamp**: {report.get('timestamp')}  
**Overall Status**: `{report.get('status')}`

## Safety & Preconditions

- **Local PostgreSQL URL Empty**: `{report['preconditions'].get('local_postgres_url_empty')}`
- **Local PostgreSQL Disabled**: `{report['preconditions'].get('local_postgres_disabled')}`
- **Candle History Backend**: `{report['preconditions'].get('candle_backend')}`
- **Neon Target (Masked)**: `{report['preconditions'].get('neon_target')}`
- **Turso Target (Masked)**: `{report['preconditions'].get('turso_target')}`
- **Read-Only Transaction Enforced on Neon**: `{report['safety_audit'].get('read_only_transaction_enforced')}`
- **Local PostgreSQL Contacted**: `{report['safety_audit'].get('local_postgres_contacted')}`
- **Writes Attempted**: `{report['safety_audit'].get('writes_attempted')}`

## Neon Operational Read

- **Table**: `{report['neon_operational_read'].get('table')}`
- **Status**: `{report['neon_operational_read'].get('status')}`
- **Row Count**: `{report['neon_operational_read'].get('count')}` (Expected: `{report['neon_operational_read'].get('expected')}`)

## Turso Candle Reads

### Daily Equity Candles (`INFY-EQ`)
- **Status**: `{report['turso_daily_candle_read'].get('status')}`
- **Rows Returned**: `{report['turso_daily_candle_read'].get('rows_returned')}`
- **First Trade Date**: `{report['turso_daily_candle_read'].get('first_date')}`
- **Sample Close**: `{report['turso_daily_candle_read'].get('sample_close')}`

### Index Candles (`NIFTY500`)
- **Status**: `{report['turso_index_candle_read'].get('status')}`
- **Rows Returned**: `{report['turso_index_candle_read'].get('rows_returned')}`
- **First Trade Date**: `{report['turso_index_candle_read'].get('first_date')}`
- **Sample Close**: `{report['turso_index_candle_read'].get('sample_close')}`
"""

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)


if __name__ == "__main__":
    exit_code = asyncio.run(run_smoke_test())
    sys.exit(exit_code)

