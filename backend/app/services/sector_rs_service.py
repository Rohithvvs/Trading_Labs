"""Sector relative strength overlay (SR-003).

Computes sector_rs_20 = sector_ROC20 - NIFTY50_ROC20 when sector index history is available.
When the static symbol→sector map is incomplete, resolves sector via stocks_master.
When sector index data is unavailable, falls back to stock-vs-NIFTY50 relative strength
(same ROC20 difference formula) so the sector overlay receives real RS when price data exists.
Never invents RS from technical scores.

Batch path MUST use ``evaluate_sector_overlays_batch`` so NIFTY50 and each
sector index are loaded once — per-symbol ``evaluate_sector_overlay`` reloads those series
and can push a ~700-symbol scan past the 600s hard timeout.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pytz
from ta.trend import EMAIndicator

from ..schemas import (
    AnalysisMode,
    FinalRecommendation,
    RecommendationReasoning,
    SectorOverlayResult,
)
from ..utils import get_logger
from ..utils.symbol import canonical_symbol, fyers_symbol
from .market_data_service import MarketDataService

logger = get_logger("app.sector_rs")

# Bounded lookback for ROC20 / EMA20 (full multi-year history is unnecessary and slow).
_RS_LOOKBACK_BARS = 260

# stocks_master.sector (and close variants) → Fyers sector index used by SR-003
_SECTOR_NAME_TO_INDEX: dict[str, str] = {
    "information technology": "NSE:NIFTYIT-INDEX",
    "it": "NSE:NIFTYIT-INDEX",
    "financial services": "NSE:NIFTYBANK-INDEX",  # bank index is available; fin-service ticker often invalid
    "banking": "NSE:NIFTYBANK-INDEX",
    "banks": "NSE:NIFTYBANK-INDEX",
    "healthcare": "NSE:NIFTYPHARMA-INDEX",
    "pharma": "NSE:NIFTYPHARMA-INDEX",
    "pharmaceuticals": "NSE:NIFTYPHARMA-INDEX",
    "automobile and auto components": "NSE:NIFTYAUTO-INDEX",
    "automobile": "NSE:NIFTYAUTO-INDEX",
    "auto": "NSE:NIFTYAUTO-INDEX",
    "fast moving consumer goods": "NSE:NIFTYFMCG-INDEX",
    "fmcg": "NSE:NIFTYFMCG-INDEX",
    "consumer durables": "NSE:NIFTYFMCG-INDEX",
    "metals & mining": "NSE:NIFTYMETAL-INDEX",
    "metals and mining": "NSE:NIFTYMETAL-INDEX",
    "metal": "NSE:NIFTYMETAL-INDEX",
    "realty": "NSE:NIFTYREALTY-INDEX",
    "real estate": "NSE:NIFTYREALTY-INDEX",
    "oil gas & consumable fuels": "NSE:NIFTYENERGY-INDEX",
    "oil gas and consumable fuels": "NSE:NIFTYENERGY-INDEX",
    "energy": "NSE:NIFTYENERGY-INDEX",
    "power": "NSE:NIFTYENERGY-INDEX",
    "construction": "NSE:NIFTYINFRA-INDEX",
    "capital goods": "NSE:NIFTYINFRA-INDEX",
    "infrastructure": "NSE:NIFTYINFRA-INDEX",
    "services": "NSE:NIFTYINFRA-INDEX",
    "chemicals": "NSE:NIFTYFMCG-INDEX",
    "consumer services": "NSE:NIFTYFMCG-INDEX",
    "construction materials": "NSE:NIFTYINFRA-INDEX",
    "telecommunication": "NSE:NIFTYIT-INDEX",
    "textiles": "NSE:NIFTYFMCG-INDEX",
    "utilities": "NSE:NIFTYENERGY-INDEX",
}

# Broken / alternate Fyers tickers seen in mapping files
_INDEX_ALIASES: dict[str, list[str]] = {
    "NSE:NIFTYFINSERVICE-INDEX": [
        "NSE:NIFTYBANK-INDEX",  # available fin proxy when fin-service index invalid
    ],
    "NIFTYFINSERVICE-INDEX": [
        "NSE:NIFTYBANK-INDEX",
    ],
}


class SectorRelativeStrengthService:
    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}
        mapping_path = Path(__file__).resolve().parent.parent / "config" / "sector_mappings.json"
        if mapping_path.exists():
            try:
                with open(mapping_path, "r", encoding="utf-8") as f:
                    self.mapping = json.load(f)
                logger.info("Loaded %d sector symbol mappings from %s", len(self.mapping), mapping_path)
            except Exception as e:
                logger.error("Failed to load sector mappings: %s", e)
        else:
            logger.warning("Sector mapping file not found at %s", mapping_path)

    def _to_ist_trading_date(self, val) -> date | None:
        """
        Normalize datetime representations into an India (Asia/Kolkata) trading calendar date.
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

        # Do NOT log per-bar: full-universe batch normalizes thousands of timestamps.
        return normalized_date

    def _lookup_master_sector(self, symbol: str) -> str | None:
        """Resolve sector label from stocks_master (authoritative universe metadata)."""
        bulk = self._bulk_lookup_master_sectors([symbol])
        canon = canonical_symbol(symbol)
        if canon and canon in bulk:
            return bulk[canon]
        raw = (symbol or "").strip().upper()
        return bulk.get(raw)

    def _bulk_lookup_master_sectors(self, symbols: list[str]) -> dict[str, str]:
        """One DB round-trip: map canonical / raw symbols → stocks_master.sector."""
        out: dict[str, str] = {}
        if not symbols:
            return out
        try:
            from ..db.session import SessionLocal
            from ..models.stock import StockMaster

            candidates: set[str] = set()
            for sym in symbols:
                raw = (sym or "").strip().upper()
                if raw:
                    candidates.add(raw)
                canon = canonical_symbol(sym)
                if canon:
                    candidates.add(canon)
                    candidates.add(f"{canon}-EQ")
            candidates.discard("")
            if not candidates:
                return out

            db = SessionLocal()
            try:
                rows = (
                    db.query(StockMaster.symbol, StockMaster.sector)
                    .filter(StockMaster.symbol.in_(list(candidates)))
                    .all()
                )
                by_sym: dict[str, str] = {}
                for row_sym, sector in rows:
                    if not sector:
                        continue
                    s = str(sector).strip()
                    if not s:
                        continue
                    key = str(row_sym or "").strip().upper()
                    if key:
                        by_sym[key] = s

                for sym in symbols:
                    raw = (sym or "").strip().upper()
                    canon = canonical_symbol(sym)
                    sector = None
                    for key in (raw, canon, f"{canon}-EQ" if canon else ""):
                        if key and key in by_sym:
                            sector = by_sym[key]
                            break
                    if sector:
                        if canon:
                            out[canon] = sector
                        if raw:
                            out[raw] = sector
            finally:
                db.close()
        except Exception as exc:
            logger.debug("stocks_master bulk sector lookup failed | err=%s", exc)
        return out

    def resolve_sector_index(self, symbol: str) -> str | None:
        """Resolve Fyers sector index for a stock (static map, then stocks_master sector name)."""
        canon = canonical_symbol(symbol)
        sector_symbol = self.mapping.get(canon)
        if sector_symbol:
            return sector_symbol

        # Static map may use EQ form keys in future
        sector_symbol = self.mapping.get(f"{canon}-EQ")
        if sector_symbol:
            return sector_symbol

        master_sector = self._lookup_master_sector(symbol)
        if not master_sector:
            return None
        key = master_sector.strip().lower()
        return _SECTOR_NAME_TO_INDEX.get(key)

    def _resolve_sector_index_with_master(
        self, symbol: str, master_sectors: dict[str, str]
    ) -> str | None:
        """Resolve sector index using preloaded master_sectors (no extra DB)."""
        canon = canonical_symbol(symbol)
        sector_symbol = self.mapping.get(canon) or self.mapping.get(f"{canon}-EQ")
        if sector_symbol:
            return sector_symbol
        raw = (symbol or "").strip().upper()
        master_sector = master_sectors.get(canon or "") or master_sectors.get(raw)
        if not master_sector:
            return None
        return _SECTOR_NAME_TO_INDEX.get(master_sector.strip().lower())

    async def _load_candles(
        self,
        md_service: MarketDataService,
        sym: str,
        *,
        is_index: bool,
        allow_network: bool = True,
        lookback: int = _RS_LOOKBACK_BARS,
    ) -> pd.DataFrame:
        """Load daily candles for equity or index.

        Prefers bounded DB history. Network (Fyers/yfinance) only when
        ``allow_network=True`` — lab batch path disables this to avoid 700×
        sequential broker/Yahoo calls that exceed the scan timeout.
        """
        candidates: list[str] = []
        raw = (sym or "").strip()
        if not raw:
            return pd.DataFrame()
        candidates.append(raw)
        canon = canonical_symbol(raw)
        if canon and canon != raw:
            candidates.append(canon)
        fy = fyers_symbol(canon or raw, is_index=is_index)
        if fy and fy not in candidates:
            candidates.append(fy)
        # Alias broken index tickers
        for base in list(candidates):
            for alt in _INDEX_ALIASES.get(base, []):
                if alt not in candidates:
                    candidates.append(alt)
            base_canon = canonical_symbol(base)
            for alt in _INDEX_ALIASES.get(base_canon, []):
                if alt not in candidates:
                    candidates.append(alt)

        for candidate in candidates:
            try:
                # Bounded lookback is enough for ROC20/EMA20 and avoids multi-year scans.
                df = await md_service.load_recent_history(candidate, "1D", lookback)
                if df is not None and not df.empty:
                    return df
            except Exception as exc:
                logger.debug("load_recent_history failed | sym=%s | err=%s", candidate, exc)
            try:
                df = await md_service.load_full_history(candidate, "1D")
                if df is not None and not df.empty:
                    if lookback and len(df) > lookback:
                        return df.iloc[-lookback:].copy()
                    return df
            except Exception as exc:
                logger.debug("load_full_history failed | sym=%s | err=%s", candidate, exc)
            if not allow_network:
                continue
            try:
                from .fyers_service import FyersService

                fs = FyersService()
                points = await fs.fetch_ohlcv(candidate, AnalysisMode.swing, "1D", 250)
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
                    return pd.DataFrame(data).set_index("timestamp")
            except Exception as exc:
                logger.debug("Fyers OHLCV fallback failed | sym=%s | err=%s", candidate, exc)
        return pd.DataFrame()

    @staticmethod
    def _ohlcv_points_to_df(points: list[Any] | None) -> pd.DataFrame:
        """Convert lab OHLCVPoint list (or dict-like) to a close series DataFrame."""
        if not points:
            return pd.DataFrame()
        rows: list[dict[str, Any]] = []
        for p in points:
            try:
                ts = getattr(p, "timestamp", None)
                close = getattr(p, "close", None)
                if ts is None and isinstance(p, dict):
                    ts = p.get("timestamp")
                    close = p.get("close")
                if ts is None or close is None:
                    continue
                rows.append(
                    {
                        "timestamp": ts,
                        "open": float(getattr(p, "open", close) if not isinstance(p, dict) else p.get("open", close) or close),
                        "high": float(getattr(p, "high", close) if not isinstance(p, dict) else p.get("high", close) or close),
                        "low": float(getattr(p, "low", close) if not isinstance(p, dict) else p.get("low", close) or close),
                        "close": float(close),
                        "volume": int(
                            getattr(p, "volume", 0)
                            if not isinstance(p, dict)
                            else (p.get("volume") or 0)
                        ),
                    }
                )
            except Exception:
                continue
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        return df

    def _roc20_diff(
        self,
        series_a: pd.DataFrame,
        series_b: pd.DataFrame,
        scan_date: datetime,
    ) -> tuple[float, float, float] | None:
        """Return (roc_a, roc_b, rs_diff) using trading-date aligned closes, or None."""
        if series_a is None or series_b is None or series_a.empty or series_b.empty:
            return None
        a = series_a.sort_index().copy()
        b = series_b.sort_index().copy()
        if "close" not in a.columns or "close" not in b.columns:
            return None
        a["trading_date"] = [self._to_ist_trading_date(ts) for ts in a.index]
        b["trading_date"] = [self._to_ist_trading_date(ts) for ts in b.index]
        merged = pd.merge(
            a[["trading_date", "close"]],
            b[["trading_date", "close"]],
            on="trading_date",
            suffixes=("_a", "_b"),
        ).sort_values("trading_date")
        scan_trading_date = self._to_ist_trading_date(scan_date)
        if scan_trading_date is not None:
            merged = merged[merged["trading_date"] <= scan_trading_date]
        if len(merged) < 21:
            return None
        close_a_t = float(merged["close_a"].iloc[-1])
        close_a_t20 = float(merged["close_a"].iloc[-21])
        close_b_t = float(merged["close_b"].iloc[-1])
        close_b_t20 = float(merged["close_b"].iloc[-21])
        if min(close_a_t, close_a_t20, close_b_t, close_b_t20) <= 0:
            return None
        if any(pd.isna(x) for x in (close_a_t, close_a_t20, close_b_t, close_b_t20)):
            return None
        roc_a = ((close_a_t / close_a_t20) - 1.0) * 100.0
        roc_b = ((close_b_t / close_b_t20) - 1.0) * 100.0
        return roc_a, roc_b, roc_a - roc_b

    def _compute_sector_vs_nifty(
        self,
        sector_df: pd.DataFrame,
        nifty_df: pd.DataFrame,
        scan_date: datetime,
        sector_symbol: str,
        original_action: str,
    ) -> SectorOverlayResult | None:
        """Path A: sector index ROC vs NIFTY50. Returns None if history insufficient."""
        result = SectorOverlayResult(
            mapped_sector=sector_symbol,
            original_action=original_action,
            challenger_action=original_action,
            downgrade_triggered=False,
        )
        if sector_df is None or nifty_df is None or sector_df.empty or nifty_df.empty:
            return None
        if len(sector_df) < 20:
            return None
        sector_work = sector_df.sort_index().copy()
        sector_work["ema20"] = EMAIndicator(
            close=sector_work["close"], window=20
        ).ema_indicator()
        sector_work["trading_date"] = [
            self._to_ist_trading_date(ts) for ts in sector_work.index
        ]
        nifty_work = nifty_df.sort_index().copy()
        nifty_work["trading_date"] = [
            self._to_ist_trading_date(ts) for ts in nifty_work.index
        ]
        merged = pd.merge(
            sector_work[["trading_date", "close", "ema20"]],
            nifty_work[["trading_date", "close"]],
            on="trading_date",
            suffixes=("_sector", "_nifty"),
        ).sort_values("trading_date")
        scan_trading_date = self._to_ist_trading_date(scan_date)
        if scan_trading_date is not None:
            merged = merged[merged["trading_date"] <= scan_trading_date]
        if len(merged) < 21:
            return None
        sector_close_t = float(merged["close_sector"].iloc[-1])
        sector_ema20_t = float(merged["ema20"].iloc[-1])
        sector_close_t_minus_20 = float(merged["close_sector"].iloc[-21])
        nifty50_close_t = float(merged["close_nifty"].iloc[-1])
        nifty50_close_t_minus_20 = float(merged["close_nifty"].iloc[-21])
        if any(
            pd.isna(x)
            for x in (
                sector_close_t,
                sector_ema20_t,
                sector_close_t_minus_20,
                nifty50_close_t,
                nifty50_close_t_minus_20,
            )
        ) or min(
            sector_close_t,
            sector_close_t_minus_20,
            nifty50_close_t,
            nifty50_close_t_minus_20,
        ) <= 0:
            return None
        roc20_sector = ((sector_close_t / sector_close_t_minus_20) - 1) * 100
        roc20_nifty50 = ((nifty50_close_t / nifty50_close_t_minus_20) - 1) * 100
        sector_rs_20 = roc20_sector - roc20_nifty50
        result.sector_close = round(sector_close_t, 2)
        result.sector_ema20 = round(sector_ema20_t, 2)
        result.sector_roc20 = round(roc20_sector, 2)
        result.nifty50_roc20 = round(roc20_nifty50, 2)
        result.sector_rs_20 = round(sector_rs_20, 2)
        is_downtrend = sector_close_t < sector_ema20_t
        is_underperforming = sector_rs_20 < 0
        if is_downtrend and is_underperforming:
            result.sector_filter_status = "WEAK"
            result.downgrade_triggered = True
            result.downgrade_reason = (
                f"Sector {sector_symbol} is weak "
                f"(close {result.sector_close} < EMA20 {result.sector_ema20}) "
                f"and underperforming Nifty (RS: {result.sector_rs_20:.2f}%)"
            )
        else:
            result.sector_filter_status = "STRENGTH"
        return result

    def _compute_stock_vs_nifty(
        self,
        stock_df: pd.DataFrame,
        nifty_df: pd.DataFrame,
        scan_date: datetime,
        mapped_sector: str | None,
        original_action: str,
        *,
        symbol: str | None = None,
        log_fallback: bool = True,
    ) -> SectorOverlayResult | None:
        """Path B: stock vs NIFTY50 ROC differential."""
        rs_pack = self._roc20_diff(stock_df, nifty_df, scan_date)
        if rs_pack is None:
            return None
        roc_stock, roc_nifty, rs_diff = rs_pack
        result = SectorOverlayResult(
            mapped_sector=mapped_sector or "NIFTY50-INDEX",
            original_action=original_action,
            challenger_action=original_action,
            downgrade_triggered=False,
        )
        result.sector_roc20 = round(roc_stock, 2)
        result.nifty50_roc20 = round(roc_nifty, 2)
        result.sector_rs_20 = round(rs_diff, 2)
        result.sector_filter_status = "STRENGTH" if rs_diff >= 0 else "WEAK"
        result.feat007_abstained_reason = None
        if rs_diff < 0:
            result.downgrade_triggered = True
            result.downgrade_reason = (
                f"Stock underperforming NIFTY50 on 20d ROC "
                f"(RS: {result.sector_rs_20:.2f}%)"
            )
        if log_fallback and symbol:
            logger.debug(
                "SR-003 market RS fallback | symbol=%s | sector_rs_20=%.2f | "
                "stock_roc20=%.2f | nifty_roc20=%.2f | mapped_sector=%s",
                symbol,
                result.sector_rs_20,
                roc_stock,
                roc_nifty,
                result.mapped_sector,
            )
        return result

    async def evaluate_sector_overlay(
        self,
        symbol: str,
        scan_date: datetime,
        original_recommendation: FinalRecommendation,
    ) -> SectorOverlayResult:
        """Single-symbol path (Production Top-N / ad-hoc). Prefer batch for lab universe."""
        sector_symbol = self.resolve_sector_index(symbol)

        result = SectorOverlayResult(
            mapped_sector=sector_symbol,
            original_action=original_recommendation.action,
            challenger_action=original_recommendation.action,
            downgrade_triggered=False,
        )

        md_service = MarketDataService()

        try:
            nifty_df = await self._load_candles(md_service, "NIFTY50-INDEX", is_index=True)

            # --- Path A: sector index vs NIFTY50 ---
            if sector_symbol:
                sector_df = await self._load_candles(md_service, sector_symbol, is_index=True)
                path_a = self._compute_sector_vs_nifty(
                    sector_df,
                    nifty_df,
                    scan_date,
                    sector_symbol,
                    original_recommendation.action,
                )
                if path_a is not None:
                    return path_a

            # --- Path B: stock vs NIFTY50 relative strength (real price RS, not invented) ---
            if not nifty_df.empty:
                stock_df = await self._load_candles(md_service, symbol, is_index=False)
                path_b = self._compute_stock_vs_nifty(
                    stock_df,
                    nifty_df,
                    scan_date,
                    sector_symbol,
                    original_recommendation.action,
                    symbol=symbol,
                    log_fallback=True,
                )
                if path_b is not None:
                    if path_b.sector_rs_20 is not None:
                        logger.info(
                            "SR-003 market RS fallback | symbol=%s | sector_rs_20=%.2f | "
                            "stock_roc20=%.2f | nifty_roc20=%.2f | mapped_sector=%s",
                            symbol,
                            path_b.sector_rs_20,
                            path_b.sector_roc20,
                            path_b.nifty50_roc20,
                            path_b.mapped_sector,
                        )
                    return path_b

            # --- Truly unavailable ---
            if not sector_symbol:
                result.sector_filter_status = "UNMAPPED"
                result.feat007_abstained_reason = "no_sector_mapping"
            else:
                result.sector_filter_status = "INSUFFICIENT_HISTORY"
                result.feat007_abstained_reason = "sector_index_unavailable"
            return result

        except Exception as e:
            logger.error("Error evaluating sector overlay: %s", e, exc_info=True)
            result.sector_filter_status = "INSUFFICIENT_HISTORY"
            result.feat007_abstained_reason = "sector_rs_computation_failed"
            return result

    async def evaluate_sector_overlays_batch(
        self,
        symbols: list[str],
        *,
        candles_by_symbol: dict[str, list[Any]] | None = None,
        scan_date: datetime | None = None,
        original_recommendation: FinalRecommendation | None = None,
        progress_callback: Callable[[dict[str, Any]], Any] | None = None,
        allow_network: bool = False,
    ) -> dict[str, SectorOverlayResult]:
        """Compute sector overlays for a full lab universe efficiently.

        Loads NIFTY50 once and each unique sector index once. Uses prefetched
        equity candles for stock-vs-NIFTY fallback. Defaults to DB-only
        (``allow_network=False``) so lab path cannot stall on Fyers/Yahoo.
        """
        t0 = time.perf_counter()
        symbols = [str(s).strip() for s in (symbols or []) if str(s).strip()]
        out: dict[str, SectorOverlayResult] = {}
        if not symbols:
            return out

        if original_recommendation is None:
            original_recommendation = FinalRecommendation(
                action="WATCH",
                confidence=0.5,
                score=50.0,
                reasoning=RecommendationReasoning(
                    bullets=[], risk_factors=[], invalidation_signals=[]
                ),
                trade_plans=[],
                summary="batch sector overlay placeholder",
            )
        action = original_recommendation.action
        default_scan = scan_date or datetime.now(timezone.utc)

        # 1) Bulk sector map (static JSON + one stocks_master query)
        master_sectors = self._bulk_lookup_master_sectors(symbols)
        sector_for_sym: dict[str, str | None] = {}
        unique_sector_indices: set[str] = set()
        for sym in symbols:
            idx = self._resolve_sector_index_with_master(sym, master_sectors)
            sector_for_sym[sym] = idx
            if idx:
                unique_sector_indices.add(idx)

        logger.info(
            "SECTOR_OVERLAY_BATCH_START | symbols=%s | unique_sectors=%s | allow_network=%s",
            len(symbols),
            len(unique_sector_indices),
            allow_network,
        )
        if progress_callback:
            try:
                progress_callback(
                    {
                        "stage": f"Lab sector RS: loading indices ({len(unique_sector_indices) + 1})...",
                        "progress": 89,
                        "heartbeat": True,
                    }
                )
            except Exception:
                pass

        # 2) Load NIFTY50 + unique sector indices once
        md_service = MarketDataService()
        nifty_df = await self._load_candles(
            md_service,
            "NIFTY50-INDEX",
            is_index=True,
            allow_network=allow_network,
        )
        sector_dfs: dict[str, pd.DataFrame] = {}
        for sector_idx in unique_sector_indices:
            sector_dfs[sector_idx] = await self._load_candles(
                md_service,
                sector_idx,
                is_index=True,
                allow_network=allow_network,
            )

        # Pre-compute Path A results per unique sector index (same scan_date for batch)
        path_a_by_sector: dict[str, SectorOverlayResult | None] = {}
        for sector_idx, sdf in sector_dfs.items():
            path_a_by_sector[sector_idx] = self._compute_sector_vs_nifty(
                sdf, nifty_df, default_scan, sector_idx, action
            )

        if progress_callback:
            try:
                progress_callback(
                    {
                        "stage": f"Lab sector RS overlays (0/{len(symbols)})...",
                        "progress": 89,
                        "heartbeat": True,
                    }
                )
            except Exception:
                pass

        # 3) Per-symbol: reuse Path A when mapped; else Path B from prefetched candles
        # Path A is O(unique sectors) already computed; Path B is pure CPU on
        # prefetched equity candles — no per-symbol DB/FYERS.
        candles_by_symbol = candles_by_symbol or {}
        by_canon: dict[str, list[Any]] = {}
        for k, v in candles_by_symbol.items():
            by_canon[canonical_symbol(k)] = v
            by_canon[str(k).strip().upper()] = v

        path_a_hits = 0
        path_b_hits = 0
        unavailable = 0

        for i, sym in enumerate(symbols):
            sector_idx = sector_for_sym.get(sym)
            # Prefer Path A when sector history computed
            if sector_idx and path_a_by_sector.get(sector_idx) is not None:
                # Copy so per-symbol mutations (if any) don't share identity
                base = path_a_by_sector[sector_idx]
                out[sym] = base.model_copy(deep=True) if hasattr(base, "model_copy") else base
                path_a_hits += 1
            else:
                stock_pts = candles_by_symbol.get(sym)
                if not stock_pts:
                    stock_pts = by_canon.get(canonical_symbol(sym)) or by_canon.get(
                        sym.strip().upper()
                    )
                stock_df = self._ohlcv_points_to_df(stock_pts)
                # Per-symbol scan_date from last candle when available
                sym_scan = default_scan
                if stock_pts:
                    try:
                        last_ts = getattr(stock_pts[-1], "timestamp", None)
                        if last_ts is None and isinstance(stock_pts[-1], dict):
                            last_ts = stock_pts[-1].get("timestamp")
                        if last_ts is not None:
                            sym_scan = last_ts
                    except Exception:
                        pass
                path_b = None
                if not nifty_df.empty and not stock_df.empty:
                    path_b = self._compute_stock_vs_nifty(
                        stock_df,
                        nifty_df,
                        sym_scan,
                        sector_idx,
                        action,
                        symbol=sym,
                        log_fallback=False,
                    )
                if path_b is not None:
                    out[sym] = path_b
                    path_b_hits += 1
                else:
                    res = SectorOverlayResult(
                        mapped_sector=sector_idx,
                        original_action=action,
                        challenger_action=action,
                        downgrade_triggered=False,
                    )
                    if not sector_idx:
                        res.sector_filter_status = "UNMAPPED"
                        res.feat007_abstained_reason = "no_sector_mapping"
                    else:
                        res.sector_filter_status = "INSUFFICIENT_HISTORY"
                        res.feat007_abstained_reason = "sector_index_unavailable"
                    out[sym] = res
                    unavailable += 1

            done = i + 1
            if progress_callback and (done % 50 == 0 or done == len(symbols)):
                try:
                    pct = 89 + int(2 * done / max(1, len(symbols)))
                    progress_callback(
                        {
                            "stage": f"Lab sector RS overlays ({done}/{len(symbols)})...",
                            "progress": min(pct, 91),
                            "heartbeat": True,
                            "done": done,
                            "remaining": len(symbols) - done,
                            "total": len(symbols),
                        }
                    )
                    logger.info(
                        "SECTOR_OVERLAY_BATCH_PROGRESS | done=%s | total=%s",
                        done,
                        len(symbols),
                    )
                except Exception:
                    pass

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "SECTOR_OVERLAY_BATCH_COMPLETE | symbols=%s | path_a=%s | path_b=%s | unavailable=%s | "
            "unique_sectors=%s | nifty_bars=%s | duration_ms=%s | allow_network=%s",
            len(symbols),
            path_a_hits,
            path_b_hits,
            unavailable,
            len(unique_sector_indices),
            0 if nifty_df is None or nifty_df.empty else len(nifty_df),
            elapsed_ms,
            allow_network,
        )
        return out
