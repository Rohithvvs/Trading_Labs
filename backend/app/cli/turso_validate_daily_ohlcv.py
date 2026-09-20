"""Compare local Postgres vs Turso daily/index history.

    python -m app.cli.turso_validate_daily_ohlcv --json
    python -m app.cli.turso_validate_daily_ohlcv --live --symbols INFY-EQ --tables daily_ohlcv --limit 100 --json --output turso_test_validation_infy.json

Bounded --live INFY-EQ compare is read-only. Full --live remains refused.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from app.services.market_data_ingestion.turso_migrate import validate_models_against_v1_schema


def _print(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
        return
    ok = payload.get("ok")
    print(f"ok={ok} live_compare={payload.get('live_compare')} skipped={payload.get('skipped', False)}")
    if payload.get("missing"):
        print(f"missing={payload['missing']}")
    if payload.get("mismatch_codes"):
        print(f"mismatch_codes={payload['mismatch_codes']}")
    if payload.get("reason"):
        print(f"reason={payload['reason']}")
    if payload.get("note"):
        print(payload["note"])


def _parse_csv(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def run(args: argparse.Namespace) -> int:
    if args.live:
        from app.config.settings import settings
        from app.db.turso import connect_turso
        from app.db.urls import public_db_target
        from app.services.market_data_ingestion.turso_bounded_copy import fetch_daily_symbol_rows
        from app.services.market_data_ingestion.turso_test_validate import (
            FAILED,
            compare_bounded_daily_rows,
            validate_infy_test_compare_request,
        )

        symbols = _parse_csv(getattr(args, "symbols", "") or "")
        tables = _parse_csv(getattr(args, "tables", "") or "")
        local_url = settings.local_postgres_source_url()
        errors = validate_infy_test_compare_request(
            symbols=symbols or None,
            tables=tables or None,
            limit=args.limit,
            local_postgres_url=local_url,
            output=getattr(args, "output", "") or "",
        )
        if errors:
            payload = {
                "ok": False,
                "wrote": False,
                "live_compare": False,
                "skipped": True,
                "reasons": errors,
                "source_target": public_db_target(local_url),
                "final_line": FAILED,
            }
            _print(payload, as_json=True)
            print(FAILED)
            return 2
        local_rows = fetch_daily_symbol_rows(local_url, symbol="INFY-EQ", limit=int(args.limit))
        client = connect_turso(settings)
        try:
            turso_rows = client.execute(
                "SELECT trade_date, symbol, open, high, low, close, volume, "
                "delivery_qty, delivery_pct, turnover, adtv_20, source, loaded_at "
                "FROM daily_ohlcv WHERE symbol = ? ORDER BY trade_date ASC LIMIT ?",
                ["INFY-EQ", int(args.limit)],
            )
        finally:
            client.close()
        payload = compare_bounded_daily_rows(local_rows, turso_rows)
        payload["source_target"] = public_db_target(local_url)
        payload["turso_target"] = public_db_target(settings.turso_database_url)
        from pathlib import Path

        Path(args.output).write_text(
            json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _print(payload, as_json=bool(args.json) or True)
        print(payload["final_line"])
        return 0 if payload.get("ok") else 2
    result = validate_models_against_v1_schema()
    _print(result, as_json=bool(args.json))
    return 0 if result.get("ok") else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="turso_validate_daily_ohlcv",
        description="Validate v1 daily/index history (static or bounded INFY live compare)",
    )
    p.add_argument("--live", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbols", type=str, default="")
    p.add_argument("--tables", type=str, default="")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--output", type=str, default="")
    p.add_argument("--sample-size", type=int, default=20)
    p.add_argument("--close-tolerance", type=float, default=1e-6)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
