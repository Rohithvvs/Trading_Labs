import json
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..core.deps import require_feature
from ..models.auth import User
from ..services.latest_scan_service import LatestScanService
from ..services.scanner_cache_service import scanner_cache_service, wants_force_refresh
from ..config.settings import settings
from ..utils import get_logger
from ..observability.scan_diagnostics import log_dashboard_request
from ..observability.metrics import (
    record_scanner_cache_force_refresh,
    record_scanner_cache_hit,
    record_scanner_cache_miss,
    record_unified_latest_fallback,
)

router = APIRouter(prefix="/scanner", tags=["scanner"])
_stats_logger = get_logger("app.routes.scanner.statistics")
logger = get_logger("app.routes.scanner")


CACHE_KEY_SCANNER_LATEST = "scanner:latest:v1"
ENDPOINT_SCANNER_LATEST = "/scanner/latest"


# ---------------------------------------------------------------------------
# Engine-specific statistics helpers
# ---------------------------------------------------------------------------

def _compute_engine_statistics(engine_id: str) -> dict:
    """Compute statistics for a single RE engine from persisted decision rows.

    Uses the most recent multi-symbol cohort scan_run_id so statistics always
    correspond to the latest scanner run for that engine, never mixing runs.

    Returns a dict with a ``status`` key:
      - ``"not_executed"``  – no rows of any kind exist for this engine
      - ``"executed"``      – rows found; metrics computed from actual data
    """
    from ..db.session import SessionLocal
    from ..models.recommendation_engine import RecommendationEngineDecision
    from sqlalchemy import func, desc

    try:
        with SessionLocal() as db:
            # Find the latest cohort scan_run_id for this engine
            decision_count_col = func.count(RecommendationEngineDecision.id).label("decision_count")
            latest_col = func.max(RecommendationEngineDecision.created_at).label("latest_created_at")

            cohort_q = (
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
                .order_by(desc(decision_count_col), desc(latest_col))
                .limit(1)
            )
            cohort_rows = cohort_q.all()

            if not cohort_rows:
                # No rows at all — engine has never been executed
                return {"status": "not_executed", "engine_id": engine_id}

            scan_run_id, total_candidates, scanned_at = cohort_rows[0]

            # Load all decisions for this scan run
            rows = (
                db.query(RecommendationEngineDecision)
                .filter(
                    RecommendationEngineDecision.engine_id == engine_id,
                    RecommendationEngineDecision.scan_run_id == scan_run_id,
                )
                .all()
            )

            # ----------------------------------------------------------------
            # Derive metrics from actual decision rows only.
            # All derivations use stored fields — no re-scoring, no new logic.
            # ----------------------------------------------------------------
            total = len(rows)
            buy_count = 0
            watch_count = 0
            reject_count = 0
            high_confidence = 0
            scores: list[float] = []
            confidences: list[float] = []
            risk_rewards: list[float] = []
            ta_completed = 0
            # "gating passed" = at minimum the evaluation_status is 'success'
            # (i.e. the engine produced a proper BUY/WATCH — not rejected_by_rules
            # due to a missing-data/regime gate before any technical work).
            gating_passed = 0

            for row in rows:
                state = str(row.recommendation_state or "REJECT").strip().upper()
                if state == "BUY":
                    buy_count += 1
                elif state == "WATCH":
                    watch_count += 1
                else:
                    reject_count += 1

                conf = float(row.confidence_score or 0.0)
                # Normalize to 0-1 range if stored as 0-100
                if conf > 1.0:
                    conf = conf / 100.0
                if conf >= 0.7:
                    high_confidence += 1

                # Production score is the engine composite score (0-100)
                prod_score = row.production_score
                if prod_score is not None:
                    try:
                        scores.append(float(prod_score))
                    except (TypeError, ValueError):
                        pass

                confidences.append(conf)

                # Technical analysis completed = technical_analysis is non-empty
                ta = row.technical_analysis
                if ta and isinstance(ta, dict) and ta:
                    ta_completed += 1

                # Gating passed = evaluation reached scoring phase successfully
                ev_status = str(row.evaluation_status or "").lower()
                if ev_status in {"success", "watch", "buy"}:
                    gating_passed += 1
                elif state in {"BUY", "WATCH"}:
                    gating_passed += 1

                # Risk/reward from trade_guidance or risk_profile
                tg = row.trade_guidance or {}
                rp = row.risk_profile or {}
                rr_val = tg.get("risk_reward_ratio") or tg.get("risk_reward") or rp.get("risk_reward")
                if rr_val is not None:
                    try:
                        rr_f = float(rr_val)
                        if rr_f > 0:
                            risk_rewards.append(rr_f)
                    except (TypeError, ValueError):
                        pass

            # ----------------------------------------------------------------
            # Count definitions (engine-independent cohorts after architecture change):
            #   total_candidates  = symbols this engine evaluated (decision rows)
            #   data_valid        = rows with usable TA payload (sufficient OHLCV/tech)
            #   eligibility_matched = data_valid proxy for trend/RS pass-through stage
            #   technical_analysis_completed = non-empty technical_analysis JSON
            #   BUY / WATCH / REJECT = recommendation_state counts
            # Never derive these from Production top-N.
            # ----------------------------------------------------------------
            data_valid = ta_completed if ta_completed > 0 else total
            eligibility_matched = ta_completed

            avg_score = round(sum(scores) / len(scores), 2) if scores else None
            highest_score = round(max(scores), 2) if scores else None
            avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
            avg_rr = round(sum(risk_rewards) / len(risk_rewards), 2) if risk_rewards else None

            gating_pass_rate = round(gating_passed / total * 100, 1) if total else None
            ta_success_rate = round(ta_completed / total * 100, 1) if total else None

            return {
                "status": "executed",
                "engine_id": engine_id,
                "scan_run_id": str(scan_run_id),
                "scanned_at": scanned_at.isoformat() if scanned_at else None,
                # Engine-evaluated population (independent of Production top_n)
                "total_candidates": total,
                "engine_evaluated": total,
                "data_valid": data_valid,
                "eligibility_matched": eligibility_matched,
                "technical_analysis_completed": ta_completed,
                "buy_ideas": buy_count,
                "watch_ideas": watch_count,
                "rejected": reject_count,
                "high_confidence": high_confidence,
                "average_score": avg_score,
                "highest_score": highest_score,
                "average_confidence": avg_confidence,
                "average_risk_reward": avg_rr,
                "gating_pass_rate": gating_pass_rate,
                "technical_analysis_success_rate": ta_success_rate,
            }

    except Exception as exc:
        _stats_logger.warning(
            "Engine statistics computation failed | engine=%s | err=%s", engine_id, exc, exc_info=True
        )
        return {"status": "error", "engine_id": engine_id, "message": str(exc)}


@router.get("/statistics")
async def get_scanner_statistics(
    _: User = Depends(require_feature("advanced_scanner")),
):
    """Consolidated scanner statistics: production + RE-001 + RE-002.

    Production stats come from the latest completed scan in the scan store.
    Engine stats are computed from ``recommendation_engine_decisions`` rows,
    scoped to the latest cohort scan_run_id per engine.

    Distinguishes "not_executed" (engine never ran) from "executed" (engine ran,
    even with 0 BUY results).  Never returns fake/hardcoded values.
    """
    from ..db.scan_store import load_latest_scan

    # ---- Production statistics from scan store ----
    production: dict = {}
    try:
        latest = await load_latest_scan()
        if latest:
            shortlisted = latest.get("shortlisted_symbols") or []
            buy_c = latest.get("buy_candidate_symbols") or []
            watch_c = latest.get("watch_candidate_symbols") or []
            data_valid = latest.get("data_valid_symbols") or []
            eligible = latest.get("eligible_symbols") or []
            production = {
                "available": True,
                "total_scanned": latest.get("scanned_symbols", 0),
                "data_valid": len(data_valid) if isinstance(data_valid, list) else data_valid,
                "trend_matched": len(eligible) if isinstance(eligible, list) else eligible,
                "favorites": len(shortlisted),
                "buy_ideas": len(buy_c),
                "watch_ideas": len(watch_c),
                "rejected": max(len(shortlisted) - len(buy_c) - len(watch_c), 0),
                "scanned_at": (
                    latest.get("last_scan_completed_at")
                    or latest.get("scanned_at")
                    or None
                ),
            }
        else:
            production = {"available": False, "message": "No completed production scan found"}
    except Exception as exc:
        _stats_logger.warning("Production statistics failed | err=%s", exc, exc_info=True)
        production = {"available": False, "message": str(exc)}

    # ---- Engine-specific statistics (run synchronously in thread pool) ----
    import asyncio

    re001_stats, re002_stats = await asyncio.gather(
        asyncio.to_thread(_compute_engine_statistics, "RE-001"),
        asyncio.to_thread(_compute_engine_statistics, "RE-002"),
    )

    # Attach human-readable engine names
    re001_stats["engine_name"] = "Trend Continuation Engine"
    re002_stats["engine_name"] = "Relative Strength Engine"

    # RE-002 uses "relative_strength_matched" instead of "eligibility_matched"
    if "eligibility_matched" in re002_stats:
        re002_stats["relative_strength_matched"] = re002_stats.pop("eligibility_matched")

    return {
        "production": production,
        "engines": {
            "RE-001": re001_stats,
            "RE-002": re002_stats,
        },
    }




@router.get("/results")
async def get_scanner_results_by_engine(
    engine: str = Query(
        default="Production",
        description="Recommendation engine: Production | RE-001 | RE-002 (also production/re001/re002)",
    ),
    force: bool = Query(default=False, description="Force refresh production cache path"),
    _: User = Depends(require_feature("advanced_scanner")),
):
    """Scanner results filtered to a single recommendation engine.

    - Production: latest completed production scan (analysis / ScreenerResponse shape)
    - RE-001 / RE-002: latest multi-symbol lab decision cohort mapped to the same shape

    Does not duplicate stored data — projects existing scans / decisions.
    """
    from ..db.session import SessionLocal
    from ..services.scanner_engine_results import (
        get_scanner_results_for_engine,
        normalize_scanner_engine,
    )

    eng = normalize_scanner_engine(engine)
    try:
        if eng == "Production":
            payload = await get_scanner_results_for_engine(None, eng, force=force)
        else:
            with SessionLocal() as db:
                payload = await get_scanner_results_for_engine(db, eng, force=force)
        return payload
    except Exception as exc:
        logger.exception("GET /scanner/results failed | engine=%s | err=%s", eng, exc)
        return {
            "available": False,
            "recommendation_engine": eng,
            "message": f"Failed to load scanner results for {eng}",
            "shortlisted_symbols": [],
            "buy_candidate_symbols": [],
            "watch_candidate_symbols": [],
            "all_analyzed_stocks": [],
            "scanned_symbols": 0,
        }


@router.get("/latest")
async def get_latest_completed_scan(
    request: Request,
    force: bool = Query(default=False, description="Force refresh cache"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_feature("advanced_scanner")),
):
    import time
    from ..services.diagnostics_service import diagnostics

    start_t = time.perf_counter()
    force_refresh = wants_force_refresh(force, request.headers.get("cache-control"))
    cache_enabled = settings.is_scanner_latest_cache_enabled()

    # Record force once at the route boundary (covers unified + legacy; no double-count).
    if force_refresh and cache_enabled:
        record_scanner_cache_force_refresh(ENDPOINT_SCANNER_LATEST)

    if settings.is_scanner_unified_latest_enabled():
        try:
            service = LatestScanService(db)
            payload, cache_status = await service.get_latest_scan(
                format_type="dashboard",
                force=force_refresh,
                cache_enabled=cache_enabled,
            )
            return Response(
                content=payload,
                media_type="application/json",
                headers={"X-Cache-Status": cache_status},
            )
        except Exception as exc:
            record_unified_latest_fallback(ENDPOINT_SCANNER_LATEST)
            logger.error(
                "Unified GET /scanner/latest failed, falling back to legacy path | err=%s",
                exc,
                exc_info=True,
            )

    async def produce_json() -> str:
        service = LatestScanService(db)
        result = await service.get_latest_completed_scan()
        duration_ms = int((time.perf_counter() - start_t) * 1000)

        if not result:
            diagnostics.record_dashboard_snapshot(
                {
                    "response_time_ms": duration_ms,
                    "snapshot_id": None,
                    "record_count": 0,
                }
            )
            log_dashboard_request(
                scan_id=None,
                endpoint=ENDPOINT_SCANNER_LATEST,
                returned_records=0,
                query_duration_ms=duration_ms,
            )
            empty_json = json.dumps(
                {
                    "message": "No completed scans found",
                    "buy_candidates": [],
                    "watch_candidates": [],
                    "rejected_candidates": [],
                }
            )
            if cache_enabled:
                await scanner_cache_service.set_latest_scan(
                    CACHE_KEY_SCANNER_LATEST, empty_json, ttl_seconds=10
                )
            return empty_json

        record_count = (
            len(result.get("buy_candidates", []))
            + len(result.get("watch_candidates", []))
            + len(result.get("rejected_candidates", []))
        )
        diagnostics.record_dashboard_snapshot(
            {
                "response_time_ms": duration_ms,
                "snapshot_id": result.get("scan_id") or result.get("snapshot_id", "unknown"),
                "record_count": record_count,
            }
        )
        log_dashboard_request(
            scan_id=result.get("scan_id") or result.get("scan_timestamp"),
            endpoint=ENDPOINT_SCANNER_LATEST,
            returned_records=record_count,
            query_duration_ms=duration_ms,
        )
        serialized_payload = json.dumps(result)
        if cache_enabled:
            await scanner_cache_service.set_latest_scan(
                CACHE_KEY_SCANNER_LATEST, serialized_payload
            )
        return serialized_payload

    payload, cache_status = await scanner_cache_service.resolve_latest_scan(
        CACHE_KEY_SCANNER_LATEST,
        produce_json,
        force=force_refresh,
        cache_enabled=cache_enabled,
    )

    if cache_status == "HIT":
        record_scanner_cache_hit(ENDPOINT_SCANNER_LATEST)
        duration_ms = int((time.perf_counter() - start_t) * 1000)
        try:
            parsed = json.loads(payload) if isinstance(payload, str) else {}
        except Exception:
            parsed = {}
        logger.info(
            "Loading latest scan... | endpoint=/scanner/latest | "
            "User ID: n/a | Latest Scan ID: %s | Completed At: %s | "
            "Returned Rows: %s | Cache Hit/Miss: HIT | duration_ms=%d",
            parsed.get("scan_id"),
            parsed.get("last_scan_completed_at") or parsed.get("scan_timestamp"),
            (
                len(parsed.get("buy_candidates") or [])
                + len(parsed.get("watch_candidates") or [])
                + len(parsed.get("rejected_candidates") or [])
            ),
            duration_ms,
        )
        logger.debug("GET /scanner/latest Cache HIT | duration_ms=%d", duration_ms)
    elif cache_status in ("MISS", "FALLBACK"):
        record_scanner_cache_miss(ENDPOINT_SCANNER_LATEST)
        logger.info(
            "Loading latest scan... | endpoint=/scanner/latest | Cache Hit/Miss: %s",
            cache_status,
        )

    return Response(
        content=payload,
        media_type="application/json",
        headers={"X-Cache-Status": cache_status},
    )
