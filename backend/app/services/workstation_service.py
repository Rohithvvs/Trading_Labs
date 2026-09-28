from __future__ import annotations

import asyncio
import json
import time as time_module
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..config.settings import ROOT_DIR
from ..core.response_cache import cache_get, cache_set, cached_async
from ..models.fyers_token import FyersToken
from ..models.workstation import RiskSettings, SavedScan, ScanHistorySnapshot, WorkstationAlert
from ..schemas.workstation import (
    AlertCreate,
    AlertItem,
    ApiHealthResponse,
    MarketIndexItem,
    MarketOverviewResponse,
    RiskSettingsRequest,
    RiskSettingsResponse,
    SavedScanCreate,
    SavedScanItem,
    ScanComparisonResponse,
    ScanHistoryItem,
    UniverseGroup,
)
from ..services.fyers_service import FyersService
from ..utils import get_logger

logger = get_logger("app.workstation")

_FALLBACK_INDICES: dict[str, str] = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "^BSESN": "SENSEX",
    "^INDIAVIX": "India VIX",
}

_NSE_SYMBOL_TO_FALLBACK = {
    "NSE:NIFTY50-INDEX": "^NSEI",
    "NSE:NIFTYBANK-INDEX": "^NSEBANK",
    "BSE:SENSEX-INDEX": "^BSESN",
    "NSE:INDIAVIX-INDEX": "^INDIAVIX",
}


def _sync_batch_download_yfinance(symbols: list[str]) -> dict[str, dict]:
    try:
        import yfinance as yf
        df = yf.download(symbols, period="5d", interval="1d", progress=False)
        if df is None or df.empty:
            return {}
        results = {}
        for sym in symbols:
            try:
                if "Close" not in df or sym not in df["Close"].columns:
                    continue
                close_series = df["Close"][sym].dropna()
                if close_series.empty:
                    continue
                ltp = round(float(close_series.iloc[-1]), 2)
                if len(close_series) > 1:
                    prev = round(float(close_series.iloc[-2]), 2)
                else:
                    open_series = df["Open"][sym].dropna() if "Open" in df and sym in df["Open"].columns else None
                    prev = round(float(open_series.iloc[-1]), 2) if open_series is not None and not open_series.empty else ltp
                high_series = df["High"][sym].dropna() if "High" in df and sym in df["High"].columns else None
                low_series = df["Low"][sym].dropna() if "Low" in df and sym in df["Low"].columns else None
                high = round(float(high_series.iloc[-1]), 2) if high_series is not None and not high_series.empty else None
                low = round(float(low_series.iloc[-1]), 2) if low_series is not None and not low_series.empty else None
                change = round(ltp - prev, 2)
                change_pct = round(((ltp - prev) / prev) * 100, 2) if prev else 0.0
                sparkline = [round(float(c), 2) for c in close_series.tolist()[-7:]]
                results[sym] = {
                    "ltp": ltp,
                    "change_pct": change_pct,
                    "change": change,
                    "high": high,
                    "low": low,
                    "prev_close": prev,
                    "sparkline": sparkline,
                    "source": "YAHOO_FALLBACK",
                }
            except Exception as e:
                logger.debug("YF_BATCH_EXTRACT_SKIP | symbol=%s | error=%s", sym, str(e))
        return results
    except Exception as exc:
        logger.warning("YF_BATCH_DOWNLOAD_FAILED | error=%s", exc)
        return {}


async def _fetch_batch_indices_yfinance(symbols: list[str]) -> dict[str, dict]:
    return await asyncio.to_thread(_sync_batch_download_yfinance, symbols)


async def _fetch_index_from_yfinance(symbol: str) -> dict | None:
    res = await _fetch_batch_indices_yfinance([symbol])
    return res.get(symbol)


class WorkstationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_universes(self) -> list[UniverseGroup]:
        groups: dict[str, list[str]] = {"NIFTY500": list(settings.nifty500_symbols)}
        csv_path = Path(settings.nifty500_csv_path)
        if not csv_path.is_absolute():
            csv_path = ROOT_DIR / csv_path
        if csv_path.exists():
            from .universe_csv import load_unique_nifty500_csv_rows

            for parsed in load_unique_nifty500_csv_rows(csv_path):
                industry = parsed["industry"] or "Other"
                series = parsed["series"]
                combined = f"{parsed['symbol']}-{series}" if series else parsed["symbol"]
                groups.setdefault(industry, []).append(combined)
        return [
            UniverseGroup(name=name, symbols=list(dict.fromkeys(symbols)), count=len(list(dict.fromkeys(symbols))))
            for name, symbols in sorted(groups.items(), key=lambda item: (item[0] != "NIFTY500", item[0]))
        ]

    async def list_universe_instruments(self, universe: str | None = "NIFTY500") -> list:
        from .universe_service import UniverseService

        return await UniverseService.list_active_instruments(universe)

    async def save_scan(self, payload: SavedScanCreate) -> SavedScanItem:
        existing = await self.db.scalar(select(SavedScan).where(SavedScan.name == payload.name))
        row = existing or SavedScan(name=payload.name)
        row.mode = payload.mode
        row.timeframe = payload.timeframe
        row.lookback_window = payload.lookback_window
        row.top_n = payload.top_n
        row.universe = payload.universe
        row.symbols_json = json.dumps(payload.symbols)
        row.filters_json = json.dumps(payload.filters)
        row.is_active = True
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return self._scan_item(row)

    async def list_saved_scans(self) -> list[SavedScanItem]:
        rows = (await self.db.scalars(select(SavedScan).where(SavedScan.is_active).order_by(SavedScan.updated_at.desc()))).all()
        return [self._scan_item(row) for row in rows]

    async def delete_saved_scan(self, scan_id: int) -> None:
        row = await self.db.scalar(select(SavedScan).where(SavedScan.id == scan_id))
        if row:
            row.is_active = False
            await self.db.commit()

    async def record_scan_history(
        self,
        payload: dict,
        *,
        scan_name: str = "Manual Scan",
        mode: str = "swing",
        timeframe: str = "1d",
        lookback_window: int = 180,
        top_n: int = 20,
        universe: str = "NIFTY500",
    ) -> ScanHistorySnapshot:
        row = ScanHistorySnapshot(
            scan_name=scan_name,
            screener_name=payload.get("screener_name") or "Nifty 500 Swing Scanner",
            mode=mode,
            timeframe=timeframe,
            lookback_window=lookback_window,
            top_n=top_n,
            universe=universe,
            scanned_symbols=int(payload.get("scanned_symbols") or 0),
            shortlisted_count=len(payload.get("shortlisted_symbols") or []),
            buy_count=len(payload.get("buy_candidate_symbols") or []),
            watch_count=len(payload.get("watch_candidate_symbols") or []),
            data_source=payload.get("data_source"),
            payload_json=json.dumps(payload),
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        await self._evaluate_scan_entry_alerts(row)
        return row

    async def list_scan_history(self, limit: int = 20) -> list[ScanHistoryItem]:
        rows = (await self.db.scalars(select(ScanHistorySnapshot).order_by(ScanHistorySnapshot.created_at.desc()).limit(limit))).all()
        return [self._history_item(row) for row in rows]

    async def compare_scan(self, current_id: int) -> ScanComparisonResponse:
        current = await self.db.get(ScanHistorySnapshot, current_id)
        if not current:
            raise ValueError("Scan history item not found.")
        previous = await self.db.scalar(
            select(ScanHistorySnapshot)
            .where(ScanHistorySnapshot.id != current.id)
            .order_by(ScanHistorySnapshot.created_at.desc())
            .limit(1)
        )
        current_set = set(self._history_symbols(current))
        previous_set = set(self._history_symbols(previous)) if previous else set()
        return ScanComparisonResponse(
            current_id=current.id,
            previous_id=previous.id if previous else None,
            new_symbols=sorted(current_set - previous_set),
            removed_symbols=sorted(previous_set - current_set),
            stayed_symbols=sorted(current_set & previous_set),
        )

    async def market_overview(self) -> MarketOverviewResponse:
        cache_key = "workstation_market_overview"
        cached = cache_get(cache_key)
        if cached is not None:
            logger.info("MARKET_OVERVIEW_CACHE_HIT | key=%s", cache_key)
            return MarketOverviewResponse(**cached)

        logger.info("MARKET_OVERVIEW_CACHE_MISS | key=%s | fetching live", cache_key)
        fyers = FyersService.shared()

        indices_defs = [
            ("NSE:NIFTY50-INDEX", "NIFTY 50", "^NSEI"),
            ("NSE:NIFTYBANK-INDEX", "BANK NIFTY", "^NSEBANK"),
            ("BSE:SENSEX-INDEX", "SENSEX", "^BSESN"),
        ]
        vix_def = ("NSE:INDIAVIX-INDEX", "India VIX", "^INDIAVIX")
        sector_defs = [
            ("NSE:NIFTYIT-INDEX", "IT", "^CNXIT"),
            ("NSE:NIFTYBANK-INDEX", "Banking", "^NSEBANK"),
            ("NSE:NIFTYPHARMA-INDEX", "Pharma", "^CNXPHARMA"),
            ("NSE:NIFTYAUTO-INDEX", "Auto", "^CNXAUTO"),
            ("NSE:NIFTYFMCG-INDEX", "FMCG", "^CNXFMCG"),
            ("NSE:NIFTYMETAL-INDEX", "Metals", "^CNXMETAL"),
            ("NSE:NIFTYREALTY-INDEX", "Realty", "^CNXREALTY"),
            ("NSE:NIFTYENERGY-INDEX", "Energy", "^CNXENERGY"),
            ("NSE:NIFTYINFRA-INDEX", "Infra", "^CNXINFRA"),
            ("NSE:NIFTYMEDIA-INDEX", "Media", "^CNXMEDIA"),
        ]

        # 1. Query FYERS in a SINGLE batch request if configured with a valid token
        fyers_results: dict[str, MarketIndexItem] = {}
        if getattr(fyers, "_is_fyers_configured", lambda: False)():
            all_symbols = [sym for sym, _, _ in indices_defs] + [vix_def[0]] + [sym for sym, _, _ in sector_defs]
            labels_map = {sym: label for sym, label, _ in indices_defs}
            labels_map[vix_def[0]] = vix_def[1]
            for sym, label, _ in sector_defs:
                labels_map[sym] = label

            fyers_raw = await fyers.fetch_quotes_batch(all_symbols)
            for sym, q in fyers_raw.items():
                if q.get("ltp") is not None:
                    fyers_results[sym] = MarketIndexItem(
                        symbol=sym,
                        label=labels_map.get(sym, sym),
                        price=q.get("ltp"),
                        change_pct=q.get("change_pct"),
                        change=q.get("change"),
                        high=q.get("high"),
                        low=q.get("low"),
                        prev_close=q.get("prev_close"),
                        source=q.get("source", "FYERS_PRIMARY"),
                    )

        # 2. Identify tickers needing Yahoo Finance
        needed_yf: list[str] = []
        for sym, _, fb in indices_defs:
            if sym not in fyers_results and fb:
                needed_yf.append(fb)
        if vix_def[0] not in fyers_results and vix_def[2]:
            needed_yf.append(vix_def[2])
        for sym, _, fb in sector_defs:
            if sym not in fyers_results and fb:
                needed_yf.append(fb)

        # 3. Batch download ALL required Yahoo Finance tickers in ONE request (~1.0s)
        yf_map = await _fetch_batch_indices_yfinance(list(set(needed_yf))) if needed_yf else {}

        # 4. Build major indices list
        indices: list[MarketIndexItem] = []
        for sym, label, fb_sym in indices_defs:
            if sym in fyers_results:
                indices.append(fyers_results[sym])
            else:
                fb = yf_map.get(fb_sym)
                indices.append(MarketIndexItem(
                    symbol=sym,
                    label=label,
                    price=fb["ltp"] if fb else None,
                    change_pct=fb["change_pct"] if fb else None,
                    change=fb.get("change") if fb else None,
                    high=fb.get("high") if fb else None,
                    low=fb.get("low") if fb else None,
                    prev_close=fb.get("prev_close") if fb else None,
                    sparkline=fb.get("sparkline") if fb else None,
                    source=fb.get("source", "unknown") if fb else "unknown",
                ))

        # 5. Build VIX
        if vix_def[0] in fyers_results:
            vix = fyers_results[vix_def[0]]
        else:
            fb = yf_map.get(vix_def[2])
            vix = MarketIndexItem(
                symbol=vix_def[0],
                label=vix_def[1],
                price=fb["ltp"] if fb else None,
                change_pct=fb["change_pct"] if fb else None,
                change=fb.get("change") if fb else None,
                high=fb.get("high") if fb else None,
                low=fb.get("low") if fb else None,
                prev_close=fb.get("prev_close") if fb else None,
                sparkline=fb.get("sparkline") if fb else None,
                source=fb.get("source", "unknown") if fb else "unknown",
            )

        # 6. Build Sectors
        sectors: list[MarketIndexItem] = []
        for sym, label, fb_sym in sector_defs:
            if sym in fyers_results:
                sectors.append(fyers_results[sym])
            else:
                fb = yf_map.get(fb_sym)
                sectors.append(MarketIndexItem(
                    symbol=sym,
                    label=label,
                    price=fb["ltp"] if fb else None,
                    change_pct=fb["change_pct"] if fb else None,
                    change=fb.get("change") if fb else None,
                    high=fb.get("high") if fb else None,
                    low=fb.get("low") if fb else None,
                    prev_close=fb.get("prev_close") if fb else None,
                    sparkline=fb.get("sparkline") if fb else None,
                    source=fb.get("source", "unknown") if fb else "unknown",
                ))

        # 7. Movers & Breadth from DB (run sequentially on the shared async session)
        movers = await self._movers_from_latest_scan()
        breadth = await self._breadth_from_latest_scan()
        gainers = [m for m in movers if m.change_pct is not None and m.change_pct > 0][:5]
        losers = [m for m in movers if m.change_pct is not None and m.change_pct < 0][-5:][::-1]

        response = MarketOverviewResponse(
            indices=indices,
            vix=vix,
            top_gainers=gainers,
            top_losers=losers,
            sectors=sectors,
            breadth=breadth,
            updated_at=datetime.now(timezone.utc),
        )
        cache_set(cache_key, response.model_dump(mode="json"), ttl_seconds=120.0)
        logger.info("MARKET_OVERVIEW_CACHED | key=%s | ttl=120s", cache_key)
        return response

    async def create_alert(self, payload: AlertCreate) -> AlertItem:
        if payload.alert_type == "PRICE" and not (payload.symbol and payload.condition and payload.target_price):
            raise ValueError("Price alerts require symbol, condition and target_price.")
        if payload.alert_type == "SCAN_ENTRY" and not payload.scan_name:
            raise ValueError("Scan-entry alerts require scan_name.")
        row = WorkstationAlert(
            alert_type=payload.alert_type,
            name=payload.name,
            symbol=payload.symbol.strip().upper() if payload.symbol else None,
            condition=payload.condition,
            target_price=payload.target_price,
            scan_name=payload.scan_name,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return self._alert_item(row)

    async def list_alerts(self) -> list[AlertItem]:
        rows = (await self.db.scalars(select(WorkstationAlert).order_by(WorkstationAlert.created_at.desc()))).all()
        return [self._alert_item(row) for row in rows]

    async def delete_alert(self, alert_id: int) -> None:
        row = await self.db.get(WorkstationAlert, alert_id)
        if row:
            self.db.delete(row)
            await self.db.commit()

    async def get_risk_settings(self) -> RiskSettingsResponse:
        row = await self._risk_row()
        return self._risk_response(row)

    async def update_risk_settings(self, payload: RiskSettingsRequest) -> RiskSettingsResponse:
        row = await self._risk_row()
        row.profile = payload.profile
        row.default_position_size_pct = payload.default_position_size_pct
        row.max_risk_per_trade_pct = payload.max_risk_per_trade_pct
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return self._risk_response(row)

    async def api_health(self) -> ApiHealthResponse:
        fyers = FyersService()
        token = await self.db.scalar(select(FyersToken).where(FyersToken.id == 1))
        services = [
            {
                "name": "FYERS",
                "status": "ok" if fyers.is_fyers_sdk_available() and token and token.access_token else "warning",
                "detail": "SDK and access token available." if token and token.access_token else "Access token missing or SDK unavailable.",
            },
            {
                "name": "News",
                "status": "ok" if settings.news_api_key else "warning",
                "detail": "News API key configured." if settings.news_api_key else "News API key not configured.",
            },
            {
                "name": "LLM",
                "status": "ok" if settings.llm_api_key else "warning",
                "detail": f"{settings.llm_provider} model {settings.llm_model}" if settings.llm_api_key else "LLM key not configured.",
            },
            {
                "name": "Database",
                "status": "ok",
                "detail": "PostgreSQL",
            },
        ]
        return ApiHealthResponse(services=services, database_size_mb=0.0, updated_at=datetime.now(timezone.utc))

    def _scan_item(self, row: SavedScan) -> SavedScanItem:
        return SavedScanItem(
            id=row.id,
            name=row.name,
            mode=row.mode,
            timeframe=row.timeframe,
            lookback_window=row.lookback_window,
            top_n=row.top_n,
            universe=row.universe,
            symbols=json.loads(row.symbols_json or "[]"),
            filters=json.loads(row.filters_json or "{}"),
            is_active=bool(row.is_active),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _history_item(self, row: ScanHistorySnapshot) -> ScanHistoryItem:
        payload = json.loads(row.payload_json)
        return ScanHistoryItem(
            id=row.id,
            scan_name=row.scan_name,
            screener_name=row.screener_name,
            mode=row.mode,
            timeframe=row.timeframe,
            lookback_window=row.lookback_window,
            top_n=row.top_n,
            universe=row.universe,
            scanned_symbols=row.scanned_symbols,
            shortlisted_count=row.shortlisted_count,
            buy_count=row.buy_count,
            watch_count=row.watch_count,
            data_source=row.data_source,
            buy_symbols=payload.get("buy_candidate_symbols") or [],
            watch_symbols=payload.get("watch_candidate_symbols") or [],
            shortlisted_symbols=payload.get("shortlisted_symbols") or [],
            created_at=row.created_at,
        )

    def _history_symbols(self, row: ScanHistorySnapshot | None) -> list[str]:
        if not row:
            return []
        payload = json.loads(row.payload_json)
        return list(payload.get("shortlisted_symbols") or [])

    async def _market_item(self, fyers: FyersService, symbol: str, label: str) -> MarketIndexItem:
        start_t = time_module.time()
        quote = await fyers.fetch_quote(symbol, allow_yfinance=False)
        elapsed = int((time_module.time() - start_t) * 1000)
        price = None
        change_pct = None
        change = None
        high = None
        low = None
        prev_close = None
        source = "unknown"
        if quote:
            price = round(float(quote.get("ltp", 0)), 2) if quote.get("ltp") is not None else None
            change_pct = round(float(quote.get("change_pct", 0)), 2) if quote.get("change_pct") is not None else None
            change = round(float(quote.get("change", 0)), 2) if quote.get("change") is not None else None
            high = round(float(quote.get("high", 0)), 2) if quote.get("high") is not None else None
            low = round(float(quote.get("low", 0)), 2) if quote.get("low") is not None else None
            prev_close = round(float(quote.get("prev_close", 0)), 2) if quote.get("prev_close") is not None else None
            source = quote.get("source", "unknown")
            logger.info("MARKET_ITEM_FETCHED | symbol=%s | label=%s | ltp=%s | source=%s | duration_ms=%s", symbol, label, price, source, elapsed)
        else:
            logger.warning("MARKET_ITEM_FAILED | symbol=%s | label=%s | duration_ms=%s | quote=None", symbol, label, elapsed)
        return MarketIndexItem(
            symbol=symbol,
            label=label,
            price=price,
            change_pct=change_pct,
            change=change,
            high=high,
            low=low,
            prev_close=prev_close,
            source=source,
        )

    async def _movers_from_latest_scan(self) -> list[MarketIndexItem]:
        row = await self.db.scalar(select(ScanHistorySnapshot).order_by(ScanHistorySnapshot.created_at.desc()).limit(1))
        if not row:
            logger.info("MOVERS_NO_SCAN_HISTORY | no snapshots found")
            return []
        payload = json.loads(row.payload_json)
        stocks = payload.get("all_analyzed_stocks") or payload.get("matches") or []
        if not stocks:
            logger.info("MOVERS_EMPTY | scan snapshot has no stock data")
            return []
        has_change = any(item.get("change_pct") is not None for item in stocks)
        if has_change:
            sorted_rows = sorted(stocks, key=lambda item: float(item.get("change_pct") or 0), reverse=True)
            result = [
                MarketIndexItem(
                    symbol=item.get("symbol", ""),
                    label=item.get("symbol", ""),
                    price=float(item.get("close", 0)) if item.get("close") else None,
                    change_pct=float(item.get("change_pct", 0)) if item.get("change_pct") else None,
                    source="scan_data",
                )
                for item in sorted_rows
            ]
            logger.info("MOVERS_FOUND | count=%s | source=scan_data", len(result))
            return result
        sorted_rows = sorted(stocks, key=lambda item: float(item.get("screener_score") or 0), reverse=True)
        result = [
            MarketIndexItem(
                symbol=item.get("symbol", ""),
                label=item.get("symbol", ""),
                price=float(item.get("close", 0)) if item.get("close") else None,
                change_pct=None,
                source="latest_scan_score",
            )
            for item in sorted_rows
        ]
        logger.info("MOVERS_FOUND | count=%s | source=latest_scan_score (no change_pct)", len(result))
        return result

    async def _evaluate_scan_entry_alerts(self, row: ScanHistorySnapshot) -> None:
        current = set(self._history_symbols(row))
        previous = await self.db.scalar(
            select(ScanHistorySnapshot)
            .where(ScanHistorySnapshot.id != row.id)
            .order_by(ScanHistorySnapshot.created_at.desc())
            .limit(1)
        )
        previous_symbols = set(self._history_symbols(previous))
        new_symbols = sorted(current - previous_symbols)
        if not new_symbols:
            return
        alerts = await self.db.scalars(select(WorkstationAlert).where(WorkstationAlert.alert_type == "SCAN_ENTRY", WorkstationAlert.status == "ACTIVE")).all()
        for alert in alerts:
            alert.last_triggered_at = datetime.now(timezone.utc)
            alert.last_message = f"New scan entries: {', '.join(new_symbols[:8])}"
        await self.db.commit()

    async def _risk_row(self) -> RiskSettings:
        row = await self.db.get(RiskSettings, 1)
        if row:
            return row
        row = RiskSettings(id=1)
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    def _risk_response(self, row: RiskSettings) -> RiskSettingsResponse:
        return RiskSettingsResponse(
            id=row.id,
            profile=row.profile,
            default_position_size_pct=row.default_position_size_pct,
            max_risk_per_trade_pct=row.max_risk_per_trade_pct,
            updated_at=row.updated_at,
        )

    def _alert_item(self, row: WorkstationAlert) -> AlertItem:
        return AlertItem(
            id=row.id,
            alert_type=row.alert_type,
            name=row.name,
            symbol=row.symbol,
            condition=row.condition,
            target_price=row.target_price,
            scan_name=row.scan_name,
            status=row.status,
            last_triggered_at=row.last_triggered_at,
            last_message=row.last_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _breadth_from_latest_scan(self) -> dict[str, Any]:
        row = await self.db.scalar(select(ScanHistorySnapshot).order_by(ScanHistorySnapshot.created_at.desc()).limit(1))
        if not row:
            return {"advances": 0, "declines": 0, "unchanged": 0, "total": 0, "high_52w": 0, "low_52w": 0, "source": "unavailable"}
        try:
            payload = json.loads(row.payload_json)
            stocks = payload.get("all_analyzed_stocks") or payload.get("matches") or []
            advances = 0
            declines = 0
            unchanged = 0
            for s in stocks:
                chg = s.get("change_pct")
                if chg is not None:
                    try:
                        c = float(chg)
                        if c > 0:
                            advances += 1
                        elif c < 0:
                            declines += 1
                        else:
                            unchanged += 1
                    except (ValueError, TypeError):
                        pass
            total = advances + declines + unchanged
            return {
                "advances": advances,
                "declines": declines,
                "unchanged": unchanged,
                "total": total if total > 0 else len(stocks),
                "high_52w": payload.get("high_52w_count", 0),
                "low_52w": payload.get("low_52w_count", 0),
                "source": "scan_snapshot",
            }
        except Exception as exc:
            logger.warning("BREADTH_PARSE_FAILED | error=%s", exc)
            return {"advances": 0, "declines": 0, "unchanged": 0, "total": 0, "high_52w": 0, "low_52w": 0, "source": "error"}

    async def get_index_candles(self, symbol: str, timeframe: str = "1M") -> list[dict[str, Any]]:
        cache_key = f"index_candles_{symbol}_{timeframe}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        sym_map = {
            "NSE:NIFTY50-INDEX": "^NSEI",
            "NIFTY 50": "^NSEI",
            "^NSEI": "^NSEI",
            "NSE:NIFTYBANK-INDEX": "^NSEBANK",
            "BANK NIFTY": "^NSEBANK",
            "^NSEBANK": "^NSEBANK",
            "BSE:SENSEX-INDEX": "^BSESN",
            "SENSEX": "^BSESN",
            "^BSESN": "^BSESN",
            "NSE:INDIAVIX-INDEX": "^INDIAVIX",
            "INDIA VIX": "^INDIAVIX",
            "^INDIAVIX": "^INDIAVIX",
        }
        yf_symbol = sym_map.get(symbol.strip().upper(), "^NSEI")

        period_map = {
            "1D": ("5d", "15m"),
            "1W": ("1mo", "1d"),
            "1M": ("1mo", "1d"),
            "3M": ("3mo", "1d"),
            "6M": ("6mo", "1d"),
            "1Y": ("1y", "1d"),
        }
        period, interval = period_map.get(timeframe.strip().upper(), ("6mo", "1d"))

        try:
            import yfinance as yf
            import pandas as pd
            df = await asyncio.to_thread(yf.download, yf_symbol, period=period, interval=interval, progress=False)
            if df is None or df.empty:
                return []
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            candles = []
            for idx, row in df.iterrows():
                d_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                candles.append({
                    "date": d_str,
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row.get("Volume", 0)),
                })
            cache_set(cache_key, candles, ttl_seconds=300.0)
            return candles
        except Exception as exc:
            logger.warning("INDEX_CANDLES_FAILED | symbol=%s | error=%s", symbol, str(exc))
            return []

