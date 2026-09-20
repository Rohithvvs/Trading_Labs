"""Future-only repair planner, provider preview, and manifest builder.

    python -m app.cli.ohlcv_repair_plan --dry-run --from-anomaly-json report.json
    python -m app.cli.ohlcv_repair_plan --preview-provider --from-anomaly-json report.json --json
    python -m app.cli.ohlcv_repair_plan --build-manifest --from-preview-json preview.json --output repair_manifest.json

--execute is always refused until a later explicit approval.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

EXECUTE_DISABLED = "REPAIR EXECUTION IS DISABLED UNTIL EXPLICIT APPROVAL"


def plan_from_anomalies(anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    keys = []
    seen: set[tuple[str, str, str]] = set()
    for row in anomalies:
        table = str(row.get("table") or "daily_ohlcv")
        symbol = str(row.get("symbol") or "")
        trade_date = str(row.get("trade_date") or "")
        key = (table, symbol, trade_date)
        if not symbol or not trade_date or key in seen:
            continue
        seen.add(key)
        keys.append({"table": table, "symbol": symbol, "trade_date": trade_date})
    return {
        "wrote": False,
        "db_connected": False,
        "provider_called": False,
        "keys": keys,
        "key_count": len(keys),
        "provider": "PreviewSessionProvider (env-only FYERS_APP_ID / FYERS_ACCESS_TOKEN)",
        "steps": [
            "Backup local trading_data (pg_dump).",
            "Provider preview with process-env FYERS credentials.",
            "Build repair manifest from REPAIRABLE rows.",
            "Require --execute --confirm-local-backup --manifest --approved-repair-run-id.",
        ],
        "blocked": (
            "Live repair is disabled. This command will not UPDATE daily_ohlcv."
        ),
        "final_line": "REPAIR PLAN DRY-RUN — NO DATA WAS WRITTEN",
    }


def _parse_csv(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _load_json(path: str) -> dict[str, Any]:
    from decimal import Decimal

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_float=Decimal,
    )


def _load_anomalies(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = _load_json(path)
    return list(payload.get("anomalies") or [])


def _write_output(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    Path(path).write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _print_payload(payload: dict[str, Any], *, as_json: bool, text_fn, final_key: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str, ensure_ascii=False))
    else:
        print(text_fn(payload))
    print(payload.get(final_key) or payload.get("final_line") or "")


def _run_repair(args: argparse.Namespace, *, execute: bool) -> int:
    from app.config.settings import settings
    from app.services.market_data_ingestion.repair_apply import RepairError, apply_manifest_repairs

    if not args.manifest:
        print(json.dumps({"status": "ERROR", "wrote": False, "reason": "--manifest is required"}))
        return 2
    try:
        manifest = _load_json(args.manifest)
    except FileNotFoundError:
        print(json.dumps({"status": "ERROR", "wrote": False, "reason": "manifest file not found"}))
        return 2
    try:
        payload = apply_manifest_repairs(
            manifest,
            local_postgres_url=settings.local_postgres_source_url(),
            approved_run_id=args.approved_repair_run_id,
            confirm_local_backup=bool(args.confirm_local_backup),
            execute=execute,
            limit=args.limit,
        )
    except RepairError as exc:
        print(json.dumps({"status": "REFUSED", "wrote": False, "reason": str(exc)}, indent=2))
        return 2
    _write_output(args.output or None, payload)
    skipped_path = getattr(args, "skipped_report", "") or ""
    if skipped_path:
        skipped = [r for r in payload.get("results") or [] if r.get("status") in {"ALREADY_REPAIRED", "FINGERPRINT_MISMATCH"}]
        _write_output(
            skipped_path,
            {"wrote": False, "item_count": len(skipped), "items": skipped},
        )
    print(json.dumps(payload, indent=2, default=str, ensure_ascii=False))
    print(payload.get("final_line") or "")
    return 0 if payload.get("status") != "REFUSED" else 2


def _refuse_execute() -> int:
    print(
        json.dumps(
            {
                "status": "REFUSED",
                "wrote": False,
                "db_connected": False,
                "reason": EXECUTE_DISABLED,
                "required_later": [
                    "--execute",
                    "--confirm-local-backup",
                    "--manifest PATH",
                    "--approved-repair-run-id ID",
                    "local-only source host",
                    "expected-old-row fingerprint match",
                    "transactional UPDATE of manifest keys only",
                ],
            },
            indent=2,
        )
    )
    print(EXECUTE_DISABLED)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ohlcv_repair_plan")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--preview-provider", action="store_true")
    parser.add_argument("--build-manifest", action="store_true")
    parser.add_argument("--build-phantom-review", action="store_true")
    parser.add_argument("--from-anomaly-json", type=str, default="")
    parser.add_argument("--from-preview-json", type=str, default="")
    parser.add_argument("--symbols", type=str, default="")
    parser.add_argument("--dates", type=str, default="")
    parser.add_argument("--tables", type=str, default="")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--repair-dry-run", action="store_true")
    parser.add_argument("--confirm-local-backup", action="store_true")
    parser.add_argument("--manifest", type=str, default="")
    parser.add_argument("--approved-repair-run-id", type=str, default="")
    parser.add_argument("--skipped-report", type=str, default="")
    args = parser.parse_args(argv)
    if args.execute and not args.repair_dry_run:
        missing = []
        if not args.confirm_local_backup:
            missing.append("--confirm-local-backup")
        if not args.manifest:
            missing.append("--manifest")
        if not args.approved_repair_run_id:
            missing.append("--approved-repair-run-id")
        if missing:
            print(json.dumps({"status": "REFUSED", "wrote": False, "reason": EXECUTE_DISABLED, "missing": missing}, indent=2))
            print(EXECUTE_DISABLED)
            return 2
        return _run_repair(args, execute=True)
    if args.repair_dry_run:
        return _run_repair(args, execute=False)

    if args.build_phantom_review:
        from app.services.market_data_ingestion.repair_manifest import (
            ManifestError,
            build_phantom_delete_review,
        )

        if not args.from_preview_json or not args.output:
            print(json.dumps({"status": "ERROR", "wrote": False, "reason": "--from-preview-json and --output are required"}))
            return 2
        try:
            report = build_phantom_delete_review(_load_json(args.from_preview_json))
        except ManifestError as exc:
            print(json.dumps({"status": "ERROR", "wrote": False, "reason": str(exc)}))
            return 2
        _write_output(args.output, report)
        print(json.dumps({"status": "OK", "wrote": False, "deleted": False, "item_count": report["item_count"], "output": args.output}, indent=2))
        print("PHANTOM REVIEW WRITTEN — NO DELETE")
        return 0

    if args.build_manifest:
        from app.services.market_data_ingestion.repair_manifest import (
            ManifestError,
            build_repair_manifest,
            checksum_bytes,
        )

        if not args.from_preview_json:
            print(json.dumps({"status": "ERROR", "wrote": False, "reason": "--from-preview-json is required"}))
            return 2
        raw = Path(args.from_preview_json).read_bytes()
        try:
            from decimal import Decimal

            manifest = build_repair_manifest(
                json.loads(raw.decode("utf-8"), parse_float=Decimal),
                source_checksum=checksum_bytes(raw),
            )
        except ManifestError as exc:
            print(json.dumps({"status": "ERROR", "wrote": False, "reason": str(exc)}))
            return 2
        if not args.output:
            print(json.dumps({"status": "ERROR", "wrote": False, "reason": "--output is required for --build-manifest"}))
            return 2
        _write_output(args.output, manifest)
        print(json.dumps({"status": "OK", "wrote": False, "item_count": manifest["item_count"], "output": args.output}, indent=2))
        print("MANIFEST WRITTEN — NO DATABASE UPDATE")
        return 0

    anomalies = _load_anomalies(args.from_anomaly_json)
    if args.preview_provider:
        from app.services.market_data_ingestion.repair_preview import (
            PREVIEW_LINE,
            PreviewAuthError,
            PreviewRateLimitError,
            PreviewRequestError,
            PreviewResponseInvalidError,
            PreviewTokenError,
            format_preview_text,
            preview_provider_keys,
        )

        try:
            payload = asyncio.run(
                preview_provider_keys(
                    anomalies,
                    symbols=_parse_csv(args.symbols) or None,
                    dates=_parse_csv(args.dates) or None,
                    tables=_parse_csv(args.tables) or None,
                    limit=args.limit,
                )
            )
        except PreviewTokenError as exc:
            payload = {
                "status": "TOKEN_MISSING",
                "wrote": False,
                "db_connected": False,
                "turso_connected": False,
                "reason": str(exc),
                "final_line": PREVIEW_LINE,
            }
            _print_payload(payload, as_json=True, text_fn=lambda p: str(exc), final_key="final_line")
            return 2
        except PreviewAuthError as exc:
            payload = {
                "status": "FYERS_AUTH_FAILED",
                "wrote": False,
                "db_connected": False,
                "reason": str(exc),
                "final_line": PREVIEW_LINE,
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            print(PREVIEW_LINE)
            return 2
        except PreviewRateLimitError as exc:
            payload = {
                "status": "FYERS_RATE_LIMITED",
                "wrote": False,
                "db_connected": False,
                "reason": str(exc),
                "final_line": PREVIEW_LINE,
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            print(PREVIEW_LINE)
            return 2
        except (PreviewRequestError, PreviewResponseInvalidError) as exc:
            payload = {
                "status": getattr(exc, "status", "FYERS_REQUEST_FAILED"),
                "wrote": False,
                "db_connected": False,
                "reason": str(exc),
                "final_line": PREVIEW_LINE,
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            print(PREVIEW_LINE)
            return 2
        _write_output(args.output or None, payload)
        _print_payload(
            payload,
            as_json=bool(args.json),
            text_fn=format_preview_text,
            final_key="final_line",
        )
        if payload.get("status") not in (None, "OK"):
            return 2
        return 0

    plan = plan_from_anomalies(anomalies)
    print(json.dumps(plan, indent=2, default=str))
    print(plan["final_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
