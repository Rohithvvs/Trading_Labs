"""Lab query helpers for RE-001 decisions."""

from __future__ import annotations

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ...models.recommendation_engine import RecommendationEngineDecision
from .persistence import (
    get_decision_by_id,
    get_latest_for_symbol,
    list_decisions_for_scan,
    row_to_decision_dict,
)


def query_scan_comparison(db: Session, scan_run_id: str) -> list[dict]:
    rows = list_decisions_for_scan(db, scan_run_id)
    return [row_to_decision_dict(r) for r in rows]


def query_decision(db: Session, recommendation_id: str) -> dict | None:
    row = get_decision_by_id(db, recommendation_id)
    return row_to_decision_dict(row) if row else None


def query_latest_symbol(db: Session, symbol: str) -> dict | None:
    row = get_latest_for_symbol(db, symbol)
    return row_to_decision_dict(row) if row else None


def list_recent_scan_runs(
    db: Session,
    *,
    limit: int = 20,
    engine_id: str = "RE-001",
    min_decisions: int = 1,
    prefer_cohorts: bool = True,
) -> list[dict]:
    """List scan_run_id cohorts for the Lab dropdown.

    Single-symbol ``full-*`` re-analyses also create scan_run_ids (one decision each).
    When prefer_cohorts=True, multi-symbol screener cohorts are ordered first so the
    Lab UI does not look stuck on BHARATFORG-style 1-row detail analyses.
    """
    min_decisions = max(1, int(min_decisions or 1))
    decision_count_col = func.count(RecommendationEngineDecision.id).label("decision_count")
    latest_col = func.max(RecommendationEngineDecision.created_at).label("latest_created_at")
    q = (
        db.query(
            RecommendationEngineDecision.scan_run_id,
            decision_count_col,
            latest_col,
        )
        .filter(
            RecommendationEngineDecision.engine_id == engine_id,
            RecommendationEngineDecision.scan_run_id.isnot(None),
        )
        .group_by(RecommendationEngineDecision.scan_run_id)
        .having(decision_count_col >= min_decisions)
    )
    if prefer_cohorts:
        # Multi-symbol screener runs first, then newest within each size band.
        q = q.order_by(desc(decision_count_col), desc(latest_col))
    else:
        q = q.order_by(desc(latest_col))
    q = q.limit(limit)
    out: list[dict] = []
    for scan_run_id, count, latest in q.all():
        if not scan_run_id:
            continue
        out.append(
            {
                "scan_run_id": str(scan_run_id),
                "decision_count": int(count or 0),
                "latest_created_at": latest.isoformat() if latest else None,
            }
        )
    return out
