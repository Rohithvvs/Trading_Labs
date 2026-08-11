"""Independent RE-001 / RE-002 evaluation over the scan universe.

Architectural boundary (engine independence):

  Master Universe → candle acquisition → common data validation
       ├── Production Engine (own top_n shortlist / scoring)
       ├── RE-001 (full STAGE universe input — not top-N, not data_valid-gated)
       └── RE-002 (full STAGE universe input — not top-N, not data_valid-gated)

RE-001 receives the COMPLETE stage universe and performs its OWN data
validation from shared cached OHLCV. The screener ``data_valid`` set is a
diagnostic only (see ``build_lab_input_universe``), never a hard gate.
Symbols below RE-001's own min-bars (20) receive an explicit diagnostic
REJECT decision (``insufficient_history``) so funnel counts stay complete.

Engines share INPUT market data (OHLCV, regime, portfolio snapshot) but never
share Production shortlist / scores / BUY-WATCH decisions as selection gates.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..config.settings import settings
from ..schemas import AnalysisMode, FinalRecommendation, OHLCVPoint, RecommendationReasoning, TechnicalAnalysisResult
from ..utils import safe_int

logger = logging.getLogger("app.independent_lab_universe")

# Bound concurrency for lab symbol evaluation (CPU + DB persist).
_DEFAULT_LAB_CONCURRENCY = 12
# Sector RS is I/O heavy (index candles); keep a separate lower bound.
_DEFAULT_SECTOR_CONCURRENCY = 8
# RE-001 evaluation floor: the engine's own technicals min-bars (technicals.py).
_RE001_MIN_BARS = 20
# Generous per-symbol evaluation wall-clock for the full-universe lab path.
_LAB_RE001_TIMEOUT_S = 30.0
# Batch persistence flush size (one commit per batch, no per-symbol sessions).
_LAB_PERSIST_BATCH_SIZE = 50

# ---------------------------------------------------------------------------
# Dedicated executor for RE-001 CPU evaluation — never shares (or starves) the
# app-wide default asyncio thread pool that the screener/backtest paths use.
# ---------------------------------------------------------------------------
_lab_executor: ThreadPoolExecutor | None = None
_lab_executor_lock = threading.Lock()


def _get_lab_executor() -> ThreadPoolExecutor:
    global _lab_executor
    if _lab_executor is None:
        with _lab_executor_lock:
            if _lab_executor is None:
                _lab_executor = ThreadPoolExecutor(
                    max_workers=_DEFAULT_LAB_CONCURRENCY,
                    thread_name_prefix="re001-lab",
                )
    return _lab_executor


class LabDecisionSink:
    """Thread-safe batch persistence channel for lab RE-001 decisions.

    Decisions are collected in memory and flushed to ``recommendation_engine_decisions``
    in batches (one commit per batch) so a 755-symbol run does not open 755 sessions
    or spawn 755 executor jobs.
    """

    def __init__(self, *, mode: str = "swing", batch_size: int = _LAB_PERSIST_BATCH_SIZE) -> None:
        self._lock = threading.Lock()
        self._decisions: list[Any] = []
        self._mode = mode
        self._batch_size = max(1, int(batch_size))
        self.persisted = 0

    def add(self, decision: Any) -> None:
        with self._lock:
            self._decisions.append(decision)
            if len(self._decisions) >= self._batch_size:
                self._flush_locked()

    def flush(self) -> int:
        with self._lock:
            return self._flush_locked()

    def _flush_locked(self) -> int:
        pending = self._decisions
        self._decisions = []
        if not pending:
            return 0
        from ..db.session import SessionLocal
        from .re001.persistence import persist_decision_batch

        inserted = 0
        try:
            db = SessionLocal()
            try:
                inserted = persist_decision_batch(db, pending, mode=self._mode)
                self.persisted += inserted
                for d in pending:
                    state = str(getattr(d, "recommendation_state", "") or "").upper()
                    if state == "BUY":
                        try:
                            from .auto_paper_trading_service import maybe_auto_paper_from_lab_decision

                            maybe_auto_paper_from_lab_decision(db, d)
                        except Exception as auto_exc:
                            logger.warning(
                                "RE-001 lab auto paper hook failed (ignored) | symbol=%s | err=%s",
                                getattr(d, "symbol", None),
                                auto_exc,
                                exc_info=True,
                            )
            finally:
                db.close()
        except Exception as exc:
            logger.warning(
                "LAB_DECISION_SINK_FLUSH_FAILED | rows=%s | err=%s",
                len(pending),
                exc,
                exc_info=True,
            )
        return inserted


def build_lab_input_universe(
    source_universe: list[str],
    data_valid_symbols: list[str],
) -> dict[str, Any]:
    """Build the RE-001 lab input universe (unit-testable boundary).

    RE-001 receives the COMPLETE stage universe — never Production top-N /
    shortlist / matched candidates. The engine performs its own data validation;
    the screener ``data_valid`` set is only reported as an audit diagnostic.
    """
    source = [str(s).strip() for s in (source_universe or []) if str(s).strip()]
    valid = {str(s).strip() for s in (data_valid_symbols or []) if str(s).strip()}
    missing_from_valid = [s for s in source if s not in valid]
    return {
        "universe": list(source),
        "universe_size": len(source),
        "data_valid_size": len(valid),
        "missing_from_data_valid": len(missing_from_valid),
        "reason": (
            "RE-001 receives the full stage universe; the screener data_valid "
            "set is a diagnostic only. Symbols missing from data_valid are "
            "re-validated by RE-001's own data stage (cached OHLCV)."
        ),
    }


def _empty_reasoning() -> RecommendationReasoning:
    return RecommendationReasoning(bullets=[], risk_factors=[], invalidation_signals=[])


def _placeholder_recommendation() -> FinalRecommendation:
    return FinalRecommendation(
        action="WATCH",
        confidence=0.5,
        score=50.0,
        reasoning=_empty_reasoning(),
        trade_plans=[],
        summary="Independent lab sector-overlay placeholder",
    )


def frames_to_ohlcv_points(
    frames: dict[str, Any],
    symbols: list[str],
    *,
    min_bars: int = 220,
) -> dict[str, list[OHLCVPoint]]:
    """Convert screener DataFrames into OHLCVPoint lists for lab reuse.

    CPU-heavy (iterrows over hundreds of symbols). Prefer
    ``frames_to_ohlcv_points_async`` from async code so the event loop stays free.
    """
    out: dict[str, list[OHLCVPoint]] = {}
    if not frames:
        return out

    # Canonical index so NSE:FOO-EQ finds FOO frames
    by_canonical: dict[str, str] = {}
    for key in frames.keys():
        by_canonical[_canonical(key)] = key

    for sym in symbols:
        df = frames.get(sym)
        if df is None:
            alt = by_canonical.get(_canonical(sym))
            if alt is not None:
                df = frames.get(alt)
        if df is None or getattr(df, "empty", True):
            continue
        try:
            if len(df) < min_bars:
                continue
        except Exception:
            continue
        points = _df_to_ohlcv_points(df, sym)
        if len(points) >= min_bars:
            out[sym] = points
    return out


def _df_to_ohlcv_points(df: Any, symbol: str) -> list[OHLCVPoint]:
    """Convert one DataFrame to OHLCVPoint list (sync, safe for worker threads)."""
    points: list[OHLCVPoint] = []
    try:
        for ts, row in df.iterrows():
            dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            if getattr(dt, "tzinfo", None) is not None:
                dt = dt.replace(tzinfo=None)
            points.append(
                OHLCVPoint(
                    timestamp=dt,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=safe_int(row["volume"], symbol=symbol, field="volume"),
                )
            )
    except Exception as exc:
        logger.debug("frame→OHLCV failed | symbol=%s | err=%s", symbol, exc)
        return []
    return points


async def frames_to_ohlcv_points_async(
    frames: dict[str, Any],
    symbols: list[str],
    *,
    min_bars: int = 220,
) -> dict[str, list[OHLCVPoint]]:
    """Async wrapper — never block the event loop on full-universe frame conversion."""
    if not frames:
        return {}
    return await asyncio.to_thread(
        frames_to_ohlcv_points, frames, symbols, min_bars=min_bars
    )


def _canonical(symbol: str) -> str:
    s = str(symbol or "").strip().upper()
    if s.startswith("NSE:"):
        s = s[4:]
    if s.endswith("-EQ"):
        s = s[:-3]
    return s


def technical_from_screener_row(row: Any, mode: AnalysisMode = AnalysisMode.swing) -> TechnicalAnalysisResult:
    """Build TechnicalAnalysisResult from screener condition row (reuse score, no re-score)."""
    score = 0.0
    signal = "neutral"
    try:
        score = float(getattr(row, "technical_score", None) or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    try:
        signal = str(getattr(row, "technical_signal", None) or "neutral")
    except Exception:
        signal = "neutral"
    indicators: dict[str, float | str | bool] = {}
    for field in (
        "ema_20",
        "ema_50",
        "sma_30",
        "sma_50",
        "sma_100",
        "sma_200",
        "macd",
        "macd_signal",
        "supertrend",
    ):
        try:
            val = getattr(row, field, None)
            if val is not None:
                indicators[field] = float(val)
        except (TypeError, ValueError):
            pass
    return TechnicalAnalysisResult(
        mode=mode,
        signal=signal,
        score=score,
        indicators=indicators,
        summary="Reused from common screener validation stage",
    )


def build_technical_map(
    screener_results: list[Any],
    symbols: list[str],
) -> dict[str, list[TechnicalAnalysisResult]]:
    """Map symbol → [TechnicalAnalysisResult] for lab eligibility floors."""
    by_sym: dict[str, Any] = {}
    for item in screener_results or []:
        sym = str(getattr(item, "symbol", "") or "").strip()
        if sym:
            by_sym[sym] = item
            by_sym[_canonical(sym)] = item

    out: dict[str, list[TechnicalAnalysisResult]] = {}
    for sym in symbols:
        row = by_sym.get(sym) or by_sym.get(_canonical(sym))
        if row is not None:
            out[sym] = [technical_from_screener_row(row)]
        else:
            out[sym] = [
                TechnicalAnalysisResult(
                    mode=AnalysisMode.swing,
                    signal="neutral",
                    score=0.0,
                    indicators={},
                    summary="No screener technical row",
                )
            ]
    return out


async def _load_missing_candles(
    symbols: list[str],
    existing: dict[str, list[OHLCVPoint]],
    *,
    lookback_window: int = 180,
    progress_callback: Any | None = None,
) -> dict[str, list[OHLCVPoint]]:
    """Fill candles from DB/cache for symbols missing screener frames — no triple FYERS fetch."""
    missing = [s for s in symbols if s not in existing or len(existing.get(s) or []) < 220]
    if not missing:
        return existing

    from .market_data_service import MarketDataService

    md = MarketDataService()
    # Bound concurrency + bar count so lab fill cannot exhaust the asyncpg pool
    # (pool_size=20) or load multi-year histories during the scanner path.
    sem = asyncio.Semaphore(8)
    bar_limit = max(int(lookback_window or 180) + 50, 260)
    completed = {"n": 0}
    total_missing = len(missing)

    async def _one(sym: str) -> tuple[str, list[OHLCVPoint] | None]:
        async with sem:
            try:
                try:
                    df = await asyncio.wait_for(
                        md.load_recent_history(sym, "1D", bar_limit),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    logger.debug("lab candle fill timeout | symbol=%s | limit=%s", sym, bar_limit)
                    return sym, None
                if df is None or df.empty or len(df) < 220:
                    return sym, None
                # iterrows on large frames is CPU-bound — keep event loop free for SSE/health.
                points = await asyncio.to_thread(_df_to_ohlcv_points, df, sym)
                if len(points) >= 220:
                    return sym, points
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("lab candle fill failed | symbol=%s | err=%s", sym, exc)
            finally:
                completed["n"] += 1
                done = completed["n"]
                if progress_callback and (done % 10 == 0 or done == total_missing):
                    try:
                        pct = 86 + int(2 * done / max(1, total_missing))
                        progress_callback(
                            {
                                "stage": f"Lab: loading history for missing symbols ({done}/{total_missing})...",
                                "progress": min(pct, 88),
                                "heartbeat": True,
                                "done": done,
                                "remaining": total_missing - done,
                            }
                        )
                    except Exception:
                        pass
            return sym, None

    results = await asyncio.gather(*(_one(s) for s in missing), return_exceptions=False)
    filled = 0
    for sym, pts in results:
        if pts:
            existing[sym] = pts
            filled += 1
    logger.info(
        "LAB_UNIVERSE_CANDLE_FILL | requested_missing=%s | filled=%s | still_missing=%s",
        len(missing),
        filled,
        len(missing) - filled,
    )
    return existing


async def _benchmark_candles_for_re002() -> tuple[list[dict[str, Any]] | None, str | None]:
    """Resolve shared benchmark OHLCV once for the whole lab universe."""
    try:
        from .market_data_service import MarketDataService

        md = MarketDataService()
        for bm in ("NIFTY500-INDEX", "NIFTY50-INDEX", "NIFTY500", "NIFTY50"):
            try:
                try:
                    df = await asyncio.wait_for(
                        md.load_recent_history(bm, "1D", 260),
                        timeout=8.0,
                    )
                except asyncio.TimeoutError:
                    continue
                if df is None or getattr(df, "empty", True) or len(df) < 50:
                    continue
                candles: list[dict[str, Any]] = []
                tmp = df.reset_index()
                ts_col = "timestamp" if "timestamp" in tmp.columns else tmp.columns[0]
                for _, row in tmp.iterrows():
                    candles.append(
                        {
                            "timestamp": row[ts_col],
                            "open": float(row.get("open", row.get("close", 0)) or 0),
                            "high": float(row.get("high", row.get("close", 0)) or 0),
                            "low": float(row.get("low", row.get("close", 0)) or 0),
                            "close": float(row["close"]),
                            "volume": int(row.get("volume") or 0),
                        }
                    )
                if candles:
                    logger.info("LAB_UNIVERSE_BENCHMARK | symbol=%s | bars=%s", bm, len(candles))
                    return candles, bm
            except Exception:
                continue
    except Exception as exc:
        logger.warning("LAB_UNIVERSE_BENCHMARK failed | err=%s", exc)
    return None, None


async def _resolve_sector_overlays(
    symbols: list[str],
    candles_by_symbol: dict[str, list[OHLCVPoint]],
    *,
    concurrency: int = _DEFAULT_SECTOR_CONCURRENCY,  # kept for call-site compat; unused
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Sector overlays for the full lab universe (RE-002 RS prefilter).

    CRITICAL: Must use the batch SR-003 path. The old per-symbol
    ``evaluate_sector_overlay`` reloaded NIFTY50 + sector indices + optional
    Fyers/yfinance for every symbol and caused SCAN_TIMEOUT_ABORT at 600s
    (see logs: stuck in ``_resolve_sector_overlays`` / ``asyncio.gather``).
    """
    from .sector_rs_service import SectorRelativeStrengthService

    del concurrency  # batch path loads each index once; per-symbol concurrency unused
    svc = SectorRelativeStrengthService()
    placeholder = _placeholder_recommendation()

    # Shared scan date from any symbol with candles
    scan_date = datetime.now(timezone.utc)
    for candles in candles_by_symbol.values():
        if candles:
            try:
                ts = candles[-1].timestamp
                if isinstance(ts, datetime):
                    scan_date = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                    break
            except Exception:
                continue

    try:
        out = await svc.evaluate_sector_overlays_batch(
            symbols,
            candles_by_symbol=candles_by_symbol,
            scan_date=scan_date,
            original_recommendation=placeholder,
            progress_callback=progress_callback,
            # Lab path must not fan out Fyers/Yahoo per symbol — DB + prefetched
            # candles only. Missing sector indices fall back to stock-vs-NIFTY.
            allow_network=False,
        )
        return out
    except Exception as exc:
        logger.warning(
            "LAB_SECTOR_OVERLAY_BATCH_FAILED | symbols=%s | err=%s",
            len(symbols),
            exc,
            exc_info=True,
        )
        # Fail-open: empty overlays so RE engines still run without RS filter
        return {sym: None for sym in symbols}


def _preload_earnings_overrides(
    symbols: list[str],
    *,
    as_of: datetime | None = None,
    days_ahead: int = 30,
) -> dict[str, dict[str, Any]]:
    """Bulk-load next EARNINGS for the whole lab universe (ONE event_calendar query).

    Mirrors ``re001.earnings.lookup_next_earnings`` per-symbol semantics; the
    lab path passes the result as ``earnings_info`` overrides to RE-001 so the
    engine never performs per-symbol calendar queries (N+1).
    """
    from .re001.earnings import (
        EARNINGS_BLACKOUT_TRADING_DAYS,
        _as_date,
        trading_days_between,
    )

    as_of = as_of or datetime.now(timezone.utc)
    as_of_d = _as_date(as_of) or date.today()
    canon = {_canonical(s) for s in symbols if _canonical(s)}
    out: dict[str, dict[str, Any]] = {}
    if not canon:
        return out

    try:
        from sqlalchemy import and_, select

        from ..db.session import SessionLocal
        from ..models.event_calendar import EventCalendar

        horizon = as_of_d + timedelta(days=days_ahead)
        db = SessionLocal()
        try:
            stmt = (
                select(EventCalendar)
                .where(
                    and_(
                        EventCalendar.symbol.in_(sorted(canon)),
                        EventCalendar.event_type == "EARNINGS",
                    )
                )
                .order_by(EventCalendar.event_date.asc())
            )
            rows = list(db.execute(stmt).scalars().all())
        finally:
            db.close()

        by_sym: dict[str, Any] = {}
        for row in rows:
            sym = _canonical(str(getattr(row, "symbol", "") or ""))
            if sym not in canon or sym in by_sym:
                continue
            ed = _as_date(getattr(row, "event_date", None))
            if ed is None or not (as_of_d <= ed <= horizon):
                continue
            by_sym[sym] = row

        for sym, row in by_sym.items():
            ed = _as_date(row.event_date)
            td = trading_days_between(as_of_d, ed) if ed else None
            clear = True
            if td is not None and td <= EARNINGS_BLACKOUT_TRADING_DAYS:
                clear = False
            out[sym] = {
                "next_earnings_date": ed.isoformat() if ed else None,
                "trading_days_until_earnings": td,
                "earnings_clear": bool(clear),
                "source": "event_calendar_bulk",
            }
    except Exception as exc:
        logger.debug("RE-001 earnings bulk preload failed (fail-open) | err=%s", exc)
    return out


def _diagnostic_re001_decision(
    *,
    symbol: str,
    scan_run_id: str | None,
    status: str,
    reason: str,
    message: str,
    bars: int,
) -> Any:
    """Emit an explicit RE-001 diagnostic decision (mirrors runner._diagnostic_decision)."""
    from uuid import uuid4

    from .re001.registry import get_re001_registration
    from ..schemas.re001 import Re001DecisionObject

    reg = get_re001_registration()
    return Re001DecisionObject(
        recommendation_id=str(uuid4()),
        engine_id="RE-001",
        engine_version=reg.engine_version,
        market_regime="UNKNOWN",
        recommendation_state="REJECT",
        confidence_score=0.0,
        risk_profile={"mode": "diagnostic"},
        portfolio_decision={"status": "skipped"},
        evidence={
            "diagnostic": status,
            "reason": reason,
            "data": {"bars": bars, "min_bars": _RE001_MIN_BARS},
        },
        explanation=message,
        reason_codes=[reason],
        symbol=symbol,
        scan_run_id=scan_run_id,
        analysis_history_id=None,
        evaluation_status="error",  # literal: success|rejected_by_rules|error|timeout
        timestamp=datetime.now(timezone.utc),
    )


async def run_independent_lab_universe(
    *,
    symbols: list[str],
    source_universe: list[str] | None = None,
    lab_input_universe: dict[str, Any] | None = None,
    screener_results: list[Any] | None = None,
    prefetched_frames: dict[str, Any] | None = None,
    prefetched_candles: dict[str, list[OHLCVPoint]] | None = None,
    market_regime: Any = None,
    mode: str = "swing",
    scan_run_id: str | None = None,
    user_portfolio: dict[str, Any] | None = None,
    production_recommendations: dict[str, Any] | None = None,
    progress_callback: Any | None = None,
    concurrency: int | None = None,
    lookback_window: int = 180,
    max_duration_s: float | None = 240.0,
    run_recommendation_backtest: bool = False,
) -> dict[str, Any]:
    """Evaluate RE-001 and RE-002 on every symbol in ``symbols``.

    Input-universe audit: ``lab_input_universe`` (from
    ``build_lab_input_universe``) is logged so every run documents whether the
    full stage universe or only the screener ``data_valid`` set reached RE-001.
    The engine always performs its OWN data validation — the screener set is a
    diagnostic, never a hard gate.

    Evaluation no longer silently skips symbols with thin candle history:
    - ``< RE-001``'s own min bars (20): an explicit diagnostic REJECT decision
      (``insufficient_history``) is emitted so funnel counts stay complete.
    - ``>= 20`` bars: RE-001 evaluates normally; its bull filter rejects
      symbols with too little history (RE-001's data-validation semantics).

    Returns summary counts and per-symbol decision dicts for UI merge.

    Scanner performance defaults (do not change Product Top-N math):
    - ``run_recommendation_backtest=False`` — skip 3y backtests on the ~700-symbol
      lab path (each backtest can cost 20–45s; Production Top-N still runs them).
    - ``max_duration_s`` — residual wall budget; returns partial decisions so the
      Production scan can still finish SUCCESS instead of SCAN_TIMEOUT_ABORT.
    """
    symbols = [str(s).strip() for s in (symbols or []) if str(s).strip()]
    lab_audit: dict[str, Any] = {}
    if lab_input_universe and isinstance(lab_input_universe, dict):
        lab_audit = dict(lab_input_universe)
    elif source_universe is not None:
        lab_audit = build_lab_input_universe(source_universe, symbols)
    summary: dict[str, Any] = {
        "input_universe": len(symbols),
        "lab_input_universe": lab_audit,
        "candles_ready": 0,
        "re001_evaluated": 0,
        "re002_evaluated": 0,
        "re001_buy": 0,
        "re001_watch": 0,
        "re001_reject": 0,
        "re002_buy": 0,
        "re002_watch": 0,
        "re002_reject": 0,
        "re001_data_valid": 0,
        "re001_trend_matched": 0,
        "re001_favorites": 0,
        "re001_insufficient_history": 0,
        "re001_timeout_count": 0,
        "re001_processing_errors": 0,
        "decisions": {},  # symbol -> {RE-001: dump, RE-002: dump}
        "skipped_no_candles": 0,
        "partial": False,
        "budget_exhausted": False,
    }
    if not symbols:
        return summary

    re001_on = bool(settings.is_re001_active())
    re002_on = bool(settings.is_re002_active())
    if not re001_on and not re002_on:
        logger.info("LAB_UNIVERSE_SKIP | reason=both_engines_inactive | symbols=%s", len(symbols))
        return summary

    # Progress band AFTER Production deep analysis (which ends ~85):
    # 86–88 candle prep, 89–91 sector RS, 92–96 engine eval. Never regress to 70s.
    lab_t0 = time.perf_counter()
    logger.info(
        "LAB_UNIVERSE_START | symbols=%s | source_size=%s | data_valid_size=%s | "
        "missing_from_data_valid=%s | re001=%s | re002=%s | scan_run_id=%s | "
        "note=re001_gets_full_stage_universe_per_decision",
        len(symbols),
        lab_audit.get("universe_size"),
        lab_audit.get("data_valid_size"),
        lab_audit.get("missing_from_data_valid"),
        re001_on,
        re002_on,
        scan_run_id,
    )
    if progress_callback:
        try:
            progress_callback(
                {
                    "stage": (
                        f"Lab engines: preparing validated universe "
                        f"({len(symbols)} symbols, independent of Top Set)..."
                    ),
                    "progress": 86,
                    "heartbeat": True,
                    "lab_universe_size": len(symbols),
                }
            )
        except Exception:
            pass

    # ---- Shared candles (prefer screener frames; fill from DB cache) ----
    candles_by_symbol: dict[str, list[OHLCVPoint]] = {}
    if prefetched_candles:
        candles_by_symbol.update({k: v for k, v in prefetched_candles.items() if v})
    if prefetched_frames:
        from_frames = await frames_to_ohlcv_points_async(prefetched_frames, symbols)
        for sym, pts in from_frames.items():
            if sym not in candles_by_symbol:
                candles_by_symbol[sym] = pts
    candles_by_symbol = await _load_missing_candles(
        symbols, candles_by_symbol, lookback_window=lookback_window, progress_callback=progress_callback
    )
    summary["candles_ready"] = sum(1 for s in symbols if len(candles_by_symbol.get(s) or []) >= 220)
    summary["skipped_no_candles"] = len(symbols) - summary["candles_ready"]

    technical_map = build_technical_map(screener_results or [], symbols)

    # Shared market regime once (scan-scoped; reuses production result when present)
    if market_regime is None:
        try:
            from .scan_market_context import get_or_build_market_regime, get_scan_market_regime

            existing = get_scan_market_regime()
            if existing is not None:
                market_regime = existing
            else:
                sample = next((candles_by_symbol[s] for s in symbols if candles_by_symbol.get(s)), None)
                scan_date = sample[-1].timestamp if sample else datetime.now(timezone.utc)
                market_regime = await get_or_build_market_regime(
                    scan_date,
                    scan_id=scan_run_id,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("LAB_UNIVERSE market_regime failed | err=%s", exc)
            market_regime = None

    # Shared portfolio once
    if user_portfolio is None and (re001_on or re002_on):
        try:
            from .re001.portfolio_loader import load_user_portfolio_dict
            from .re001.scan_context import get_user_id

            uid = get_user_id()
            user_portfolio = await asyncio.wait_for(
                asyncio.to_thread(load_user_portfolio_dict, uid, timeout_s=0),
                timeout=2.0,
            )
        except Exception as exc:
            logger.warning("LAB_UNIVERSE portfolio skipped | err=%s", exc)
            user_portfolio = None

    # Earnings overrides: ONE bulk event_calendar query for the whole universe
    # (per-symbol lookups would be N+1; RE-001 precheck/engine consume the map).
    earnings_map: dict[str, dict[str, Any]] = {}
    try:
        earnings_map = await asyncio.to_thread(
            _preload_earnings_overrides, symbols, as_of=datetime.now(timezone.utc)
        )
        logger.info(
            "LAB_UNIVERSE_EARNINGS_PRELOAD | symbols=%s | loaded=%s",
            len(symbols),
            len(earnings_map),
        )
    except Exception as exc:
        logger.warning("LAB_UNIVERSE_EARNINGS_PRELOAD failed | err=%s", exc)
        earnings_map = {}

    # Shared RE-002 benchmark once
    re002_bm_candles = None
    re002_bm_symbol = None
    if re002_on:
        re002_bm_candles, re002_bm_symbol = await _benchmark_candles_for_re002()

    # Sector overlays (RE-002 hard prefilter; RE-001 soft) — BATCHED, full data_valid.
    if progress_callback:
        try:
            progress_callback(
                {
                    "stage": f"Lab sector RS overlays (0/{len(symbols)})...",
                    "progress": 89,
                    "heartbeat": True,
                    "done": 0,
                    "remaining": len(symbols),
                    "total": len(symbols),
                }
            )
        except Exception:
            pass
    logger.info(
        "SECTOR_OVERLAY_BATCH_START | scan_run_id=%s | symbols=%s | mode=batch_cached",
        scan_run_id,
        len(symbols),
    )
    sector_t0 = time.perf_counter()
    sector_map = await _resolve_sector_overlays(
        symbols, candles_by_symbol, progress_callback=progress_callback
    )
    logger.info(
        "SECTOR_OVERLAY_BATCH_COMPLETE | scan_run_id=%s | symbols=%s | results=%s | duration_ms=%.0f",
        scan_run_id,
        len(symbols),
        len(sector_map),
        (time.perf_counter() - sector_t0) * 1000,
    )

    # Bulk lab: decisions are batch-persisted via the shared sink (one commit per
    # batch) — no per-symbol SessionLocal persist and no per-decision executor job.
    # RE-001 receives the sink; RE-002 keeps in-memory-only behavior.
    decision_sink = LabDecisionSink(mode=mode)
    db_factory = None  # per-decision persist disabled — sink owns persistence

    conc = concurrency or _DEFAULT_LAB_CONCURRENCY
    sem = asyncio.Semaphore(max(1, int(conc)))
    completed = {"n": 0}
    total = len(symbols)
    decisions: dict[str, dict[str, Any]] = {}
    budget_s = float(max_duration_s) if max_duration_s and max_duration_s > 0 else None
    stop_new = {"flag": False}

    def _budget_left() -> float:
        if budget_s is None:
            return 1e9
        return budget_s - (time.perf_counter() - lab_t0)

    def _classify_re001(decision: Any) -> tuple[bool, bool, bool]:
        """Funnel: (data_valid, trend_matched, favorites) from the decision itself."""
        state = str(getattr(decision, "recommendation_state", "") or "").upper()
        evidence = getattr(decision, "evidence", None)
        if isinstance(evidence, dict):
            validation = evidence.get("validation")
        else:
            validation = None
        if not isinstance(validation, dict):
            validation = {}
        ta = getattr(decision, "technical_analysis", None)
        data_ok = (
            validation.get("market_regime") == "pass"
            and isinstance(ta, dict)
            and bool(ta)
            and "error" not in ta
        )
        trend_ok = data_ok and validation.get("bull_stock_filter") == "pass"
        favorites = trend_ok and state in {"BUY", "WATCH"}
        return bool(data_ok), bool(trend_ok), bool(favorites)

    async def _eval_symbol(sym: str) -> None:
        if stop_new["flag"] or _budget_left() <= 1.0:
            stop_new["flag"] = True
            completed["n"] += 1
            return
        async with sem:
            if stop_new["flag"] or _budget_left() <= 0.5:
                stop_new["flag"] = True
                completed["n"] += 1
                return
            candles = candles_by_symbol.get(sym) or []

            tech = technical_map.get(sym) or []
            sector_overlay = sector_map.get(sym)
            prod_rec = None
            if production_recommendations:
                prod_rec = production_recommendations.get(sym) or production_recommendations.get(
                    _canonical(sym)
                )

            entry: dict[str, Any] = {}
            if re001_on and len(candles) < _RE001_MIN_BARS:
                # Thin history: explicit diagnostic REJECT instead of a silent skip
                # so funnel counts cover the whole input universe.
                diag = _diagnostic_re001_decision(
                    symbol=sym,
                    scan_run_id=scan_run_id,
                    status="insufficient_history",
                    reason="insufficient_history",
                    message=(
                        f"RE-001 not evaluated: only {len(candles)} bars available "
                        f"(engine minimum is {_RE001_MIN_BARS})."
                    ),
                    bars=len(candles),
                )
                try:
                    diag_dump = diag.model_dump(mode="json")
                except Exception:
                    diag_dump = {"engine_id": "RE-001", "recommendation_state": "REJECT"}
                entry["RE-001"] = diag_dump
                summary["re001_evaluated"] += 1
                summary["re001_reject"] += 1
                summary["re001_insufficient_history"] += 1
                completed["n"] += 1
                decisions[sym] = entry
                return

            lab_kwargs = dict(
                symbol=sym,
                mode=mode,
                scan_run_id=scan_run_id,
                candles=candles,
                technical_results=tech,
                sentiment_score=0.0,
                fundamental_result=None,
                backtests=[],
                production_recommendation=prod_rec,
                market_regime=market_regime,
                sector_overlay=sector_overlay,
                market_breadth_soft_score=None,
                user_portfolio=user_portfolio,
                risk_settings=None,
                analysis_history_id=None,
                db_session_factory=db_factory,
                run_recommendation_backtest=run_recommendation_backtest,
            )

            tasks = []
            labels = []
            if re001_on:
                from .re001 import run_re001_isolated_async

                tasks.append(
                    run_re001_isolated_async(
                        **lab_kwargs,
                        earnings_info=earnings_map.get(_canonical(sym)),
                        eval_timeout_s=_LAB_RE001_TIMEOUT_S,
                        _executor=_get_lab_executor(),
                        _decision_sink=decision_sink,
                    )
                )
                labels.append("RE-001")
            if re002_on:
                from .re002 import run_re002_isolated_async

                tasks.append(
                    run_re002_isolated_async(
                        **lab_kwargs,
                        benchmark_candles=re002_bm_candles,
                        benchmark_symbol=re002_bm_symbol,
                    )
                )
                labels.append("RE-002")

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for label, res in zip(labels, results):
                if isinstance(res, BaseException) and not isinstance(res, Exception):
                    # Propagate CancelledError so scan timeout tears down cleanly.
                    raise res
                if isinstance(res, Exception):
                    logger.warning(
                        "LAB_UNIVERSE engine error | engine=%s | symbol=%s | err=%s",
                        label,
                        sym,
                        res,
                    )
                    if label == "RE-001":
                        summary["re001_processing_errors"] += 1
                    continue
                if res is None:
                    continue
                try:
                    dump = res.model_dump(mode="json")
                except Exception:
                    dump = {
                        "engine_id": getattr(res, "engine_id", label),
                        "recommendation_state": getattr(res, "recommendation_state", None),
                        "confidence_score": getattr(res, "confidence_score", None),
                        "technical_analysis": getattr(res, "technical_analysis", None),
                    }
                entry[label] = dump
                state = str(getattr(res, "recommendation_state", "") or "").upper()
                if label == "RE-001":
                    summary["re001_evaluated"] += 1
                    if state == "BUY":
                        summary["re001_buy"] += 1
                    elif state == "WATCH":
                        summary["re001_watch"] += 1
                    else:
                        summary["re001_reject"] += 1
                    ev_status = str(getattr(res, "evaluation_status", "") or "")
                    if ev_status == "timeout":
                        summary["re001_timeout_count"] += 1
                    data_ok, trend_ok, fav = _classify_re001(res)
                    if data_ok:
                        summary["re001_data_valid"] += 1
                    if trend_ok:
                        summary["re001_trend_matched"] += 1
                    if fav:
                        summary["re001_favorites"] += 1
                elif label == "RE-002":
                    summary["re002_evaluated"] += 1
                    if state == "BUY":
                        summary["re002_buy"] += 1
                    elif state == "WATCH":
                        summary["re002_watch"] += 1
                    else:
                        summary["re002_reject"] += 1

            if entry:
                decisions[sym] = entry

            completed["n"] += 1
            done = completed["n"]
            if progress_callback and (done % 25 == 0 or done == total):
                try:
                    pct = 92 + int(4 * done / max(1, total))
                    progress_callback(
                        {
                            "stage": f"Lab engines ({done}/{total})...",
                            "progress": min(pct, 96),
                            "current_symbol": sym,
                            "done": done,
                            "remaining": total - done,
                            "total_scoring": total,
                            "heartbeat": True,
                        }
                    )
                except Exception:
                    pass

    # Explicit tasks so parent cancel propagates and we can await teardown.
    eval_tasks = [asyncio.create_task(_eval_symbol(s), name=f"lab_eval:{s}") for s in symbols]
    try:
        if budget_s is not None:
            try:
                await asyncio.wait_for(asyncio.gather(*eval_tasks), timeout=max(5.0, _budget_left()))
            except asyncio.TimeoutError:
                stop_new["flag"] = True
                summary["budget_exhausted"] = True
                summary["partial"] = True
                for t in eval_tasks:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*eval_tasks, return_exceptions=True)
                logger.warning(
                    "LAB_UNIVERSE_BUDGET | scan_run_id=%s | budget_s=%.0f | completed=%s | total=%s",
                    scan_run_id,
                    budget_s,
                    completed["n"],
                    total,
                )
        else:
            await asyncio.gather(*eval_tasks)
    except asyncio.CancelledError:
        for t in eval_tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*eval_tasks, return_exceptions=True)
        raise
    try:
        flushed = decision_sink.flush()
    except Exception as exc:
        logger.warning("LAB_UNIVERSE sink final flush failed | err=%s", exc)
        flushed = 0
    summary["sink_persisted"] = flushed
    summary["decisions"] = decisions
    if stop_new["flag"] and completed["n"] < total:
        summary["partial"] = True

    logger.info(
        "LAB_UNIVERSE_COMPLETE | input=%s | candles_ready=%s | "
        "re001_eval=%s buy=%s watch=%s reject=%s | "
        "funnel data_valid=%s trend_matched=%s favorites=%s insufficient_history=%s "
        "timeouts=%s errors=%s | "
        "re002_eval=%s buy=%s watch=%s reject=%s | sink_persisted=%s | "
        "duration_ms=%.0f | partial=%s | budget_exhausted=%s | backtest=%s | scan_run_id=%s",
        summary["input_universe"],
        summary["candles_ready"],
        summary["re001_evaluated"],
        summary["re001_buy"],
        summary["re001_watch"],
        summary["re001_reject"],
        summary["re001_data_valid"],
        summary["re001_trend_matched"],
        summary["re001_favorites"],
        summary["re001_insufficient_history"],
        summary["re001_timeout_count"],
        summary["re001_processing_errors"],
        summary["re002_evaluated"],
        summary["re002_buy"],
        summary["re002_watch"],
        summary["re002_reject"],
        summary["sink_persisted"],
        (time.perf_counter() - lab_t0) * 1000,
        summary.get("partial"),
        summary.get("budget_exhausted"),
        run_recommendation_backtest,
        scan_run_id,
    )
    return summary
