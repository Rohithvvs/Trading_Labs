"""Local Postgres trading_data → Turso copy (v1 daily_ohlcv + index_ohlcv).

    python -m app.cli.turso_migrate_daily_ohlcv --dry-run
    python -m app.cli.turso_migrate_daily_ohlcv --source-inspect
    python -m app.cli.turso_migrate_daily_ohlcv --source-anomalies --json
    python -m app.cli.turso_migrate_daily_ohlcv --execute --confirm-local-backup

--dry-run is models-only (no DB connections).
--source-inspect is read-only against LOCAL_POSTGRES_DATABASE_URL (never DATABASE_URL, never Turso).
Live writes are refused in this phase.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from app.config.settings import settings
from app.services.market_data_ingestion.turso_migrate import (
    plan_v1_migration,
    refuse_live_migration,
)
from app.services.market_data_ingestion.turso_source_anomalies import (
    ANOMALY_LINE,
    format_anomaly_text,
    run_source_anomalies,
)
from app.services.market_data_ingestion.turso_source_preflight import (
    FAILED_LINE,
    FINAL_FAILED_LINE,
    PreflightError,
    format_final_preflight_text,
    format_preflight_text,
    run_final_source_preflight,
    run_source_preflight,
)


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str, ensure_ascii=False))


def _parse_list(raw: str) -> list[str] | None:
    items = [x.strip() for x in (raw or "").split(",") if x.strip()]
    return items or None


def _write_output(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    from pathlib import Path

    out = Path(path)
    out.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    symbols = _parse_list(args.symbols)
    tables = _parse_list(args.tables)
    local_url = settings.local_postgres_source_url()
    if getattr(args, "source_anomalies", False):
        try:
            payload = run_source_anomalies(
                local_postgres_url=local_url,
                symbols=symbols,
                tables=tables,
                limit=args.limit,
            )
        except PreflightError as exc:
            payload = {
                "ok": False,
                "wrote": False,
                "turso_connected": False,
                "mode": "source-anomalies",
                "failures": [str(exc)],
                "final_line": ANOMALY_LINE,
            }
            if args.json:
                _print(payload)
            else:
                print(str(exc))
            print(ANOMALY_LINE)
            return 2
        _write_output(getattr(args, "output", None), payload)
        if args.json:
            _print(payload)
            print(payload.get("final_line") or ANOMALY_LINE)
        else:
            print(format_anomaly_text(payload))
        return 0
    if args.source_inspect:
        try:
            payload = run_source_preflight(
                local_postgres_url=local_url,
                symbols=symbols,
                tables=tables,
                limit=args.limit,
                batch_size=args.batch_size,
            )
        except PreflightError as exc:
            payload = {
                "ok": False,
                "wrote": False,
                "turso_connected": False,
                "mode": "source-inspect",
                "failures": [str(exc)],
                "final_line": FAILED_LINE,
            }
            if args.json:
                _print(payload)
            else:
                print(str(exc))
            print(FAILED_LINE)
            return 2
        _write_output(getattr(args, "output", None), payload)
        if args.json:
            _print(payload)
            print(payload.get("final_line") or FAILED_LINE)
        else:
            print(format_preflight_text(payload))
        return 0 if payload.get("ok") else 2
    if getattr(args, "final_preflight", False):
        try:
            payload = run_final_source_preflight(
                local_postgres_url=local_url,
                exclude_json_paths=_parse_list(getattr(args, "exclude_json", "") or "") or [],
                repair_manifest_path=getattr(args, "repair_manifest", "") or None,
                tables=tables,
                batch_size=args.batch_size,
            )
        except PreflightError as exc:
            payload = {
                "ok": False,
                "wrote": False,
                "turso_connected": False,
                "mode": "final-source-preflight",
                "failures": [str(exc)],
                "final_line": FINAL_FAILED_LINE,
            }
            _write_output(getattr(args, "output", None), payload)
            if args.json:
                _print(payload)
            else:
                print(str(exc))
            print(FINAL_FAILED_LINE)
            return 2
        _write_output(getattr(args, "output", None), payload)
        if args.json:
            _print(payload)
            print(payload.get("final_line") or FINAL_FAILED_LINE)
        else:
            print(format_final_preflight_text(payload))
        return 0 if payload.get("ok") else 2
    if args.execute:
        from app.db.turso import connect_turso
        from app.db.urls import public_db_target

        if getattr(args, "full", False):
            from app.services.market_data_ingestion.turso_full_copy import (
                FullCopyError,
                run_full_v1_copy,
                validate_full_copy_request,
            )

            errors = validate_full_copy_request(
                full=True,
                confirm_local_backup=bool(args.confirm_local_backup),
                symbols=symbols,
                tables=tables,
                limit=args.limit,
                batch_size=args.batch_size,
                local_postgres_url=local_url,
                exclude_json=getattr(args, "exclude_json", "") or "",
                exclusion_report=getattr(args, "exclusion_report", "") or "",
                result_report=getattr(args, "result_report", "") or "",
                migration_policy=getattr(args, "migration_policy", "") or "",
            )
            if errors:
                _print(
                    {
                        "status": "REFUSED",
                        "wrote": False,
                        "wrote_postgres": False,
                        "reason": "; ".join(errors),
                        "reasons": errors,
                        "source_target": public_db_target(local_url),
                    }
                )
                return 2
            client = connect_turso(settings)
            try:
                payload = run_full_v1_copy(
                    local_postgres_url=local_url,
                    turso_client=client,
                    exclude_json_paths=_parse_list(args.exclude_json) or [],
                    exclusion_report_path=args.exclusion_report,
                    result_report_path=args.result_report,
                    batch_size=int(args.batch_size or 500),
                    progress_path=getattr(args, "progress_log", "") or None,
                )
            except FullCopyError as exc:
                _print({"status": "ERROR", "wrote": False, "wrote_postgres": False, "reason": str(exc)})
                return 2
            finally:
                client.close()
            _print(payload)
            return 0

        from app.services.market_data_ingestion.turso_bounded_copy import (
            BoundedCopyError,
            run_bounded_infy_copy,
            validate_bounded_test_request,
        )

        errors = validate_bounded_test_request(
            symbols=symbols,
            tables=tables,
            limit=args.limit,
            batch_size=args.batch_size,
            local_postgres_url=local_url,
            exclude_json=getattr(args, "exclude_json", "") or "",
            exclusion_report=getattr(args, "exclusion_report", "") or "",
            result_report=getattr(args, "result_report", "") or "",
            confirm_local_backup=bool(args.confirm_local_backup),
        )
        if errors:
            _print(
                {
                    "status": "REFUSED",
                    "wrote": False,
                    "wrote_postgres": False,
                    "reason": "; ".join(errors),
                    "reasons": errors,
                    "source_target": public_db_target(local_url),
                }
            )
            return 2
        client = connect_turso(settings)
        try:
            payload = run_bounded_infy_copy(
                local_postgres_url=local_url,
                turso_client=client,
                exclude_json_paths=_parse_list(args.exclude_json) or [],
                exclusion_report_path=args.exclusion_report,
                result_report_path=args.result_report,
                limit=int(args.limit),
                batch_size=int(args.batch_size or 100),
            )
        except BoundedCopyError as exc:
            _print({"status": "ERROR", "wrote": False, "reason": str(exc)})
            return 2
        finally:
            client.close()
        _print(payload)
        return 0
    try:
        plan = plan_v1_migration(
            source_url=local_url or None,
            symbols=symbols,
            limit=args.limit,
            tables=tables,
            batch_size=args.batch_size,
            exclude_json_paths=_parse_list(getattr(args, "exclude_json", "") or "") or [],
        )
    except ValueError as exc:
        _print({"status": "ERROR", "wrote": False, "reason": str(exc)})
        return 2
    report_path = getattr(args, "exclusion_report", "") or ""
    if report_path:
        from pathlib import Path

        from app.services.market_data_ingestion.turso_exclusions import write_exclusion_report

        write_exclusion_report(Path(report_path), plan.get("exclusions") or [])
        plan["exclusion_report"] = report_path
    _print(plan)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="turso_migrate_daily_ohlcv",
        description="Copy daily_ohlcv/index_ohlcv from local Postgres to Turso",
    )
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument(
        "--source-inspect",
        action="store_true",
        help="Read-only inspect of LOCAL_POSTGRES_DATABASE_URL (never Turso, never DATABASE_URL)",
    )
    p.add_argument(
        "--source-anomalies",
        action="store_true",
        help="Read-only invalid-bar listing from LOCAL_POSTGRES_DATABASE_URL (diagnosis only)",
    )
    p.add_argument(
        "--final-preflight",
        action="store_true",
        help="Read-only full source preflight with V1 exclusion/repair classification",
    )
    p.add_argument("--json", action="store_true", help="JSON output for inspect/anomaly modes")
    p.add_argument("--output", type=str, default="", help="Optional JSON report path (anomaly/inspect)")
    p.add_argument("--execute", action="store_true")
    p.add_argument(
        "--full",
        action="store_true",
        help="Full V1 copy of daily_ohlcv+index_ohlcv (requires --execute and confirmation)",
    )
    p.add_argument("--confirm-local-backup", action="store_true")
    p.add_argument(
        "--repair-manifest",
        type=str,
        default="",
        help="repair_manifest_v2.json for final-preflight repaired-key checks",
    )
    p.add_argument(
        "--progress-log",
        type=str,
        default="",
        help="Append-only JSONL progress path for --full --execute (no secrets)",
    )
    p.add_argument(
        "--migration-policy",
        type=str,
        default="",
        help="Required for --full --execute. Must be validated_legacy_backfill_v1",
    )
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--symbols", type=str, default="")
    p.add_argument("--tables", type=str, default="daily_ohlcv,index_ohlcv")
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument(
        "--exclude-json",
        type=str,
        default="",
        help="Comma-separated exclusion JSON files (e.g. phantom_rows_delete_review.json)",
    )
    p.add_argument(
        "--exclusion-report",
        type=str,
        default="",
        help="Path to write the exclusion report (required for approved test --execute)",
    )
    p.add_argument(
        "--result-report",
        type=str,
        default="",
        help="Path to write the migration result JSON (required for approved test --execute)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
