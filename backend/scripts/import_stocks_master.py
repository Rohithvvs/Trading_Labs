import csv
import sys
import asyncio
from sqlalchemy.dialects.postgresql import insert
import os
from pathlib import Path

# Robust path setup so the script works whether run directly,
# via python -m, or from repo root / Render environment.
_here = Path(__file__).resolve()
# Try common layouts: repo_root/backend/scripts/...
candidates = [
    _here.parents[1],   # backend/
    _here.parents[2],   # repo root/
    Path.cwd(),
]
for cand in candidates:
    if (cand / "app" / "db" / "session.py").exists():
        sys.path.insert(0, str(cand))
        break
else:
    # Fallback
    sys.path.append(str(_here.parents[1]))

from datetime import datetime, timezone

from app.db.session import AsyncSessionLocal
from app.models.stock import StockMaster

async def import_csv(csv_path: str, universe: str):
    print(f"Importing {csv_path} into universe {universe}...")
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    is_nifty500 = universe.upper().replace(" ", "") in {"NIFTY500", "NIFTY_500"}
    records = []
    seen_store_symbols: set[str] = set()
    from app.services.universe_csv import parse_nifty500_row
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = parse_nifty500_row(row)
            if not parsed:
                continue
            raw_symbol = parsed["symbol"]
            series = parsed["series"]

            # Normalization: ABC -> ABC-EQ. Preserve BE/other series as stored today.
            if series == "EQ" and not raw_symbol.endswith("-EQ"):
                symbol = f"{raw_symbol}-EQ"
            elif not series and not raw_symbol.endswith("-EQ"):
                symbol = f"{raw_symbol}-EQ"
            else:
                symbol = raw_symbol

            if symbol in seen_store_symbols:
                continue
            seen_store_symbols.add(symbol)

            company_name = parsed["company_name"]
            sector = parsed["industry"]
            industry = parsed["industry"] or None
            isin = parsed["isin"]

            records.append({
                "symbol": symbol,
                "company_name": company_name,
                "sector": sector,
                "industry": industry,
                "series": series,
                "isin": isin,
                "universe": universe,
                "is_nifty500": is_nifty500,
                "is_active": True,
                "first_seen": now,
                "last_seen": now,
            })

    if not records:
        print("No valid records found.")
        return

    async with AsyncSessionLocal() as db:
        stmt = insert(StockMaster).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={
                "company_name": stmt.excluded.company_name,
                "sector": stmt.excluded.sector,
                "industry": stmt.excluded.industry,
                "series": stmt.excluded.series,
                "isin": stmt.excluded.isin,
                "universe": stmt.excluded.universe,
                "is_nifty500": stmt.excluded.is_nifty500,
                "is_active": True,
                "last_seen": now,
            }
        )
        await db.execute(stmt)
        await db.commit()
    print(f"Successfully upserted {len(records)} records for universe {universe}.")

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "ind_nifty500list.csv"
    universe = sys.argv[2] if len(sys.argv) > 2 else "NIFTY500"
    asyncio.run(import_csv(csv_path, universe))
