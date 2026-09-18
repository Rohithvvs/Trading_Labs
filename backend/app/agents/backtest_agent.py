from __future__ import annotations

from ..schemas import AnalysisMode, BacktestResult, OHLCVPoint
from ..services.backtest_service import BacktestService


class BacktestAgent:
    def __init__(self) -> None:
        self.service = BacktestService()

    def run(
        self,
        symbol: str,
        mode: AnalysisMode,
        candles: list[OHLCVPoint],
        cost_scenario: str = "BASE_COST",
        position_sizing_pct: float = 20.0,
        execution_model: str = "REALISTIC",
        composite_uses_realistic: bool = True,
        skip_on_missing_next_bar: bool = True,
        feat008_enabled: bool = True,
        company_name: str | None = None,
    ) -> BacktestResult:
        return self.service.run(
            symbol, mode, candles, cost_scenario,
            position_sizing_pct, execution_model, composite_uses_realistic,
            skip_on_missing_next_bar=skip_on_missing_next_bar,
            feat008_enabled=feat008_enabled,
            company_name=company_name,
        )

    async def run_async(
        self,
        symbol: str,
        mode: AnalysisMode,
        candles: list[OHLCVPoint],
        cost_scenario: str = "BASE_COST",
        position_sizing_pct: float = 20.0,
        execution_model: str = "REALISTIC",
        composite_uses_realistic: bool = True,
        skip_on_missing_next_bar: bool = True,
        feat008_enabled: bool = True,
        company_name: str | None = None,
    ) -> BacktestResult:
        bt_candles = candles
        if mode.value == "swing":
            try:
                from datetime import date, datetime, timedelta, timezone
                from ..services.market_data_ingestion.repository import fetch_equity_history
                three_years_ago = date.today() - timedelta(days=3 * 365)
                history = await fetch_equity_history(symbol, from_date=three_years_ago)
                if history and len(history) > len(bt_candles):
                    bt_candles = []
                    for r in history:
                        dt = datetime.combine(r["trade_date"], datetime.min.time()).replace(tzinfo=timezone.utc)
                        bt_candles.append(
                            OHLCVPoint(
                                timestamp=dt,
                                open=r["open"],
                                high=r["high"],
                                low=r["low"],
                                close=r["close"],
                                volume=r["volume"]
                            )
                        )
            except Exception as e:
                import logging
                logging.getLogger("app.backtest_agent").warning("Failed to fetch 3-year daily_ohlcv for %s: %s", symbol, e)
                
        return self.run(
            symbol, mode, bt_candles, cost_scenario,
            position_sizing_pct, execution_model, composite_uses_realistic,
            skip_on_missing_next_bar=skip_on_missing_next_bar,
            feat008_enabled=feat008_enabled,
            company_name=company_name,
        )

    async def run_with_authoritative_candles(
        self,
        symbol: str,
        mode: AnalysisMode,
        resolution: str = "1D",
        start_date: str | None = None,
        end_date: str | None = None,
        cost_scenario: str = "BASE_COST",
        company_name: str | None = None,
    ) -> BacktestResult:
        """Run backtest using Authoritative Candle Store as historical data source."""
        from ..config.settings import settings
        from ..services.authoritative_candle_store import authoritative_candle_store

        candles = await authoritative_candle_store.get_candles(
            symbol=symbol,
            resolution=resolution,
            start_date=start_date,
            end_date=end_date,
        )
        return self.run(
            symbol=symbol, mode=mode, candles=candles,
            cost_scenario=cost_scenario, company_name=company_name,
        )
