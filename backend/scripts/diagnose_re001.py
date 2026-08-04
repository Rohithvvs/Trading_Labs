"""Diagnose RE-001 decision coverage and reject reasons."""
from __future__ import annotations

import json
import sys

from sqlalchemy import text

from app.db.session import SessionLocal


def main() -> int:
    db = SessionLocal()
    try:
        print("=== totals ===")
        print("rows", db.execute(text("SELECT count(1) FROM recommendation_engine_decisions")).scalar())
        print(
            "unique symbols",
            db.execute(text("SELECT count(DISTINCT symbol) FROM recommendation_engine_decisions")).scalar(),
        )
        print(
            "unique scans",
            db.execute(
                text(
                    "SELECT count(DISTINCT scan_run_id) FROM recommendation_engine_decisions "
                    "WHERE scan_run_id IS NOT NULL"
                )
            ).scalar(),
        )

        print("\n=== by scan_run_id (latest 15) ===")
        rows = db.execute(
            text(
                """
                SELECT scan_run_id,
                       count(1) AS c,
                       count(DISTINCT symbol) AS syms,
                       string_agg(DISTINCT recommendation_state, ',' ORDER BY recommendation_state) AS states,
                       string_agg(DISTINCT symbol, ',' ORDER BY symbol) AS symbols
                FROM recommendation_engine_decisions
                GROUP BY scan_run_id
                ORDER BY max(created_at) DESC NULLS LAST
                LIMIT 15
                """
            )
        ).fetchall()
        for r in rows:
            print(dict(r._mapping))

        print("\n=== by symbol ===")
        for r in db.execute(
            text(
                """
                SELECT symbol, count(1) AS c, count(DISTINCT scan_run_id) AS scans,
                       string_agg(DISTINCT recommendation_state, ',' ORDER BY recommendation_state) AS states
                FROM recommendation_engine_decisions
                GROUP BY symbol ORDER BY c DESC LIMIT 20
                """
            )
        ).fetchall():
            print(dict(r._mapping))

        print("\n=== by state / evaluation_status ===")
        for r in db.execute(
            text(
                """
                SELECT recommendation_state, evaluation_status, count(1) AS c
                FROM recommendation_engine_decisions
                GROUP BY recommendation_state, evaluation_status
                ORDER BY c DESC
                """
            )
        ).fetchall():
            print(dict(r._mapping))

        print("\n=== reason_codes frequency (flatten JSON) ===")
        samples = db.execute(
            text(
                """
                SELECT symbol, scan_run_id, recommendation_state, market_regime,
                       strategy_name, reason_codes, confidence_score, production_action,
                       evaluation_status, evidence, left(coalesce(explanation,''), 240) AS expl,
                       created_at
                FROM recommendation_engine_decisions
                ORDER BY created_at DESC NULLS LAST
                LIMIT 25
                """
            )
        ).fetchall()
        reason_counts: dict[str, int] = {}
        for r in samples:
            m = dict(r._mapping)
            codes = m.get("reason_codes") or []
            if isinstance(codes, str):
                try:
                    codes = json.loads(codes)
                except Exception:
                    codes = [codes]
            for c in codes:
                reason_counts[str(c)] = reason_counts.get(str(c), 0) + 1
            print(
                {
                    "symbol": m["symbol"],
                    "scan": m["scan_run_id"],
                    "state": m["recommendation_state"],
                    "regime": m["market_regime"],
                    "strategy": m["strategy_name"],
                    "prod": m["production_action"],
                    "codes": codes,
                    "conf": m["confidence_score"],
                    "status": m["evaluation_status"],
                    "expl": m["expl"],
                    "created": str(m["created_at"]),
                }
            )
        print("\n=== reason_codes tallies (latest 25 rows) ===")
        for k, v in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")

        print("\n=== decisions per scan histogram ===")
        for r in db.execute(
            text(
                """
                SELECT c AS decisions_per_scan, count(1) AS num_scans
                FROM (
                  SELECT scan_run_id, count(1) AS c
                  FROM recommendation_engine_decisions
                  GROUP BY scan_run_id
                ) t
                GROUP BY c
                ORDER BY c
                """
            )
        ).fetchall():
            print(dict(r._mapping))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
