"""RE-002 Recommendation Lab read APIs (multi-engine extension)."""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..config.settings import settings
from ..core.deps import require_feature_sync
from ..db.session import get_sync_db
from ..schemas.re002 import (
    Re002ComparisonRow,
    Re002HealthSegment,
    Re002HistoryResponse,
    Re002RecentScansResponse,
    Re002Registration,
    Re002ScanComparisonResponse,
    Re002ScanRunSummary,
)
from ..services.re002.analytics import health_segment
from ..services.re002.lab_query import (
    by_recommendation_id,
    latest_for_symbol,
    list_history,
    list_recent_scan_runs,
    scan_comparison,
)
from ..services.re002.registry import get_re002_registration

router = APIRouter(prefix="/api/v1/recommendation-lab", tags=["recommendation-lab-re002"])

_SCAN_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
_RECOMMENDATION_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,32}$")


def _lab_access():
    def _dep(_principal=Depends(require_feature_sync("recommendation_lab"))):
        if not bool(getattr(settings, "re002_ui_enabled", True)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="RE-002 lab UI is disabled (RE002_UI_ENABLED=false)",
            )
        return _principal

    return _dep


@router.get("/re002/registration", response_model=Re002Registration)
def get_re002_registration_route(
    _=Depends(_lab_access()),
) -> Re002Registration:
    return get_re002_registration()


@router.get("/re002/scans/recent", response_model=Re002RecentScansResponse)
def get_re002_recent_scans(
    limit: int = Query(default=20, ge=1, le=100),
    min_decisions: int = Query(default=1, ge=1, le=500),
    prefer_cohorts: bool = Query(default=True),
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> Re002RecentScansResponse:
    items = [
        Re002ScanRunSummary(**row)
        for row in list_recent_scan_runs(
            db,
            limit=limit,
            min_decisions=min_decisions,
            prefer_cohorts=prefer_cohorts,
        )
    ]
    return Re002RecentScansResponse(items=items)


@router.get("/re002/history", response_model=Re002HistoryResponse)
def get_re002_history(
    experiment_id: str | None = Query(default=None, max_length=64),
    symbol: str | None = Query(default=None, max_length=32),
    state: str | None = Query(default=None, max_length=12),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> Re002HistoryResponse:
    if symbol is not None:
        sym = symbol.strip().upper()
        if sym and not _SYMBOL_RE.match(sym):
            raise HTTPException(status_code=400, detail="Invalid symbol")
        symbol = sym or None
    if state is not None:
        st = state.strip().upper()
        if st and st not in {"BUY", "WATCH", "REJECT"}:
            raise HTTPException(status_code=400, detail="Invalid state")
        state = st or None
    payload = list_history(
        db,
        experiment_id=(experiment_id or "").strip() or None,
        symbol=symbol,
        state=state,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
    return Re002HistoryResponse(**payload)


@router.get("/re002/scans/{scan_run_id}/comparison", response_model=Re002ScanComparisonResponse)
def get_re002_scan_comparison(
    scan_run_id: str,
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> Re002ScanComparisonResponse:
    s = (scan_run_id or "").strip()
    if not s or not _SCAN_RUN_ID_RE.match(s):
        raise HTTPException(status_code=400, detail="Invalid scan_run_id")
    rows = scan_comparison(db, s)
    items = [
        Re002ComparisonRow(
            symbol=str(r.get("symbol") or ""),
            recommendation_id=str(r.get("recommendation_id") or ""),
            production_action=r.get("production_action"),
            production_score=r.get("production_score"),
            re002_state=r.get("re002_state") or "REJECT",  # type: ignore[arg-type]
            confidence_score=float(r.get("confidence_score") or 0.0),
            strategy_name=r.get("strategy_name"),
            strategy_family=r.get("strategy_family"),
            is_mismatch=r.get("is_mismatch"),
            experiment_id=r.get("experiment_id"),
        )
        for r in rows
    ]
    return Re002ScanComparisonResponse(scan_run_id=s, items=items)


@router.get("/re002/decisions/{recommendation_id}")
def get_re002_decision(
    recommendation_id: str,
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> dict:
    rid = (recommendation_id or "").strip()
    if not rid or not _RECOMMENDATION_ID_RE.match(rid):
        raise HTTPException(status_code=400, detail="Invalid recommendation_id")
    row = by_recommendation_id(db, rid)
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    return row


@router.get("/re002/symbols/{symbol}/latest")
def get_re002_symbol_latest(
    symbol: str,
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> dict:
    sym = (symbol or "").strip().upper()
    if not sym or not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail="Invalid symbol")
    row = latest_for_symbol(db, sym)
    if not row:
        raise HTTPException(status_code=404, detail="No RE-002 decision for symbol")
    return row


@router.get("/re002/health", response_model=Re002HealthSegment)
def get_re002_health(
    days: int = Query(default=7, ge=1, le=90),
    experiment_id: str | None = Query(default=None, max_length=64),
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> Re002HealthSegment:
    seg = health_segment(
        db,
        window_hours=days * 24,
        experiment_id=(experiment_id or "").strip() or None,
    )
    return Re002HealthSegment(**seg)
