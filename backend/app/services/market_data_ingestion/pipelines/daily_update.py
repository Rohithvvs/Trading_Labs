"""Daily incremental EOD update for strategy-grade market data.

Delegates to ``ensure_latest_market_data`` so CLI and scanner share one code path.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ..ensure import ensure_latest_market_data

logger = logging.getLogger("app.market_data_ingestion.daily_update")


async def run_daily_update(
    *,
    target_date: date | None = None,
    trigger_source: str = "CLI",
    force: bool = False,
) -> dict[str, Any]:
    """Ensure latest completed session (gap-fill + delivery + index + adtv)."""
    result = await ensure_latest_market_data(
        target_date=target_date,
        trigger_source=trigger_source,
        force=force,
        write_load_log=True,
    )
    # Map ALREADY_FRESH → SUCCESS for CLI compatibility
    if result.get("status") == "ALREADY_FRESH":
        return {
            **result,
            "status": "SUCCESS",
            "exit_code": 0,
            "rows_fetched": result.get("rows_fetched", 0),
            "rows_upserted": result.get("rows_upserted", 0),
            "rows_failed": result.get("rows_failed", 0),
        }
    return result
