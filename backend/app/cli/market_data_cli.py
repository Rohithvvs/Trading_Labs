"""Strategy market-data operator CLI.

Usage:
    python -m app.cli.market_data_cli full-load [--years 3]
    python -m app.cli.market_data_cli daily-update [--date YYYY-MM-DD] [--force]
    python -m app.cli.market_data_cli status
    python -m app.cli.market_data_cli verify [--date YYYY-MM-DD] [--json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


async def _cmd_full_load(args: argparse.Namespace) -> int:
    from app.services.market_data_ingestion.pipelines.full_load import run_full_load

    symbols = None
    if args.symbols:
        symbols = [x.strip().upper() for x in args.symbols.split(",") if x.strip()]
    result = await run_full_load(
        years=args.years,
        symbols=symbols,
        trigger_source="CLI",
        skip_delivery=bool(args.skip_delivery),
    )
    print(json.dumps(result, indent=2, default=str))
    return int(result.get("exit_code", 1))


async def _cmd_daily_update(args: argparse.Namespace) -> int:
    from app.services.market_data_ingestion.pipelines.daily_update import run_daily_update

    result = await run_daily_update(
        target_date=_parse_date(args.date),
        trigger_source="CLI",
        force=bool(args.force),
    )
    print(json.dumps(result, indent=2, default=str))
    return int(result.get("exit_code", 1))


async def _cmd_status(_args: argparse.Namespace) -> int:
    from app.services.market_data_ingestion.freshness import status_snapshot

    try:
        snap = await status_snapshot()
        print(json.dumps(snap, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


async def _cmd_verify(args: argparse.Namespace) -> int:
    from app.services.market_data_ingestion.freshness import evaluate_freshness

    try:
        result = await evaluate_freshness(expected=_parse_date(args.date))
        payload = result.to_dict()
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(
                f"gate_enabled={payload['gate_enabled']} code={payload['code']} "
                f"ok={payload['ok']} expected={payload['expected_trade_date']} "
                f"coverage={payload['equity_coverage_ratio']:.3f} "
                f"index_present={payload['index_present']} reason={payload.get('reason')}"
            )
            if payload.get("remediation"):
                print(f"remediation: {payload['remediation']}")
        if payload["ok"] and payload["code"] == "OK":
            return 0
        if payload["code"] == "MARKET_DATA_STALE":
            # When gate disabled, still surface stale as exit 2 for verify semantics
            return 2 if not payload["ok"] or payload.get("reason") else 0
        return 2 if not payload["ok"] else 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="market_data_cli", description="Strategy market-data ops")
    sub = p.add_subparsers(dest="command", required=True)

    fl = sub.add_parser("full-load", help="Full historical load")
    fl.add_argument("--years", type=int, default=3, help="Calendar years of daily history to load")
    fl.add_argument("--symbols", type=str, default="", help="Comma-separated subset for debug")
    fl.add_argument(
        "--skip-delivery",
        action="store_true",
        help="Skip NSE delivery archives (recommended for multi-year price backfills)",
    )
    fl.set_defaults(func=_cmd_full_load)

    du = sub.add_parser("daily-update", help="Daily incremental update")
    du.add_argument("--date", type=str, default=None)
    du.add_argument("--force", action="store_true")
    du.set_defaults(func=_cmd_daily_update)

    st = sub.add_parser("status", help="Load and freshness snapshot")
    st.set_defaults(func=_cmd_status)

    vf = sub.add_parser("verify", help="Run freshness gate checks")
    vf.add_argument("--date", type=str, default=None)
    vf.add_argument("--json", action="store_true")
    vf.set_defaults(func=_cmd_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
