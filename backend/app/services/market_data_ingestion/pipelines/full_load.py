"""Full historical load (≥3 years) for strategy-grade market data."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from ....config.settings import settings
from ..calendar_utils import expected_last_completed_session
from ..derived import attach_adtv_20_series, compute_delivery_pct, compute_turnover
from .. import load_tracking
from ..locks import acquire_market_data_load_lock
from ..providers.fyers_eod import FyersEodProvider
from ..providers.nse_delivery import NseDeliveryProvider
from .. import repository

logger = logging.getLogger("app.market_data_ingestion.full_load")

# NSE delivery archives are session-by-session. An 18-year window is ~4,500
# HTTP fetches and is not required for price backtests.
_DELIVERY_AUTO_SKIP_YEARS = 5


def missing_ohlcv_ranges(
    start: date,
    end: date,
    min_d: date | None,
    max_d: date | None,
) -> list[tuple[date, date]]:
    """Inclusive date windows still missing from an existing equity series."""
    if start > end:
        return []
    if min_d is None or max_d is None:
        return [(start, end)]
    out: list[tuple[date, date]] = []
    if start < min_d:
        gap_end = min_d - timedelta(days=1)
        if start <= gap_end:
            out.append((start, gap_end))
    if max_d < end:
        gap_start = max_d + timedelta(days=1)
        if gap_start <= end:
            out.append((gap_start, end))
    return out


async def run_full_load(
    *,
    years: int = 3,
    symbols: list[str] | None = None,
    trigger_source: str = "CLI",
    skip_delivery: bool | None = None,
) -> dict[str, Any]:
    lease = await acquire_market_data_load_lock()
    if not lease.acquired:
        await load_tracking.record_skipped_locked("FULL", trigger_source)
        return {"status": "SKIPPED_LOCKED", "exit_code": 3}

    run_id = None
    nse: NseDeliveryProvider | None = None
    try:
        end = expected_last_completed_session()
        start = end - timedelta(days=int(years * 365) + 30)

        from ...universe_service import UniverseService

        universe = symbols or await UniverseService.get_active_nifty500_symbols()
        if not universe:
            run_id = await load_tracking.start_load(
                "FULL",
                trigger_source,
                range_from=start,
                range_to=end,
                provider="FYERS+NSE",
            )
            await load_tracking.finish_load(run_id, "FAILED", error_summary="empty universe")
            return {"status": "FAILED", "exit_code": 1, "error": "empty universe"}

        await UniverseService.touch_lifecycle(universe, is_nifty500=True)

        run_id = await load_tracking.start_load(
            "FULL",
            trigger_source,
            range_from=start,
            range_to=end,
            data_date=end,
            provider="FYERS+NSE",
        )
        logger.info(
            "MARKET_DATA_LOAD_START | type=FULL | years=%s | symbols=%s | from=%s | to=%s",
            years,
            len(universe),
            start.isoformat(),
            end.isoformat(),
        )

        fyers = FyersEodProvider()
        load_delivery = True
        if skip_delivery is None:
            load_delivery = years <= _DELIVERY_AUTO_SKIP_YEARS
        else:
            load_delivery = not skip_delivery
        nse = NseDeliveryProvider() if load_delivery else None
        concurrency = max(1, min(settings.strategy_market_data_load_concurrency, 8))
        sem = asyncio.Semaphore(concurrency)

        # Index first
        try:
            idx_rows = await fyers.fetch_index_range(start, end)
            await repository.upsert_index_bars(idx_rows)
        except Exception as exc:
            logger.warning("FULL_INDEX_FAIL | err=%s", type(exc).__name__)

        delivery_maps: dict[date, Any] = {}
        delivery_sessions_ok = 0
        if load_delivery and nse is not None:
            # Delivery over full OHLCV window (trading days only; soft-fail per session)
            logger.info(
                "MARKET_DATA_DELIVERY_START | from=%s | to=%s",
                start.isoformat(),
                end.isoformat(),
            )
            delivery_maps = await nse.fetch_range_delivery(
                start,
                end,
                trading_days_only=True,
                concurrency=min(6, concurrency),
            )
            delivery_sessions_ok = sum(1 for m in delivery_maps.values() if m)
        else:
            logger.info(
                "MARKET_DATA_DELIVERY_SKIPPED | years=%s | skip_delivery=%s",
                years,
                skip_delivery,
            )

        total_fetched = 0
        total_upserted = 0
        total_failed = 0
        total_skipped = 0
        failed: list[str] = []

        async def load_symbol(sym: str) -> None:
            nonlocal total_fetched, total_upserted, total_failed, total_skipped
            async with sem:
                try:
                    min_d, max_d, _row_count = await repository.equity_date_span(sym)
                    windows = missing_ohlcv_ranges(start, end, min_d, max_d)
                    if not windows:
                        total_skipped += 1
                        return

                    for range_from, range_to in windows:
                        rows = await fyers.fetch_daily_range(sym, range_from, range_to)
                        for bar in rows:
                            dmap = delivery_maps.get(bar["trade_date"]) or {}
                            drec = nse.lookup(dmap, symbol=sym) if nse is not None and dmap else None
                            d_qty = drec.get("delivery_qty") if drec else None
                            traded = drec.get("traded_qty") if drec else None
                            d_pct = drec.get("delivery_pct") if drec else None
                            if d_pct is None and d_qty is not None:
                                pct = compute_delivery_pct(d_qty, traded)
                                d_pct = float(pct) if pct is not None else None
                            turn = compute_turnover(bar["close"], bar["volume"])
                            bar["delivery_qty"] = d_qty
                            bar["delivery_pct"] = d_pct
                            bar["turnover"] = float(turn) if turn is not None else None
                        if rows:
                            if range_from > start:
                                prior = await repository.fetch_recent_equity_before(
                                    sym, range_from, limit=19
                                )
                                combined = prior + rows
                                attach_adtv_20_series(combined)
                            else:
                                attach_adtv_20_series(rows)
                        total_fetched += len(rows)
                        chunk = 500
                        for i in range(0, len(rows), chunk):
                            n, _ = await repository.upsert_daily_bars(rows[i : i + chunk])
                            total_upserted += n
                except Exception as exc:
                    total_failed += 1
                    failed.append(sym)
                    logger.warning("FULL_SYMBOL_FAIL | symbol=%s | err=%s", sym, type(exc).__name__)

        await asyncio.gather(*[load_symbol(s) for s in universe])

        # Delivery pass for rows that already existed (skipped symbols / prior OHLCV)
        delivery_rows_updated = 0
        if load_delivery and nse is not None:
            for sess, dmap in delivery_maps.items():
                if not dmap:
                    continue
                try:
                    delivery_rows_updated += await repository.update_delivery_for_session(
                        sess, dmap, symbols=universe
                    )
                except Exception as exc:
                    logger.warning(
                        "FULL_DELIVERY_APPLY_FAIL | session=%s | err=%s",
                        sess.isoformat(),
                        type(exc).__name__,
                    )

        if total_upserted == 0 and total_failed == len(universe):
            status, exit_code = "FAILED", 1
        elif total_failed > 0:
            status, exit_code = "PARTIAL", 4
        else:
            status, exit_code = "SUCCESS", 0

        await load_tracking.finish_load(
            run_id,
            status,
            rows_fetched=total_fetched,
            rows_inserted=total_upserted,
            rows_failed=total_failed,
            rows_skipped=total_skipped,
            error_summary=None if status == "SUCCESS" else f"failed_symbols={total_failed}",
            details_json={
                "failed_sample": failed[:40],
                "years": years,
                "delivery_sessions_ok": delivery_sessions_ok,
                "delivery_rows_updated": delivery_rows_updated,
            },
        )
        logger.info(
            "MARKET_DATA_LOAD_END | type=FULL | status=%s | fetched=%s | upserted=%s | "
            "failed=%s | skipped=%s | delivery_sessions=%s | delivery_updates=%s",
            status,
            total_fetched,
            total_upserted,
            total_failed,
            total_skipped,
            delivery_sessions_ok,
            delivery_rows_updated,
        )
        return {
            "status": status,
            "exit_code": exit_code,
            "rows_fetched": total_fetched,
            "rows_upserted": total_upserted,
            "rows_failed": total_failed,
            "rows_skipped": total_skipped,
            "range_from": start.isoformat(),
            "range_to": end.isoformat(),
            "delivery_sessions_ok": delivery_sessions_ok,
            "delivery_rows_updated": delivery_rows_updated,
            "run_id": str(run_id),
        }
    except Exception as exc:
        logger.exception("MARKET_DATA_LOAD_FAILED | type=FULL | error=%s", exc)
        if run_id:
            await load_tracking.finish_load(run_id, "FAILED", error_summary=str(exc)[:500])
        return {"status": "FAILED", "exit_code": 1, "error": str(exc)}
    finally:
        if nse is not None:
            try:
                await nse.aclose()
            except Exception:
                pass
        await lease.release()
