"""Read-only data audit + index backfill + 52W scan verification."""
from __future__ import annotations

import asyncio
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

# Ensure backend/ is on sys.path when invoked as a file
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _dq_table(db, model, label: str) -> dict:
    from sqlalchemy import func, select

    today = date.today()
    rows = (
        await db.execute(
            select(
                model.trade_date,
                model.symbol,
                model.open,
                model.high,
                model.low,
                model.close,
                model.volume,
            )
        )
    ).all()
    n = len(rows)
    dates = {r[0] for r in rows}
    keys = [(r[0], r[1]) for r in rows]
    dup = n - len(set(keys))
    nulls = {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}
    invalid_ohlc = 0
    future = 0
    neg = 0
    zero = 0
    for td, _s, o, h, l, c, v in rows:
        vals = {"open": o, "high": h, "low": l, "close": c, "volume": v}
        for k, val in vals.items():
            if val is None:
                nulls[k] += 1
        try:
            fo, fh, fl, fc = float(o), float(h), float(l), float(c)
        except (TypeError, ValueError):
            invalid_ohlc += 1
            continue
        if any(not math.isfinite(x) for x in (fo, fh, fl, fc)):
            invalid_ohlc += 1
        if fh < fl or fh < fo or fh < fc or fl > fo or fl > fc:
            invalid_ohlc += 1
        if td > today:
            future += 1
        if any(x < 0 for x in (fo, fh, fl, fc)):
            neg += 1
        if any(x == 0 for x in (fo, fh, fl, fc)):
            zero += 1
    return {
        "table": label,
        "rows": n,
        "unique_dates": len(dates),
        "duplicates": dup,
        "nulls": nulls,
        "invalid_ohlc": invalid_ohlc,
        "future_dates": future,
        "negative_prices": neg,
        "zero_prices": zero,
        "min_date": min(dates).isoformat() if dates else None,
        "max_date": max(dates).isoformat() if dates else None,
    }


async def audit_and_scan() -> dict:
    from sqlalchemy import func, select

    from app.config import settings
    from app.db.session import AsyncSessionLocal
    from app.models.strategy_market_data import DailyOhlcv, IndexOhlcv
    from app.models.stock import StockMaster
    from app.services.market_data_ingestion.ensure import backfill_index_history
    from app.services.strategies.breakout52w.indicators import market_ok, market_sma50
    from app.services.strategies.breakout52w.scan_service import run_scan
    from app.services.universe_service import UniverseService

    report: dict = {"database_url_host": None}

    parsed = settings.database_url
    try:
        from urllib.parse import urlsplit

        report["database_url_host"] = urlsplit(parsed).hostname
    except Exception:
        report["database_url_host"] = "unknown"

    async with AsyncSessionLocal() as db:
        universe = await UniverseService.get_active_nifty500_symbols()
        report["universe"] = len(universe)

        daily_dq = await _dq_table(db, DailyOhlcv, "daily_ohlcv")
        index_dq_before = await _dq_table(db, IndexOhlcv, "index_ohlcv")
        report["daily_ohlcv"] = daily_dq
        report["index_ohlcv_before"] = index_dq_before

        # Per-symbol session counts (universe only)
        stmt = (
            select(DailyOhlcv.symbol, func.count(), func.min(DailyOhlcv.trade_date), func.max(DailyOhlcv.trade_date))
            .where(DailyOhlcv.symbol.in_(universe) if universe else True)
            .group_by(DailyOhlcv.symbol)
        )
        counts = (await db.execute(stmt)).all()
        by_sym = {s: int(n) for s, n, _a, _b in counts}
        ge252 = sum(1 for s in universe if by_sym.get(s, 0) >= 252)
        lt252 = sum(1 for s in universe if 0 < by_sym.get(s, 0) < 252)
        zero = sum(1 for s in universe if by_sym.get(s, 0) == 0)
        report["session_coverage"] = {
            "ge252": ge252,
            "lt252": lt252,
            "zero": zero,
            "symbols_with_ohlcv": len(by_sym),
        }

        # Anomalous date 2026-06-26
        anomaly = date(2026, 6, 26)
        have_anomaly = (
            await db.execute(select(func.count()).select_from(DailyOhlcv).where(DailyOhlcv.trade_date == anomaly))
        ).scalar() or 0
        report["anomaly_2026_06_26_rows"] = int(have_anomaly)

        date_counts = (
            await db.execute(
                select(DailyOhlcv.trade_date, func.count()).group_by(DailyOhlcv.trade_date)
            )
        ).all()
        sparse = [(d.isoformat(), int(c)) for d, c in date_counts if int(c) <= 20]
        report["sparse_dates"] = sparse

    print("=== AUDIT (before index backfill) ===")
    print(json.dumps({k: report[k] for k in report if k != "scan"}, indent=2, default=str))

    print("=== INDEX BACKFILL ===")
    try:
        bf = await backfill_index_history(years=3)
        report["index_backfill"] = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in bf.items()}
        print(json.dumps(report["index_backfill"], indent=2, default=str))
    except Exception as exc:
        report["index_backfill"] = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
        print("INDEX BACKFILL FAILED:", report["index_backfill"])

    async with AsyncSessionLocal() as db:
        report["index_ohlcv_after"] = await _dq_table(db, IndexOhlcv, "index_ohlcv")
        idx_rows = (
            await db.execute(
                select(IndexOhlcv.trade_date, IndexOhlcv.close)
                .where(IndexOhlcv.symbol == settings.strategy_index_store_symbol)
                .order_by(IndexOhlcv.trade_date.asc())
            )
        ).all()
        idx_closes = [float(c) for _d, c in idx_rows]
        idx_dates = [d for d, _c in idx_rows]
        market = None
        if idx_closes:
            t = len(idx_closes) - 1
            sma = market_sma50(idx_closes, t)
            mok = market_ok(idx_closes, t)
            market = {
                "nifty500_close": idx_closes[t],
                "nifty500_sma50": sma,
                "market_ok": mok,
                "evaluation_date": idx_dates[t].isoformat() if idx_dates else None,
                "index_rows": len(idx_closes),
            }
        report["market_filter"] = market
        print("=== MARKET FILTER ===")
        print(json.dumps(market, indent=2, default=str))

    print("=== RUNNING 52W SCAN ===")
    payload = await run_scan(mode="B")
    summary = payload.get("summary") or {}
    breakdown = payload.get("rejection_breakdown") or []
    report["scan"] = {
        "status": payload.get("status"),
        "error_code": payload.get("error_code"),
        "evaluation_date": payload.get("evaluation_date"),
        "market_ok": payload.get("market_ok"),
        "nifty_close": payload.get("nifty_close"),
        "nifty_sma50": payload.get("nifty_sma50"),
        "book_status": payload.get("book_status"),
        "summary": summary,
        "rejection_breakdown": breakdown,
        "buy_count": summary.get("buy"),
        "watch_count": summary.get("watch"),
        "reject_count": summary.get("reject"),
    }
    buys = [r for r in (payload.get("recommendations") or []) if r.get("signal") == "BUY"]
    report["buys"] = []
    for r in buys:
        tech = r.get("technicals") or {}
        report["buys"].append(
            {
                "symbol": r.get("symbol"),
                "close": r.get("close"),
                "prior_high": r.get("high_252_prior"),
                "close_ge_prior": tech.get("close_vs_prior_high"),
                "volume": r.get("volume"),
                "vol_sma20": r.get("vol_sma20"),
                "volume_gt_avg": tech.get("volume_vs_average"),
                "nifty_close": tech.get("nifty_close"),
                "nifty_sma50": tech.get("nifty_sma50"),
                "market_ok": tech.get("market_ok"),
                "slot_status": tech.get("slot_status"),
                "mom60": r.get("mom60"),
                "signal": r.get("signal"),
            }
        )
    print("=== SCAN SUMMARY ===")
    print(json.dumps(report["scan"], indent=2, default=str))
    print("=== BUYS ===")
    print(json.dumps(report["buys"], indent=2, default=str))
    return report


def main() -> int:
    report = asyncio.run(audit_and_scan())
    out = Path(__file__).resolve().parents[2] / "backend" / "scripts" / "w52_alignment_verify_result.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("Wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
