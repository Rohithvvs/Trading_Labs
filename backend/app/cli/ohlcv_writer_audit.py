"""Read-only inventory of code paths that can write daily/index OHLCV.

    python -m app.cli.ohlcv_writer_audit

Does not connect to any database.
"""
from __future__ import annotations

import json

from app.services.market_data_ingestion.writer_inventory import DAILY_INDEX_WRITERS


def main(argv: list[str] | None = None) -> int:
    writers = [w for w in DAILY_INDEX_WRITERS if w["writes"]]
    print(json.dumps({"wrote": False, "db_connected": False, "writers": writers}, indent=2))
    print("WRITER AUDIT COMPLETE — NO DATA WAS WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
