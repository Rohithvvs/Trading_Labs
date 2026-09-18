import pandas as pd
import pytz
import asyncio
import time
from datetime import datetime, date
from ta.trend import EMAIndicator
from ..utils.symbol import canonical_symbol, fyers_symbol
from ..schemas import MarketRegimeResult
from .market_data_service import MarketDataService
from ..config import settings
from ..utils import get_logger

logger = get_logger("app.market_permission")

# Bounded lookbacks — match existing Fyers live fallback (250 bars) for EMA50 semantics.
# VIX only needs latest close + staleness; keep a small window for holidays/gaps.
_NIFTY_BREADTH_LOOKBACK_BARS = 250
_VIX_LOOKBACK_BARS = 60
# Per-symbol DB load budget so pool checkout / pre_ping cannot consume the scan timeout.
_CANDLE_LOAD_TIMEOUT_SEC = 8.0
# Cap concurrent breadth history loads (pool_size=20; leave headroom for the scan).
_BREADTH_LOAD_CONCURRENCY = 4


class MarketPermissionService:
    def __init__(self) -> None:
        self.md_service = MarketDataService()
        # Benchmark stocks representing top liquid equities to measure market breadth
        self.benchmark_symbols = list(settings.fyers_screener_symbols)

    def _to_ist_trading_date(self, val) -> date:
        """
        Normalize datetime representations (strings, Timestamps, naive/aware datetimes)
        into a timezone-naive calendar date representing the trading day in India (Asia/Kolkata).
        """
        if val is None:
            return None

        if isinstance(val, str):
            val = pd.to_datetime(val)

        has_tz = False
        if hasattr(val, "tzinfo") and val.tzinfo is not None:
            has_tz = True
        elif hasattr(val, "tz") and val.tz is not None:
            has_tz = True

        if has_tz:
            tz_kolkata = pytz.timezone("Asia/Kolkata")
            if hasattr(val, "tz_convert"):
                val_ist = val.tz_convert(tz_kolkata)
            else:
                val_ist = val.astimezone(tz_kolkata)
            normalized_date = val_ist.date()
        else:
            if hasattr(val, "date"):
                normalized_date = val.date()
            else:
                normalized_date = pd.to_datetime(val).date()

        return normalized_date

    async def _load_candles(self, symbol: str, is_index: bool = False) -> pd.DataFrame:
        """Load a **bounded** daily history for market-regime inputs.

        Prefer ``load_recent_history`` (LIMIT N) over unbounded ``load_full_history``.
        Each DB attempt is timeout-bounded so a stuck pool checkout cannot hang the scan.

        Signature stays ``(symbol, is_index=False)`` for compatibility with existing tests
        and callers; lookback is selected from the symbol (VIX vs NIFTY/breadth).
        """
        sym_u = str(symbol or "").upper()
        if "VIX" in sym_u:
            lookback_bars = _VIX_LOOKBACK_BARS
        else:
            lookback_bars = _NIFTY_BREADTH_LOOKBACK_BARS

        canon = canonical_symbol(symbol)
        candidates = [canon, fyers_symbol(canon, is_index=is_index)]
        # Deduplicate while preserving order
        seen: set[str] = set()
        variants: list[str] = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                variants.append(c)

        last_exc: Exception | None = None
        for variant in variants:
            try:
                df = await asyncio.wait_for(
                    self.md_service.load_recent_history(variant, "1D", lookback_bars),
                    timeout=_CANDLE_LOAD_TIMEOUT_SEC,
                )
                if df is not None and not df.empty:
                    return df.sort_index()
            except asyncio.TimeoutError:
                logger.warning(
                    "SCAN_VIX_LOAD_TIMEOUT | symbol=%s | variant=%s | lookback=%s | timeout_s=%.1f",
                    symbol,
                    variant,
                    lookback_bars,
                    _CANDLE_LOAD_TIMEOUT_SEC,
                )
                last_exc = TimeoutError(
                    f"candle load timed out for {variant} after {_CANDLE_LOAD_TIMEOUT_SEC:.0f}s"
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                logger.debug(
                    "bounded candle load failed | symbol=%s | variant=%s | err=%s",
                    symbol,
                    variant,
                    exc,
                )

        # Live Fyers fallback (also bounded to lookback_bars) — only if DB empty/timeout.
        try:
            from .fyers_service import FyersService
            from ..schemas import AnalysisMode

            fs = FyersService()
            fyers = fyers_symbol(canon, is_index=is_index)
            points = await asyncio.wait_for(
                fs.fetch_ohlcv(fyers, AnalysisMode.swing, "1D", lookback_bars),
                timeout=_CANDLE_LOAD_TIMEOUT_SEC,
            )
            if points:
                data = [
                    {
                        "timestamp": p.timestamp,
                        "open": p.open,
                        "high": p.high,
                        "low": p.low,
                        "close": p.close,
                        "volume": p.volume,
                    }
                    for p in points
                ]
                df = pd.DataFrame(data).set_index("timestamp")
                return df.sort_index()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Live fallback fetch for index %s failed: %s", symbol, exc)
            last_exc = exc

        if last_exc and "INDIAVIX" in str(symbol).upper():
            logger.warning(
                "SCAN_VIX_LOAD_FAILURE | symbol=%s | error=%s",
                symbol,
                last_exc,
            )
        return pd.DataFrame()

    async def evaluate_market_permission(self, scan_date: datetime) -> MarketRegimeResult:
        """
        Evaluate the broad market permission state (regime) as of a given scan_date cutoff.
        Uses NIFTY 50 trend, VIX volatility regime, and top liquid stock breadth.

        Candle loads are **bounded** (no full-history scans) and timeout-guarded.
        Prefer ``scan_market_context.get_or_build_market_regime`` from scanner code so
        this runs at most once per scan.
        """
        scan_trading_date = self._to_ist_trading_date(scan_date)
        reasons = []
        data_quality_flags = {
            "nifty_data_present": True,
            "nifty_data_fresh": True,
            "vix_data_present": True,
            "vix_data_fresh": True,
            "breadth_data_sufficient": True
        }

        # Initialize defaults
        market_state = "CAUTIOUS"
        trend_state = "UNKNOWN"
        breadth_state = "UNKNOWN"
        volatility_state = "UNKNOWN"
        new_entry_allowed = True
        risk_multiplier = 0.5
        manual_review_flag = False

        try:
            # 1. Evaluate NIFTY 50 Trend
            nifty_df = await self._load_candles("NIFTY50-INDEX", is_index=True)
            if nifty_df.empty:
                data_quality_flags["nifty_data_present"] = False
                reasons.append("NIFTY 50 candles completely missing from database")
                # Safe failure to HIGHRISK/DEFENSIVE
                return MarketRegimeResult(
                    market_state="DEFENSIVE",
                    trend_state="UNKNOWN",
                    breadth_state="UNKNOWN",
                    volatility_state="UNKNOWN",
                    data_quality_flags=data_quality_flags,
                    reasons=reasons,
                    new_entry_allowed=False,
                    risk_multiplier=0.0,
                    manual_review_flag=True
                )

            # Warmup indicator EMA50
            if len(nifty_df) >= 50:
                nifty_df["ema50"] = EMAIndicator(close=nifty_df["close"], window=50).ema_indicator()
            else:
                nifty_df["ema50"] = nifty_df["close"].ewm(span=50, adjust=False).mean()

            # Align Nifty dates and filter up to scan date
            nifty_df["trading_date"] = [self._to_ist_trading_date(ts) for ts in nifty_df.index]
            nifty_filtered = nifty_df[nifty_df["trading_date"] <= scan_trading_date]

            if nifty_filtered.empty:
                data_quality_flags["nifty_data_present"] = False
                reasons.append(f"No NIFTY 50 data available up to trading date {scan_trading_date}")
                return MarketRegimeResult(
                    market_state="DEFENSIVE",
                    trend_state="UNKNOWN",
                    breadth_state="UNKNOWN",
                    volatility_state="UNKNOWN",
                    data_quality_flags=data_quality_flags,
                    reasons=reasons,
                    new_entry_allowed=False,
                    risk_multiplier=0.0,
                    manual_review_flag=True
                )

            latest_nifty_row = nifty_filtered.iloc[-1]
            latest_nifty_date = latest_nifty_row["trading_date"]
            nifty_close = float(latest_nifty_row["close"])
            nifty_ema50 = float(latest_nifty_row["ema50"])

            # Check Freshness (stale if > 5 calendar days old, accounting for market holidays/weekends)
            staleness_days = (scan_trading_date - latest_nifty_date).days
            if staleness_days > 5:
                data_quality_flags["nifty_data_fresh"] = False
                reasons.append(f"NIFTY 50 data is stale. Last available candle was {staleness_days} days ago ({latest_nifty_date})")
            
            # Trend Direction
            if pd.isna(nifty_ema50):
                trend_state = "UNKNOWN"
                reasons.append("NIFTY 50 EMA50 contains NaN (insufficient warmup history)")
            elif nifty_close > nifty_ema50:
                trend_state = "BULLISH"
            else:
                trend_state = "BEARISH"

            # 2. Evaluate Volatility Regime via India VIX (bounded load — latest close only)
            vix_t0 = time.perf_counter()
            logger.info(
                "SCAN_VIX_LOAD_START | symbol=INDIAVIX-INDEX | lookback_bars=%s | scan_date=%s",
                _VIX_LOOKBACK_BARS,
                scan_trading_date,
            )
            vix_df = await self._load_candles("INDIAVIX-INDEX", is_index=True)
            vix_close = None
            if vix_df.empty:
                data_quality_flags["vix_data_present"] = False
                reasons.append("India VIX candles missing from database")
                logger.warning(
                    "SCAN_VIX_LOAD_FAILURE | symbol=INDIAVIX-INDEX | duration_ms=%.0f | reason=empty",
                    (time.perf_counter() - vix_t0) * 1000,
                )
            else:
                vix_df["trading_date"] = [self._to_ist_trading_date(ts) for ts in vix_df.index]
                vix_filtered = vix_df[vix_df["trading_date"] <= scan_trading_date]
                if vix_filtered.empty:
                    data_quality_flags["vix_data_present"] = False
                    reasons.append(f"No India VIX data available up to trading date {scan_trading_date}")
                    logger.warning(
                        "SCAN_VIX_LOAD_FAILURE | symbol=INDIAVIX-INDEX | duration_ms=%.0f | reason=no_rows_upto_scan_date",
                        (time.perf_counter() - vix_t0) * 1000,
                    )
                else:
                    vix_latest_row = vix_filtered.iloc[-1]
                    vix_latest_date = vix_latest_row["trading_date"]
                    vix_staleness = (scan_trading_date - vix_latest_date).days
                    
                    if vix_staleness > 5:  # Align with NIFTY 50 5-day staleness threshold
                        data_quality_flags["vix_data_fresh"] = False
                        reasons.append(f"India VIX data is stale. Last available candle was {vix_staleness} days ago ({vix_latest_date})")
                    else:
                        vix_close = float(vix_latest_row["close"])
                    logger.info(
                        "SCAN_VIX_LOAD_SUCCESS | symbol=INDIAVIX-INDEX | duration_ms=%.0f | "
                        "bars=%s | vix_close=%s | data_source=bounded_db_or_fyers | cache_hit=false",
                        (time.perf_counter() - vix_t0) * 1000,
                        len(vix_df),
                        vix_close,
                    )

            if vix_close is None:
                volatility_state = "UNKNOWN"
            elif vix_close < 18.0:
                volatility_state = "NORMAL"
            elif vix_close < 22.0:
                volatility_state = "ELEVATED"
            elif vix_close < 30.0:
                volatility_state = "HIGH"
            else:
                volatility_state = "EXTREME"

            # 3. Evaluate Breadth Proxy via top liquid screener benchmark stocks (TEMPORARY_ASSUMPTION)
            # Bounded concurrency — never stampede the asyncpg pool with 25 full-history loads.
            breadth_sem = asyncio.Semaphore(_BREADTH_LOAD_CONCURRENCY)

            async def get_bench_status(symbol: str) -> tuple[date, bool] | None:
                async with breadth_sem:
                    try:
                        df = await self._load_candles(symbol)
                        if df.empty or len(df) < 5:
                            return None
                        df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
                        df["trading_date"] = [self._to_ist_trading_date(ts) for ts in df.index]
                        df_filtered = df[df["trading_date"] <= scan_trading_date]
                        if df_filtered.empty:
                            return None
                        row = df_filtered.iloc[-1]
                        return row["trading_date"], float(row["close"]) > float(row["ema50"])
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        return None

            bench_tasks = [get_bench_status(sym) for sym in self.benchmark_symbols]
            bench_results = await asyncio.gather(*bench_tasks)
            valid_results = [res for res in bench_results if res is not None]

            breadth_pct = None
            if len(valid_results) < len(self.benchmark_symbols) * 0.5:
                # If we don't have enough benchmark stock data, mark breadth as UNKNOWN
                data_quality_flags["breadth_data_sufficient"] = False
                reasons.append("Sufficient benchmark stock candles missing for breadth calculation")
            else:
                above_count = sum(1 for _, above in valid_results if above)
                breadth_pct = above_count / len(valid_results)

            if breadth_pct is None:
                breadth_state = "UNKNOWN"
            elif breadth_pct >= 0.50:
                breadth_state = "HEALTHY"
            elif breadth_pct >= 0.30:
                breadth_state = "MIXED"
            else:
                breadth_state = "WEAK"

            # 4. State Decision Matrix
            # DEFENSIVE Rule
            if volatility_state == "EXTREME" or not data_quality_flags["nifty_data_present"] or not data_quality_flags["nifty_data_fresh"]:
                market_state = "DEFENSIVE"
                new_entry_allowed = False
                risk_multiplier = 0.0
                if not data_quality_flags["nifty_data_present"] or not data_quality_flags["nifty_data_fresh"]:
                    reasons.append("System in DEFENSIVE state due to critical market data issues")
                else:
                    reasons.append(f"System in DEFENSIVE state due to extreme volatility (VIX: {vix_close})")

            # HIGHRISK Rule
            elif trend_state == "BEARISH" or volatility_state == "HIGH" or breadth_state == "WEAK":
                market_state = "HIGHRISK"
                new_entry_allowed = False
                risk_multiplier = 0.0
                if trend_state == "BEARISH":
                    reasons.append(f"Market in HIGHRISK: NIFTY 50 trend is bearish (close {nifty_close:.2f} < EMA50 {nifty_ema50:.2f})")
                elif volatility_state == "HIGH":
                    reasons.append(f"Market in HIGHRISK: Volatility is high (VIX: {vix_close})")
                else:
                    reasons.append(f"Market in HIGHRISK: Breadth is weak ({breadth_pct*100:.1f}% stocks above EMA50)")

            # CAUTIOUS Rule
            elif trend_state == "UNKNOWN" or breadth_state == "UNKNOWN" or volatility_state == "UNKNOWN" or volatility_state == "ELEVATED" or breadth_state == "MIXED":
                market_state = "CAUTIOUS"
                new_entry_allowed = True
                risk_multiplier = 0.5
                if volatility_state == "ELEVATED":
                    reasons.append(f"Market in CAUTIOUS: Volatility is elevated (VIX: {vix_close})")
                elif breadth_state == "MIXED":
                    reasons.append(f"Market in CAUTIOUS: Breadth is mixed ({breadth_pct*100:.1f}% stocks above EMA50)")
                else:
                    reasons.append("Market in CAUTIOUS due to missing index/breadth components or warnings")

            # FAVORABLE Rule
            else:
                market_state = "FAVORABLE"
                new_entry_allowed = True
                risk_multiplier = 1.0
                reasons.append("Market FAVORABLE: Trend strong, breadth healthy, and low volatility")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.critical("Error during market permission evaluation: %s", e, exc_info=True)
            market_state = "HIGHRISK"
            new_entry_allowed = False
            risk_multiplier = 0.0
            reasons.append(f"Critical execution failure in permission engine: {e}")

        logger.info(
            "Market Permission Evaluation | state=%s | nifty_trend=%s | breadth=%s | vix=%s | entry_allowed=%s",
            market_state, trend_state, breadth_state, volatility_state, new_entry_allowed
        )

        return MarketRegimeResult(
            market_state=market_state,
            trend_state=trend_state,
            breadth_state=breadth_state,
            volatility_state=volatility_state,
            data_quality_flags=data_quality_flags,
            reasons=reasons,
            new_entry_allowed=new_entry_allowed,
            risk_multiplier=risk_multiplier,
            manual_review_flag=(market_state in ("DEFENSIVE", "HIGHRISK"))
        )
