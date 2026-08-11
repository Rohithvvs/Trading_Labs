"""RE-002 technical calculation layer (Relative Strength).

Single source of truth for CRS / CRS SMA21 / slope / relative breakout,
stock RSI14, RVOL, benchmark RSI14, ATR14 stop, and earnings proximity.

Decision logic is NOT owned here (next phase). This module only computes
and packages technical values for the engine + Technicals tab.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
import ta

from ...config.settings import settings

logger = logging.getLogger("app.re002")

# ---------------------------------------------------------------------------
# Approved RE-002 technical parameters (not tunable in this task)
# ---------------------------------------------------------------------------
CRS_SMA_PERIOD = 21
CRS_SLOPE_LAG = 3
STOCK_RSI_PERIOD = 14
STOCK_RSI_LOWER = 50.0
STOCK_RSI_UPPER = 70.0
VOLUME_SMA_PERIOD = 20
RVOL_THRESHOLD = 1.2
BENCHMARK_RSI_PERIOD = 14
BENCHMARK_RSI_THRESHOLD = 40.0
ATR_PERIOD = 14
ATR_STOP_MULT = 2.0
EARNINGS_BLACKOUT_SESSIONS = 7
# Need SMA21 at t and at t-3 → at least 21 + 3 aligned CRS points
MIN_ALIGNED_SESSIONS = CRS_SMA_PERIOD + CRS_SLOPE_LAG  # 24
DEFAULT_BENCHMARK_SYMBOL = "NIFTY500"


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _to_session_date(val: Any) -> date | None:
    """Normalize timestamp/date to a calendar trading session date (no TZ invent)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        # Prefer IST calendar day when tz-aware; else use date as stored
        try:
            if val.tzinfo is not None:
                from zoneinfo import ZoneInfo

                return val.astimezone(ZoneInfo("Asia/Kolkata")).date()
        except Exception:
            pass
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, pd.Timestamp):
        try:
            if val.tzinfo is not None:
                from zoneinfo import ZoneInfo

                return val.tz_convert("Asia/Kolkata").date()
        except Exception:
            pass
        return val.date()
    # int index fallback (tests) — not a real session
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return None
    try:
        ts = pd.to_datetime(val, utc=False)
        if getattr(ts, "tzinfo", None) is not None:
            from zoneinfo import ZoneInfo

            return ts.tz_convert("Asia/Kolkata").date()
        return ts.date()
    except Exception:
        return None


def candles_to_ohlcv_df(candles: list[Any], *, label: str = "stock") -> pd.DataFrame:
    """Convert candle objects/dicts to sorted OHLCV frame with session_date.

    Drops rows without a valid session date. Dedupes by session (keep last).
    Does not invent prices.
    """
    rows: list[dict[str, Any]] = []
    for i, c in enumerate(candles or []):
        try:
            ts = _field(c, "timestamp", _field(c, "trade_date", i))
            session = _to_session_date(ts)
            if session is None and isinstance(ts, (int, float)):
                # Synthetic ordered bars (unit tests without real dates):
                # map ordinal index to a monotonic pseudo-session via epoch days.
                session = date.fromordinal(date(1970, 1, 1).toordinal() + int(ts))
            if session is None:
                continue
            rows.append(
                {
                    "session_date": session,
                    "timestamp": ts,
                    "open": float(_field(c, "open")),
                    "high": float(_field(c, "high")),
                    "low": float(_field(c, "low")),
                    "close": float(_field(c, "close")),
                    "volume": float(_field(c, "volume") or 0),
                }
            )
        except (TypeError, ValueError):
            continue
    if not rows:
        return pd.DataFrame(
            columns=["session_date", "timestamp", "open", "high", "low", "close", "volume"]
        )
    df = pd.DataFrame(rows)
    df = df.sort_values("session_date").drop_duplicates(subset=["session_date"], keep="last")
    df = df.reset_index(drop=True)
    return df


def align_stock_benchmark(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
) -> pd.DataFrame:
    """Inner-join stock and benchmark on session_date (same trading session only).

    No forward-fill of benchmark prices. Missing sessions are dropped, not invented.
    """
    if stock_df.empty or bench_df.empty:
        return pd.DataFrame()
    s = stock_df.rename(
        columns={
            "open": "stock_open",
            "high": "stock_high",
            "low": "stock_low",
            "close": "stock_close",
            "volume": "stock_volume",
        }
    )
    b = bench_df.rename(
        columns={
            "open": "bench_open",
            "high": "bench_high",
            "low": "bench_low",
            "close": "bench_close",
            "volume": "bench_volume",
        }
    )
    keep_s = ["session_date", "stock_open", "stock_high", "stock_low", "stock_close", "stock_volume"]
    keep_b = ["session_date", "bench_open", "bench_high", "bench_low", "bench_close", "bench_volume"]
    merged = pd.merge(s[keep_s], b[keep_b], on="session_date", how="inner")
    merged = merged.sort_values("session_date").reset_index(drop=True)
    # Drop non-positive closes (invalid ratio)
    merged = merged[(merged["stock_close"] > 0) & (merged["bench_close"] > 0)]
    return merged.reset_index(drop=True)


def compute_crs_series(aligned: pd.DataFrame) -> pd.Series:
    """CRS_t = Stock_Close_t / Benchmark_Close_t on aligned sessions only."""
    return aligned["stock_close"] / aligned["bench_close"]


def compute_crs_sma21(crs: pd.Series, window: int = CRS_SMA_PERIOD) -> pd.Series:
    """SMA applied to the CRS ratio series (not stock/benchmark closes)."""
    return crs.rolling(window=window, min_periods=window).mean()


def compute_crs_slope_3(
    crs_sma21: pd.Series,
    lag: int = CRS_SLOPE_LAG,
) -> pd.Series:
    """CRS_Slope_t = CRS_SMA21_t - CRS_SMA21_(t-lag). Exact difference, not ROC."""
    return crs_sma21 - crs_sma21.shift(lag)


def relative_breakout_pass(crs: float, crs_sma21: float) -> bool:
    """CRS_t > CRS_SMA21_t."""
    return float(crs) > float(crs_sma21)


def stock_rsi_in_range(rsi: float | None) -> bool:
    """50 <= RSI14 <= 70 inclusive."""
    if rsi is None or not math.isfinite(float(rsi)):
        return False
    v = float(rsi)
    return STOCK_RSI_LOWER <= v <= STOCK_RSI_UPPER


def rvol_pass(rvol: float | None) -> bool:
    """RVOL >= 1.2 inclusive."""
    if rvol is None or not math.isfinite(float(rvol)):
        return False
    return float(rvol) >= RVOL_THRESHOLD


def benchmark_rsi_pass(rsi: float | None) -> bool:
    """Benchmark RSI14 >= 40 inclusive."""
    if rsi is None or not math.isfinite(float(rsi)):
        return False
    return float(rsi) >= BENCHMARK_RSI_THRESHOLD


def atr_stop(entry: float, atr14: float, mult: float = ATR_STOP_MULT) -> float:
    """Initial SL = Entry - (2.0 × ATR14)."""
    return float(entry) - (float(mult) * float(atr14))


def earnings_clear(
    trading_sessions_until: int | None,
    threshold: int = EARNINGS_BLACKOUT_SESSIONS,
) -> bool:
    """True when no earnings within threshold trading sessions (or unknown)."""
    if trading_sessions_until is None:
        return True  # fail-open when unknown (no invent)
    return int(trading_sessions_until) > int(threshold)


def resolve_benchmark_symbol(
    benchmark_symbol: str | None = None,
    sector_overlay: Any | None = None,
) -> str:
    """Default NIFTY500; honor configured strategy/feat004 benchmark when present."""
    if benchmark_symbol and str(benchmark_symbol).strip():
        return str(benchmark_symbol).strip().upper().replace("NSE:", "").replace("-INDEX", "")
    # Prefer strategy store symbol (NIFTY500)
    store = getattr(settings, "strategy_index_store_symbol", None) or DEFAULT_BENCHMARK_SYMBOL
    # feat004 list first token
    raw = getattr(settings, "feat004_benchmark_symbols", None) or store
    first = str(raw).split(",")[0].strip() if raw else store
    return (first or DEFAULT_BENCHMARK_SYMBOL).upper().replace("NSE:", "").replace("-INDEX", "")


def load_benchmark_candles_sync(
    symbol: str | None = None,
    *,
    limit: int = 400,
) -> list[dict[str, Any]]:
    """Best-effort sync load of index OHLCV from strategy IndexOhlcv table."""
    sym = resolve_benchmark_symbol(symbol)
    try:
        from sqlalchemy import select

        from ...db.session import SessionLocal
        from ...models.strategy_market_data import IndexOhlcv

        db = SessionLocal()
        try:
            stmt = (
                select(IndexOhlcv)
                .where(IndexOhlcv.symbol == sym)
                .order_by(IndexOhlcv.trade_date.desc())
                .limit(limit)
            )
            rows = list(db.execute(stmt).scalars().all())
            rows.reverse()  # chronological
            out: list[dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "timestamp": datetime.combine(r.trade_date, datetime.min.time()).replace(
                            tzinfo=timezone.utc
                        ),
                        "trade_date": r.trade_date,
                        "open": float(r.open),
                        "high": float(r.high),
                        "low": float(r.low),
                        "close": float(r.close),
                        "volume": int(r.volume or 0),
                    }
                )
            return out
        finally:
            db.close()
    except Exception as exc:
        logger.debug("RE-002 benchmark load failed | symbol=%s | err=%s", sym, exc)
        return []


def _resolve_earnings_info(
    symbol: str,
    *,
    as_of: datetime | None,
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    if override:
        td = override.get("trading_sessions_until")
        if td is None:
            td = override.get("trading_days_until_earnings")
        clear = override.get("earnings_clear")
        if clear is None:
            clear = earnings_clear(
                int(td) if td is not None else None,
                EARNINGS_BLACKOUT_SESSIONS,
            )
        return {
            "next_earnings_date": override.get("next_earnings_date"),
            "trading_sessions_until": td,
            "threshold": EARNINGS_BLACKOUT_SESSIONS,
            "condition": bool(clear),
            "source": override.get("source") or "override",
        }
    try:
        from ..re001.earnings import lookup_next_earnings

        info = lookup_next_earnings(symbol, as_of=as_of)
        td = info.get("trading_days_until_earnings")
        clear = earnings_clear(
            int(td) if td is not None else None,
            EARNINGS_BLACKOUT_SESSIONS,
        )
        return {
            "next_earnings_date": info.get("next_earnings_date"),
            "trading_sessions_until": td,
            "threshold": EARNINGS_BLACKOUT_SESSIONS,
            "condition": clear,
            "source": info.get("source") or "event_calendar",
        }
    except Exception as exc:
        logger.debug("RE-002 earnings lookup failed (fail-open) | %s", exc)
        return {
            "next_earnings_date": None,
            "trading_sessions_until": None,
            "threshold": EARNINGS_BLACKOUT_SESSIONS,
            "condition": True,
            "source": "error_fail_open",
        }


def _insufficient(
    reason: str,
    *,
    benchmark_symbol: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "engine_id": "RE-002",
        "status": "INSUFFICIENT_HISTORY",
        "error": reason,
        "benchmark": {
            "symbol": benchmark_symbol,
            "close": None,
            "rsi14": None,
            "rsi_threshold": BENCHMARK_RSI_THRESHOLD,
            "rsi_condition": None,
        },
        "relative_strength": {
            "crs": None,
            "crs_sma21": None,
            "crs_slope_3": None,
            "relative_breakout": None,
        },
        "volume": {
            "volume": None,
            "volume_sma20": None,
            "relative_volume": None,
            "threshold": RVOL_THRESHOLD,
            "condition": None,
        },
        "momentum": {
            "stock_rsi14": None,
            "lower_threshold": STOCK_RSI_LOWER,
            "upper_threshold": STOCK_RSI_UPPER,
            "condition": None,
        },
        "volatility": {
            "atr14": None,
            "atr_multiplier": ATR_STOP_MULT,
            "atr_stop": None,
            "entry": None,
        },
        "earnings": {
            "next_earnings_date": None,
            "trading_sessions_until": None,
            "threshold": EARNINGS_BLACKOUT_SESSIONS,
            "condition": None,
        },
        "conditions": {},
        "baseline": {},  # backward-compatible empty
        "interpretation": {"status": "INSUFFICIENT_HISTORY", "reason": reason},
    }
    if detail:
        payload["detail"] = detail
    return payload


def build_re002_technicals(
    candles: list[Any],
    sector_overlay: dict | Any | None = None,
    market_regime: dict | Any | None = None,
    *,
    benchmark_candles: list[Any] | None = None,
    benchmark_symbol: str | None = None,
    symbol: str | None = None,
    earnings_info: dict[str, Any] | None = None,
    as_of: datetime | None = None,
    load_benchmark_if_missing: bool = True,
) -> dict[str, Any]:
    """Build full RE-002 technical analysis payload (single source of truth).

    Parameters keep backward-compatible positional args used by decision_builder.
    """
    bm_sym = resolve_benchmark_symbol(benchmark_symbol, sector_overlay)

    if not candles:
        return _insufficient("no_stock_candles", benchmark_symbol=bm_sym)

    try:
        stock_df = candles_to_ohlcv_df(candles, label="stock")
        if stock_df.empty:
            return _insufficient("stock_no_valid_sessions", benchmark_symbol=bm_sym)

        bm_candles = list(benchmark_candles or [])
        if not bm_candles and load_benchmark_if_missing:
            bm_candles = load_benchmark_candles_sync(bm_sym)

        if not bm_candles:
            return _insufficient(
                "no_benchmark_candles",
                benchmark_symbol=bm_sym,
                detail={"hint": "Pass benchmark_candles or load IndexOhlcv for NIFTY500"},
            )

        bench_df = candles_to_ohlcv_df(bm_candles, label="benchmark")
        if bench_df.empty:
            return _insufficient("benchmark_no_valid_sessions", benchmark_symbol=bm_sym)

        aligned = align_stock_benchmark(stock_df, bench_df)
        n_aligned = len(aligned)
        if n_aligned < MIN_ALIGNED_SESSIONS:
            return _insufficient(
                "INSUFFICIENT_HISTORY",
                benchmark_symbol=bm_sym,
                detail={
                    "aligned_sessions": n_aligned,
                    "required_min": MIN_ALIGNED_SESSIONS,
                    "stock_sessions": len(stock_df),
                    "benchmark_sessions": len(bench_df),
                },
            )

        # ---- CRS series (look-ahead safe: only through t) ----
        crs = compute_crs_series(aligned)
        crs_sma = compute_crs_sma21(crs)
        crs_slope = compute_crs_slope_3(crs_sma)

        idx = n_aligned - 1
        crs_t = float(crs.iloc[idx])
        sma_t = float(crs_sma.iloc[idx]) if not pd.isna(crs_sma.iloc[idx]) else None
        slope_t = float(crs_slope.iloc[idx]) if not pd.isna(crs_slope.iloc[idx]) else None
        sma_t_lag = (
            float(crs_sma.iloc[idx - CRS_SLOPE_LAG])
            if idx >= CRS_SLOPE_LAG and not pd.isna(crs_sma.iloc[idx - CRS_SLOPE_LAG])
            else None
        )

        if sma_t is None or slope_t is None:
            return _insufficient(
                "crs_sma_or_slope_unavailable",
                benchmark_symbol=bm_sym,
                detail={"aligned_sessions": n_aligned},
            )

        breakout = relative_breakout_pass(crs_t, sma_t)

        stock_close = float(aligned["stock_close"].iloc[idx])
        bench_close = float(aligned["bench_close"].iloc[idx])
        session = aligned["session_date"].iloc[idx]
        session_str = session.isoformat() if hasattr(session, "isoformat") else str(session)

        # ---- Stock RSI14 / ATR14 / Volume on stock series (sorted chronological) ----
        # Use full stock_df for indicators (more history if stock has extra sessions),
        # but require last stock bar session == aligned last session for consistency.
        stock_sorted = stock_df.sort_values("session_date").reset_index(drop=True)
        # Restrict stock indicator series to sessions <= last aligned session (no look-ahead)
        stock_sorted = stock_sorted[stock_sorted["session_date"] <= session].reset_index(drop=True)
        if len(stock_sorted) < max(VOLUME_SMA_PERIOD, ATR_PERIOD + 1, STOCK_RSI_PERIOD + 1):
            return _insufficient(
                "stock_indicator_history_short",
                benchmark_symbol=bm_sym,
                detail={"stock_bars": len(stock_sorted)},
            )

        rsi_s = ta.momentum.rsi(stock_sorted["close"], window=STOCK_RSI_PERIOD)
        atr_s = ta.volatility.average_true_range(
            stock_sorted["high"], stock_sorted["low"], stock_sorted["close"], window=ATR_PERIOD
        )
        vol_sma = stock_sorted["volume"].rolling(window=VOLUME_SMA_PERIOD).mean()

        s_idx = -1
        stock_rsi = float(rsi_s.iloc[s_idx]) if not pd.isna(rsi_s.iloc[s_idx]) else None
        atr14 = float(atr_s.iloc[s_idx]) if not pd.isna(atr_s.iloc[s_idx]) else None
        cur_vol = float(stock_sorted["volume"].iloc[s_idx])
        vol_sma20 = float(vol_sma.iloc[s_idx]) if not pd.isna(vol_sma.iloc[s_idx]) else None
        rvol = (cur_vol / vol_sma20) if vol_sma20 and vol_sma20 > 0 else None

        # ---- Benchmark RSI14 (on benchmark series through same session) ----
        bench_sorted = bench_df.sort_values("session_date").reset_index(drop=True)
        bench_sorted = bench_sorted[bench_sorted["session_date"] <= session].reset_index(drop=True)
        if len(bench_sorted) < BENCHMARK_RSI_PERIOD + 1:
            return _insufficient(
                "benchmark_rsi_history_short",
                benchmark_symbol=bm_sym,
                detail={"benchmark_bars": len(bench_sorted)},
            )
        bench_rsi_s = ta.momentum.rsi(bench_sorted["close"], window=BENCHMARK_RSI_PERIOD)
        bench_rsi = (
            float(bench_rsi_s.iloc[-1]) if not pd.isna(bench_rsi_s.iloc[-1]) else None
        )

        entry = stock_close
        atr_sl = atr_stop(entry, atr14, ATR_STOP_MULT) if atr14 is not None else None

        # ---- Conditions (expose only — decision phase later) ----
        rsi_ok = stock_rsi_in_range(stock_rsi)
        rvol_ok = rvol_pass(rvol)
        bm_rsi_ok = benchmark_rsi_pass(bench_rsi)
        slope_ok = slope_t is not None and float(slope_t) > 0

        earn = _resolve_earnings_info(symbol or "", as_of=as_of, override=earnings_info)
        earn_ok = bool(earn.get("condition"))

        mr = market_regime if isinstance(market_regime, dict) else {}
        if market_regime is not None and not isinstance(market_regime, dict):
            mr = {
                "market_state": _field(market_regime, "market_state"),
            }

        relative_strength = {
            "crs": crs_t,
            "crs_sma21": sma_t,
            "crs_sma21_t_minus_3": sma_t_lag,
            "crs_slope_3": slope_t,
            "relative_breakout": breakout,
            "relative_breakout_rule": "CRS > CRS_SMA21",
            "slope_rule": "CRS_SMA21[t] - CRS_SMA21[t-3] > 0",
            "slope_condition": slope_ok,
        }

        volume_block = {
            "volume": int(cur_vol) if math.isfinite(cur_vol) else None,
            "volume_sma20": vol_sma20,
            "relative_volume": rvol,
            "threshold": RVOL_THRESHOLD,
            "condition": rvol_ok,
        }

        momentum = {
            "stock_rsi14": stock_rsi,
            "lower_threshold": STOCK_RSI_LOWER,
            "upper_threshold": STOCK_RSI_UPPER,
            "condition": rsi_ok,
            "rule": "50 <= RSI14 <= 70",
        }

        volatility = {
            "atr14": atr14,
            "atr_multiplier": ATR_STOP_MULT,
            "atr_stop": atr_sl,
            "entry": entry,
            "rule": "Entry - (2.0 × ATR14)",
        }

        benchmark_block = {
            "symbol": bm_sym,
            "close": bench_close,
            "rsi14": bench_rsi,
            "rsi_threshold": BENCHMARK_RSI_THRESHOLD,
            "rsi_condition": bm_rsi_ok,
            "health_status": "NORMAL" if bm_rsi_ok else "FAIL",
        }

        conditions = {
            "relative_breakout": breakout,
            "crs_slope_positive": slope_ok,
            "stock_rsi_range": rsi_ok,
            "relative_volume": rvol_ok,
            "benchmark_rsi": bm_rsi_ok,
            "earnings_clear": earn_ok,
        }

        # Backward-compatible baseline keys used by older UI fragments
        baseline = {
            "active_benchmark": bm_sym,
            "stock_price": stock_close,
            "benchmark_price": bench_close,
            "crs": crs_t,
            "crs_sma_21": sma_t,
            "crs_sma21": sma_t,
            "crs_3_period_slope": slope_t,
            "crs_slope_3": slope_t,
            "relative_breakout": breakout,
            "stock_rsi_14": stock_rsi,
            "benchmark_rsi_14": bench_rsi,
            "relative_volume": rvol,
            "volume": int(cur_vol) if math.isfinite(cur_vol) else None,
            "volume_sma20": vol_sma20,
            "atr_14": atr14,
            "atr_stop": atr_sl,
            "atr_multiplier": ATR_STOP_MULT,
            "session_date": session_str,
            "market_state": mr.get("market_state") or "UNKNOWN",
            "next_earnings_date": earn.get("next_earnings_date"),
            "trading_sessions_until_earnings": earn.get("trading_sessions_until"),
            "earnings_condition": earn_ok,
        }

        interpretation = {
            "status": "OK",
            "relative_breakout": "PASS" if breakout else "FAIL",
            "crs_slope": "PASS" if slope_ok else "FAIL",
            "stock_rsi": "PASS" if rsi_ok else "FAIL",
            "relative_volume": "PASS" if rvol_ok else "FAIL",
            "benchmark_health": "NORMAL" if bm_rsi_ok else "FAIL",
            "earnings": "PASS" if earn_ok else "FAIL",
            "aligned_sessions": n_aligned,
        }

        return {
            "engine_id": "RE-002",
            "status": "OK",
            "session_date": session_str,
            "aligned_sessions": n_aligned,
            "benchmark": benchmark_block,
            "relative_strength": relative_strength,
            "volume": volume_block,
            "momentum": momentum,
            "volatility": volatility,
            "earnings": earn,
            "conditions": conditions,
            "baseline": baseline,
            "interpretation": interpretation,
        }
    except Exception as exc:
        logger.warning("RE-002 technicals failed | err=%s", exc, exc_info=True)
        return {
            "engine_id": "RE-002",
            "status": "ERROR",
            "error": str(exc),
            "baseline": {},
            "interpretation": {"status": "ERROR", "reason": str(exc)},
        }
