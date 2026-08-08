"""Lab query helpers for RE-002."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ...models.recommendation_engine import RecommendationEngineDecision
from .persistence import (
    get_decision_by_id,
    get_latest_for_symbol,
    list_decisions_for_scan,
    row_to_decision_dict,
)
from .registry import get_re002_registration


def registration_payload() -> dict[str, Any]:
    reg = get_re002_registration()
    return reg.model_dump()


def scan_comparison(db: Session, scan_run_id: str) -> list[dict[str, Any]]:
    rows = list_decisions_for_scan(db, scan_run_id, engine_id="RE-002")
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "symbol": row.symbol,
                "recommendation_id": row.recommendation_id,
                "production_action": row.production_action,
                "production_score": row.production_score,
                "re002_state": row.recommendation_state,
                "confidence_score": row.confidence_score,
                "strategy_name": row.strategy_name,
                "strategy_family": row.strategy_family,
                "is_mismatch": row.is_mismatch,
                "experiment_id": getattr(row, "experiment_id", None),
            }
        )
    return items


def latest_for_symbol(db: Session, symbol: str) -> dict[str, Any] | None:
    row = get_latest_for_symbol(db, symbol, engine_id="RE-002")
    if row is None:
        return None
    return row_to_decision_dict(row)


def by_recommendation_id(db: Session, recommendation_id: str) -> dict[str, Any] | None:
    row = get_decision_by_id(db, recommendation_id)
    if row is None or row.engine_id != "RE-002":
        return None
    return row_to_decision_dict(row)


def list_recent_scan_runs(
    db: Session,
    *,
    limit: int = 20,
    min_decisions: int = 1,
    prefer_cohorts: bool = True,
) -> list[dict[str, Any]]:
    """List RE-002 scan_run_id cohorts for Lab dropdown (engine_id=RE-002)."""
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
            RecommendationEngineDecision.engine_id == "RE-002",
            RecommendationEngineDecision.scan_run_id.isnot(None),
        )
        .group_by(RecommendationEngineDecision.scan_run_id)
        .having(decision_count_col >= min_decisions)
    )
    if prefer_cohorts:
        q = q.order_by(desc(decision_count_col), desc(latest_col))
    else:
        q = q.order_by(desc(latest_col))
    q = q.limit(limit)
    out: list[dict[str, Any]] = []
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


def list_history(
    db: Session,
    *,
    experiment_id: str | None = None,
    symbol: str | None = None,
    state: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Paged RE-002 decision history (contract C6). Ordered by created_at desc."""
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    q = db.query(RecommendationEngineDecision).filter(
        RecommendationEngineDecision.engine_id == "RE-002",
    )
    if experiment_id and hasattr(RecommendationEngineDecision, "experiment_id"):
        q = q.filter(RecommendationEngineDecision.experiment_id == experiment_id)
    if symbol:
        q = q.filter(RecommendationEngineDecision.symbol == str(symbol).strip().upper())
    if state:
        q = q.filter(
            func.upper(RecommendationEngineDecision.recommendation_state) == str(state).strip().upper()
        )
    if from_ts is not None:
        q = q.filter(RecommendationEngineDecision.created_at >= from_ts)
    if to_ts is not None:
        q = q.filter(RecommendationEngineDecision.created_at <= to_ts)

    total = q.count()
    rows = (
        q.order_by(desc(RecommendationEngineDecision.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [row_to_decision_dict(r) for r in rows]
    return {
        "engine_id": "RE-002",
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "items": items,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
