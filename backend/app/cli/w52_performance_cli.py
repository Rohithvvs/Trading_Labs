"""Collect and inspect stored 52W Strategy Tester metrics.

Usage:
    python -m app.cli.w52_performance_cli collect [--force] [--limit N] [--symbols RELIANCE-EQ,TCS-EQ]
    python -m app.cli.w52_performance_cli show RELIANCE-EQ [--window ALL]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_windows(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [part.strip().upper() for part in raw.split(",") if part.strip()]


async def _cmd_collect(args: argparse.Namespace) -> int:
    from app.services.strategies.breakout52w.performance_store import collect_universe_performance

    symbols = None
    if args.symbols:
        symbols = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
    result = await collect_universe_performance(
        symbols=symbols,
        asof=_parse_date(args.asof),
        windows=_parse_windows(args.windows),
        force=bool(args.force),
        concurrency=int(args.concurrency),
        limit=args.limit,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if int(result.get("failed") or 0) == 0 else 1


async def _cmd_show(args: argparse.Namespace) -> int:
    from app.services.strategies.breakout52w.performance_store import (
        get_symbol_performance,
        list_symbol_performance,
        row_to_dict,
        strategy_tester_payload,
    )

    if args.window:
        row = await get_symbol_performance(args.symbol, args.window.upper())
        rows = [row] if row is not None else []
    else:
        rows = await list_symbol_performance(args.symbol)
    if not rows:
        print(json.dumps({"symbol": args.symbol.upper(), "windows": []}, indent=2))
        return 1
    payload = []
    for row in rows:
        item = row_to_dict(row)
        item["strategy_tester"] = strategy_tester_payload(item)
        if not args.with_trades:
            item.pop("trades", None)
            item.pop("ledger", None)
            item.pop("coverage", None)
        payload.append(item)
    print(json.dumps({"symbol": args.symbol.upper(), "windows": payload}, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="52W per-symbol Strategy Tester store")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="Replay stored daily bars and persist tester metrics")
    collect.add_argument("--symbols", help="Comma-separated symbols; default is active NIFTY 500")
    collect.add_argument("--windows", help="Comma-separated windows (default 1Y,3Y,5Y,8Y,18Y,ALL)")
    collect.add_argument("--asof", help="Evaluation date YYYY-MM-DD (default last index session)")
    collect.add_argument("--force", action="store_true", help="Recompute even when data_hash matches")
    collect.add_argument("--concurrency", type=int, default=4)
    collect.add_argument("--limit", type=int, default=None)
    collect.set_defaults(func=_cmd_collect)

    show = sub.add_parser("show", help="Print stored tester metrics for one symbol")
    show.add_argument("symbol")
    show.add_argument("--window", default=None)
    show.add_argument("--with-trades", action="store_true")
    show.set_defaults(func=_cmd_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
