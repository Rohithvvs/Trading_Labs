"""Quick RE-001 diagnostics: settings, table, row counts, registration."""
from __future__ import annotations

import sys

from app.config.settings import settings
from app.db.session import SessionLocal
from app.services.re001.registry import get_re001_registration, is_re001_active
from sqlalchemy import inspect, text


def main() -> int:
    print("=== RE-001 Settings ===")
    print(f"  re001_enabled          = {settings.re001_enabled}")
    print(f"  re001_stage            = {settings.re001_stage!r}")
    print(f"  is_re001_active()      = {settings.is_re001_active()}")
    print(f"  re001_persist_decisions= {settings.re001_persist_decisions}")
    print(f"  re001_ui_enabled       = {settings.re001_ui_enabled}")
    reg = get_re001_registration()
    print(f"  registry               = {reg.model_dump()}")
    print(f"  registry is_re001_active = {is_re001_active()}")

    if str(settings.re001_stage or "").strip().upper() == "ON":
        print("\nERROR: RE001_STAGE=ON is INVALID. Use LAB_SHADOW or PAPER_LINKED.")
        return 2
    if not settings.is_re001_active():
        print("\nWARNING: RE-001 is NOT active. Engine will not write lab rows.")
        return 1

    print("\n=== Database ===")
    db = SessionLocal()
    try:
        tables = inspect(db.bind).get_table_names()
        has = "recommendation_engine_decisions" in tables
        print(f"  recommendation_engine_decisions exists = {has}")
        if not has:
            print("  ERROR: Run alembic upgrade head")
            return 3
        n = db.execute(text("SELECT count(1) FROM recommendation_engine_decisions")).scalar()
        print(f"  total decision rows = {n}")
        rows = db.execute(
            text(
                "SELECT scan_run_id, count(1) AS c, max(created_at) AS latest "
                "FROM recommendation_engine_decisions "
                "WHERE scan_run_id IS NOT NULL "
                "GROUP BY scan_run_id "
                "ORDER BY max(created_at) DESC NULLS LAST "
                "LIMIT 10"
            )
        ).fetchall()
        if not rows:
            print("  recent scans: (none) — run a NEW screener after backend restart")
        else:
            print("  recent scans:")
            for scan_run_id, c, latest in rows:
                print(f"    - {scan_run_id}  decisions={c}  latest={latest}")
    finally:
        db.close()

    print("\nOK: Settings look active. If dropdown empty, restart backend and run a new scan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
