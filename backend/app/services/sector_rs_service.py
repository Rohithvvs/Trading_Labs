"""Sector relative strength overlay (SR-003).

Computes sector_rs_20 = sector_ROC20 - NIFTY50_ROC20 when sector index history is available.
When the static symbol→sector map is incomplete, resolves sector via stocks_master.
When sector index data is unavailable, falls back to stock-vs-NIFTY50 relative strength
(same ROC20 difference formula) so RE-002 and FEAT-007 receive real RS when price data exists.
Never invents RS from technical scores.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytz
from ta.trend import EMAIndicator

from ..schemas import AnalysisMode, FinalRecommendation, SectorOverlayResult
from ..utils import get_logger
from ..utils.symbol import canonical_symbol, fyers_symbol
from .market_data_service import MarketDataService

logger = get_logger("app.sector_rs")

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

        logger.debug("Normalized timestamp %s to India trading date %s", val, normalized_date)
        return normalized_date

    def _lookup_master_sector(self, symbol: str) -> str | None:
        """Resolve sector label from stocks_master (authoritative universe metadata)."""
        try:
            from ..db.session import SessionLocal
            from ..models.stock import StockMaster

            canon = canonical_symbol(symbol)
            candidates = {
                (symbol or "").strip().upper(),
                canon,
                f"{canon}-EQ" if canon else "",
            }
            candidates.discard("")
            db = SessionLocal()
            try:
                for cand in candidates:
                    row = (
                        db.query(StockMaster)
                        .filter(StockMaster.symbol == cand)
                        .first()
                    )
                    if row is None:
                        row = (
                            db.query(StockMaster)
                            .filter(StockMaster.symbol.ilike(cand))
                            .first()
                        )
                    if row and row.sector:
                        return str(row.sector).strip()
            finally:
                db.close()
        except Exception as exc:
            logger.debug("stocks_master sector lookup failed | symbol=%s | err=%s", symbol, exc)
        return None

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

    async def _load_candles(self, md_service: MarketDataService, sym: str, *, is_index: bool) -> pd.DataFrame:
        """Load daily candles for equity or index with Fyers fallbacks."""
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
                df = await md_service.load_full_history(candidate, "1D")
                if df is not None and not df.empty:
                    return df
            except Exception as exc:
                logger.debug("load_full_history failed | sym=%s | err=%s", candidate, exc)
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

    async def evaluate_sector_overlay(
        self,
        symbol: str,
        scan_date: datetime,
        original_recommendation: FinalRecommendation,
    ) -> SectorOverlayResult:
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
                if not sector_df.empty and not nifty_df.empty and len(sector_df) >= 20:
                    sector_df = sector_df.sort_index()
                    sector_df["ema20"] = EMAIndicator(
                        close=sector_df["close"], window=20
                    ).ema_indicator()
                    sector_df["trading_date"] = [
                        self._to_ist_trading_date(ts) for ts in sector_df.index
                    ]
                    nifty_work = nifty_df.sort_index().copy()
                    nifty_work["trading_date"] = [
                        self._to_ist_trading_date(ts) for ts in nifty_work.index
                    ]
                    merged = pd.merge(
                        sector_df[["trading_date", "close", "ema20"]],
                        nifty_work[["trading_date", "close"]],
                        on="trading_date",
                        suffixes=("_sector", "_nifty"),
                    ).sort_values("trading_date")
                    scan_trading_date = self._to_ist_trading_date(scan_date)
                    if scan_trading_date is not None:
                        merged = merged[merged["trading_date"] <= scan_trading_date]
                    if len(merged) >= 21:
                        sector_close_t = float(merged["close_sector"].iloc[-1])
                        sector_ema20_t = float(merged["ema20"].iloc[-1])
                        sector_close_t_minus_20 = float(merged["close_sector"].iloc[-21])
                        nifty50_close_t = float(merged["close_nifty"].iloc[-1])
                        nifty50_close_t_minus_20 = float(merged["close_nifty"].iloc[-21])
                        if not any(
                            pd.isna(x)
                            for x in (
                                sector_close_t,
                                sector_ema20_t,
                                sector_close_t_minus_20,
                                nifty50_close_t,
                                nifty50_close_t_minus_20,
                            )
                        ) and min(
                            sector_close_t,
                            sector_close_t_minus_20,
                            nifty50_close_t,
                            nifty50_close_t_minus_20,
                        ) > 0:
                            roc20_sector = (
                                (sector_close_t / sector_close_t_minus_20) - 1
                            ) * 100
                            roc20_nifty50 = (
                                (nifty50_close_t / nifty50_close_t_minus_20) - 1
                            ) * 100
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

            # --- Path B: stock vs NIFTY50 relative strength (real price RS, not invented) ---
            if not nifty_df.empty:
                stock_df = await self._load_candles(md_service, symbol, is_index=False)
                rs_pack = self._roc20_diff(stock_df, nifty_df, scan_date)
                if rs_pack is not None:
                    roc_stock, roc_nifty, rs_diff = rs_pack
                    result.sector_roc20 = round(roc_stock, 2)
                    result.nifty50_roc20 = round(roc_nifty, 2)
                    result.sector_rs_20 = round(rs_diff, 2)
                    # Preserve sector map when known; else annotate market RS source
                    if not result.mapped_sector:
                        result.mapped_sector = "NIFTY50-INDEX"
                    result.sector_filter_status = (
                        "STRENGTH" if rs_diff >= 0 else "WEAK"
                    )
                    result.feat007_abstained_reason = None
                    if rs_diff < 0:
                        result.downgrade_triggered = True
                        result.downgrade_reason = (
                            f"Stock underperforming NIFTY50 on 20d ROC "
                            f"(RS: {result.sector_rs_20:.2f}%)"
                        )
                    logger.info(
                        "SR-003 market RS fallback | symbol=%s | sector_rs_20=%.2f | "
                        "stock_roc20=%.2f | nifty_roc20=%.2f | mapped_sector=%s",
                        symbol,
                        result.sector_rs_20,
                        roc_stock,
                        roc_nifty,
                        result.mapped_sector,
                    )
                    return result

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
