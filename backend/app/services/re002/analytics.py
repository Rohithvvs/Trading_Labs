"""RE-002 health metrics from decisions table (SQL aggregates; process counters non-authoritative)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ...models.recommendation_engine import RecommendationEngineDecision
from .metrics import snapshot as runtime_snapshot


def health_segment(
    db: Session,
    *,
    window_hours: int = 24 * 7,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    """Aggregate RE-002 decision health without loading all rows into memory."""
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, window_hours))
    state = func.upper(RecommendationEngineDecision.recommendation_state)
    eval_status = func.lower(RecommendationEngineDecision.evaluation_status)

    q = db.query(
        func.count(RecommendationEngineDecision.id).label("total"),
        func.coalesce(func.sum(case((state == "BUY", 1), else_=0)), 0).label("buy_count"),
        func.coalesce(func.sum(case((state == "WATCH", 1), else_=0)), 0).label("watch_count"),
        func.coalesce(func.sum(case((state == "REJECT", 1), else_=0)), 0).label("reject_count"),
        func.coalesce(func.sum(case((eval_status == "error", 1), else_=0)), 0).label("error_count"),
        func.coalesce(func.sum(case((eval_status == "timeout", 1), else_=0)), 0).label(
            "timeout_count"
        ),
        func.coalesce(
            func.sum(case((RecommendationEngineDecision.is_mismatch.is_(True), 1), else_=0)),
            0,
        ).label("mismatch_count"),
    ).filter(
        RecommendationEngineDecision.engine_id == "RE-002",
        RecommendationEngineDecision.created_at >= since,
    )
    if experiment_id and hasattr(RecommendationEngineDecision, "experiment_id"):
        q = q.filter(RecommendationEngineDecision.experiment_id == experiment_id)

    row = q.one()

    # Avg RS of BUYs when present — only BUY rows (bounded), real RS fields only.
    avg_rs: float | None = None
    try:
        buy_q = db.query(RecommendationEngineDecision.evidence).filter(
            RecommendationEngineDecision.engine_id == "RE-002",
            RecommendationEngineDecision.created_at >= since,
            func.upper(RecommendationEngineDecision.recommendation_state) == "BUY",
        )
        if experiment_id and hasattr(RecommendationEngineDecision, "experiment_id"):
            buy_q = buy_q.filter(RecommendationEngineDecision.experiment_id == experiment_id)
        rs_vals: list[float] = []
        for (evidence,) in buy_q.limit(2000).all():
            if not isinstance(evidence, dict):
                continue
            rs_block = evidence.get("rs") if isinstance(evidence.get("rs"), dict) else None
            if not rs_block or rs_block.get("rs_available") is False:
                continue
            v = rs_block.get("sector_rs_20")
            if v is None:
                v = rs_block.get("rs_vs_market")
            try:
                if v is not None:
                    rs_vals.append(float(v))
            except (TypeError, ValueError):
                continue
        if rs_vals:
            avg_rs = sum(rs_vals) / len(rs_vals)
    except Exception:
        avg_rs = None

    return {
        "engine_id": "RE-002",
        "buy_count": int(row.buy_count or 0),
        "watch_count": int(row.watch_count or 0),
        "reject_count": int(row.reject_count or 0),
        "error_count": int(row.error_count or 0),
        "timeout_count": int(row.timeout_count or 0),
        "mismatch_count": int(row.mismatch_count or 0),
        "total": int(row.total or 0),
        "avg_rs_of_buys": avg_rs,
        "experiment_id": experiment_id,
        # Non-authoritative process-local counters (multi-worker / restart lose data)
        "runtime_counters": runtime_snapshot(),
        "runtime_counters_authoritative": False,
    }
