"""Turso candle-history operator CLI (schema, dry-run migrate, validate).

Default commands never write. Live Turso schema apply requires --execute.
Live migration requires --execute and --confirm-local-backup.

    python -m app.cli.turso_cli schema-apply
    python -m app.cli.turso_cli migrate --dry-run
    python -m app.cli.turso_cli validate
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from app.config.settings import settings
from app.services.market_data_ingestion.turso_migrate import (
    plan_v1_migration,
    refuse_live_migration,
    schema_apply_result,
    validate_models_against_v1_schema,
)


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _cmd_schema_apply(args: argparse.Namespace) -> int:
    if args.execute:
        return _schema_apply_execute()
    result = schema_apply_result(execute=False)
    result["turso_url_set"] = bool((settings.turso_database_url or "").strip())
    result["note"] = (
        "Dry-run: SQL not applied. Re-run with --execute to apply on Turso "
        "(not done automatically)."
    )
    _print(result)
    return 0


def _schema_apply_execute() -> int:
    from app.db.turso import apply_v1_schema, connect_turso, inspect_v1_schema
    from app.db.urls import public_db_target

    client = connect_turso(settings)
    try:
        applied = apply_v1_schema(client, execute=True)
        meta = inspect_v1_schema(client)
        payload = {
            **applied,
            "target": public_db_target(settings.turso_database_url),
            "postgres_untouched": True,
            "schema": meta,
        }
        _print(payload)
        return 0 if meta.get("ok") else 2
    finally:
        client.close()


def _cmd_schema_verify(args: argparse.Namespace) -> int:
    from app.db.turso import connect_turso, inspect_v1_schema
    from app.db.urls import public_db_target

    client = connect_turso(settings)
    try:
        meta = inspect_v1_schema(client)
        meta["target"] = public_db_target(settings.turso_database_url)
        meta["wrote"] = False
        _print(meta)
        return 0 if meta.get("ok") else 2
    finally:
        client.close()


def _cmd_migrate(args: argparse.Namespace) -> int:
    tables = None
    if args.tables:
        tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    if args.execute:
        reason = refuse_live_migration(
            execute=True,
            confirm_local_backup=bool(args.confirm_local_backup),
            local_postgres_url=settings.local_postgres_source_url(),
        )
        _print({"status": "REFUSED", "wrote": False, "reason": reason})
        return 2

    try:
        plan = plan_v1_migration(
            source_url=settings.local_postgres_source_url() or None,
            symbols=symbols,
            limit=args.limit,
            tables=tables,
            batch_size=getattr(args, "batch_size", 500),
        )
    except ValueError as exc:
        _print({"status": "ERROR", "wrote": False, "reason": str(exc)})
        return 2
    _print(plan)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    if args.live:
        _print(
            {
                "ok": False,
                "live_compare": False,
                "skipped": True,
                "reason": (
                    "Live local-vs-Turso validation is skipped in this phase. "
                    "It would read trading_data and Turso; run it only after approval."
                ),
            }
        )
        return 2
    result = validate_models_against_v1_schema()
    _print(result)
    return 0 if result.get("ok") else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="turso_cli", description="Turso v1 candle-history ops")
    sub = p.add_subparsers(dest="command", required=True)

    sa = sub.add_parser("schema-apply", help="Show or apply Turso v1 DDL (default dry-run)")
    sa.add_argument("--execute", action="store_true", help="Apply DDL on Turso (refused until approved)")
    sa.add_argument(
        "--confirm-local-backup",
        action="store_true",
        help="Acknowledges a local dump exists (required with --execute for migrate)",
    )
    sa.set_defaults(func=_cmd_schema_apply)

    sv = sub.add_parser("schema-verify", help="Read-only Turso table/index metadata")
    sv.set_defaults(func=_cmd_schema_verify)

    mig = sub.add_parser("migrate", help="Plan or run local→Turso copy (default dry-run)")
    mig.add_argument("--dry-run", action="store_true", default=True)
    mig.add_argument("--execute", action="store_true", help="Write to Turso (refused without backup flag)")
    mig.add_argument(
        "--confirm-local-backup",
        action="store_true",
        help="Required with --execute; confirms a local Postgres dump exists",
    )
    mig.add_argument("--limit", type=int, default=None, help="Max rows per table for a test copy")
    mig.add_argument("--symbols", type=str, default="", help="Comma-separated symbol filter")
    mig.add_argument("--tables", type=str, default="", help="Subset of daily_ohlcv,index_ohlcv")
    mig.add_argument("--batch-size", type=int, default=500)
    mig.set_defaults(func=_cmd_migrate)

    val = sub.add_parser("validate", help="Static model vs Turso SQL check")
    val.add_argument(
        "--live",
        action="store_true",
        help="Compare live local Postgres vs Turso (skipped until approved)",
    )
    val.set_defaults(func=_cmd_validate)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
