"""Force-release the scan_execution distributed lock (orphan cleanup)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> None:
    from sqlalchemy import text
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        tables = await db.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND (tablename ILIKE '%lock%' OR tablename ILIKE '%scan%')"
            )
        )
        print("tables:", [r[0] for r in tables.fetchall()])
        for table in ("distributed_locks", "app_locks", "locks", "scan_locks"):
            try:
                r = await db.execute(text(f"SELECT * FROM {table} LIMIT 20"))
                rows = r.mappings().all()
                print(table, "rows=", len(rows))
                for row in rows:
                    print(" ", dict(row))
            except Exception as exc:
                await db.rollback()
                print(table, "skip", type(exc).__name__)

        # Best-effort delete by common names
        for q in (
            "DELETE FROM distributed_locks WHERE lock_name = 'scan_execution'",
            "DELETE FROM distributed_locks WHERE name = 'scan_execution'",
            "DELETE FROM app_locks WHERE lock_name = 'scan_execution'",
            "DELETE FROM locks WHERE name = 'scan_execution'",
        ):
            try:
                res = await db.execute(text(q))
                await db.commit()
                print("OK", q, "rowcount=", res.rowcount)
            except Exception as exc:
                await db.rollback()
                print("fail", q, type(exc).__name__, exc)


if __name__ == "__main__":
    asyncio.run(main())
