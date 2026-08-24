import pytest
from app.schemas.analysis import (
    AnalysisMode,
    BacktestResult,
    FinalRecommendation,
    OHLCVPoint,
    RankingItem,
    RankingsResponse,
    RecommendationReasoning,
    ScreenerConditionResult,
    StockAnalysisResult,
    TechnicalAnalysisResult,
)
from app.services.ranking_service import RankingService
from app.services.universe_service import UniverseService
from app.services.backtest_service import BacktestService
from app.services.latest_scan_service import LatestScanService
from app.services.strategies.breakout52w.attribution import build_boards as breakout_build_boards
from app.services.strategies.ltm.attribution import build_boards as ltm_build_boards
from app.utils.symbol import canonical_symbol
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_universe_company_name_map_contains_755_symbols():
    """Verify that UniverseService returns 755 active symbols in the company name map."""
    name_map = await UniverseService.get_company_name_map()
    assert len(name_map) >= 755
    # Verify canonical keys exist and map to non-empty company names
    assert "RELIANCE" in name_map
    assert "TCS" in name_map
    assert "INFY" in name_map
    assert "AVALON" in name_map
    assert isinstance(name_map["RELIANCE"], str) and len(name_map["RELIANCE"]) > 0
    assert isinstance(name_map["AVALON"], str) and len(name_map["AVALON"]) > 0


def test_stock_analysis_result_contract():
    """Verify StockAnalysisResult schema accepts and serializes symbol and company_name."""
    res = StockAnalysisResult(
        symbol="RELIANCE",
        company_name="Reliance Industries Ltd",
        ohlcv=[],
        technical=[],
        news_articles=[],
        news_summary="Neutral",
        news_sentiment_label="NEUTRAL",
        news_sentiment_score=0.5,
        backtests=[],
        recommendation=FinalRecommendation(
            action="BUY",
            confidence=0.85,
            score=82.0,
            reasoning=RecommendationReasoning(bullets=[], risk_factors=[], invalidation_signals=[]),
            trade_plans=[],
            summary="Strong breakout setup",
        ),
        disclaimer="Advisory only",
    )
    data = res.model_dump()
    assert data["symbol"] == "RELIANCE"
    assert data["company_name"] == "Reliance Industries Ltd"


def test_backtest_result_contract():
    """Verify BacktestResult schema accepts and serializes symbol and company_name."""
    res = BacktestResult(
        symbol="TCS",
        company_name="Tata Consultancy Services Ltd",
        mode=AnalysisMode.swing,
        strategy_name="breakout",
        total_return=15.5,
        cagr=12.0,
        max_drawdown=-5.0,
        win_rate=65.0,
        profit_factor=2.1,
        trade_count=12,
        verdict="Approved",
        equity_curve=[],
    )
    data = res.model_dump()
    assert data["symbol"] == "TCS"
    assert data["company_name"] == "Tata Consultancy Services Ltd"


def test_screener_condition_result_contract():
    """Verify ScreenerConditionResult schema accepts and serializes symbol and company_name."""
    res = ScreenerConditionResult(
        symbol="INFY",
        company_name="Infosys Ltd",
        close=1500.0,
        ema_20=1480.0,
        ema_50=1450.0,
        ema50_available=True,
        ema20_above_ema50=True,
        sma_30=1470.0,
        sma_50=1450.0,
        sma_100=1400.0,
        sma_200=1350.0,
        macd=12.5,
        macd_signal=10.0,
        supertrend=1420.0,
        volume=5000000,
        previous_volume=4500000,
        screener_score=85.0,
        technical_signal="BUY",
        technical_score=80.0,
        candles_fetched=250,
        conditions={"trend_pass": True},
        matched=True,
    )
    data = res.model_dump()
    assert data["symbol"] == "INFY"
    assert data["company_name"] == "Infosys Ltd"


def test_ranking_item_contract():
    """Verify RankingItem schema accepts and serializes symbol and company_name."""
    res = RankingItem(
        rank=1,
        symbol="HDFCBANK",
        company_name="HDFC Bank Ltd",
        overall_score=92.0,
        recommendation="BUY",
        best_for_mode="swing",
    )
    data = res.model_dump()
    assert data["rank"] == 1
    assert data["symbol"] == "HDFCBANK"
    assert data["company_name"] == "HDFC Bank Ltd"


def test_ranking_service_preserves_company_name():
    """Verify RankingService preserves company_name on all generated RankingItem instances."""
    stock1 = StockAnalysisResult(
        symbol="SBIN",
        company_name="State Bank of India",
        ohlcv=[],
        technical=[],
        news_articles=[],
        news_summary="",
        news_sentiment_label="NEUTRAL",
        news_sentiment_score=0.5,
        backtests=[],
        recommendation=FinalRecommendation(
            action="BUY",
            confidence=0.9,
            score=90.0,
            reasoning=RecommendationReasoning(bullets=[], risk_factors=[], invalidation_signals=[]),
            trade_plans=[],
            summary="",
        ),
        disclaimer="",
    )
    stock2 = StockAnalysisResult(
        symbol="ICICIBANK",
        company_name="ICICI Bank Ltd",
        ohlcv=[],
        technical=[],
        news_articles=[],
        news_summary="",
        news_sentiment_label="NEUTRAL",
        news_sentiment_score=0.5,
        backtests=[],
        recommendation=FinalRecommendation(
            action="WATCH",
            confidence=0.7,
            score=70.0,
            reasoning=RecommendationReasoning(bullets=[], risk_factors=[], invalidation_signals=[]),
            trade_plans=[],
            summary="",
        ),
        disclaimer="",
    )

    ranking_svc = RankingService()
    rankings: RankingsResponse = ranking_svc.rank([stock1, stock2])
    assert len(rankings.rankings) == 2
    assert rankings.rankings[0].symbol == "SBIN"
    assert rankings.rankings[0].company_name == "State Bank of India"
    assert rankings.rankings[1].symbol == "ICICIBANK"
    assert rankings.rankings[1].company_name == "ICICI Bank Ltd"

    assert len(rankings.buy_rankings) == 1
    assert rankings.buy_rankings[0].symbol == "SBIN"
    assert rankings.buy_rankings[0].company_name == "State Bank of India"

    assert len(rankings.watch_rankings) == 1
    assert rankings.watch_rankings[0].symbol == "ICICIBANK"
    assert rankings.watch_rankings[0].company_name == "ICICI Bank Ltd"


def test_backtest_service_populates_canonical_symbol_and_company_name():
    """Verify BacktestService.run and _empty_result set canonical symbol and company_name."""
    bt_svc = BacktestService()
    empty = bt_svc._empty_result(
        symbol="NSE:AVALON-EQ",
        mode=AnalysisMode.swing,
        strategy_name="breakout",
        company_name="Avalon Technologies Ltd",
    )
    assert empty.symbol == "AVALON"
    assert empty.company_name == "Avalon Technologies Ltd"


def test_breakout52w_attribution_boards_symbol_and_company_name():
    """Verify Breakout 52W attribution boards include canonical symbol and company_name."""
    reports = {
        "NSE:TATAMOTORS-EQ": {
            "net_return": 0.35,
            "trade_count": 8,
            "win_rate": 0.75,
            "max_drawdown": -0.08,
            "profit_factor": 2.5,
            "never_selected_in_window": False,
            "failed": False,
        },
        "NSE:MARUTI-EQ": {
            "net_return": -0.05,
            "trade_count": 4,
            "win_rate": 0.25,
            "max_drawdown": -0.12,
            "profit_factor": 0.6,
            "never_selected_in_window": False,
            "failed": False,
        },
    }
    signals = {"NSE:TATAMOTORS-EQ": "BUY", "NSE:MARUTI-EQ": "REJECT"}
    company_names = {
        "TATAMOTORS": "Tata Motors Ltd",
        "MARUTI": "Maruti Suzuki India Ltd",
    }

    top5, least5 = breakout_build_boards(reports, signals, company_names=company_names)
    assert len(top5) == 1
    assert top5[0]["symbol"] == "TATAMOTORS"
    assert top5[0]["company_name"] == "Tata Motors Ltd"
    assert top5[0]["signal"] == "BUY"

    assert len(least5) == 2
    assert least5[0]["symbol"] == "MARUTI"
    assert least5[0]["company_name"] == "Maruti Suzuki India Ltd"
    assert least5[0]["signal"] == "REJECT"


def test_ltm_attribution_boards_symbol_and_company_name():
    """Verify LTM attribution boards include canonical symbol and company_name."""
    reports = {
        "BAJFINANCE-EQ": {
            "net_return": 0.42,
            "trade_count": 5,
            "win_rate": 0.80,
            "max_drawdown": -0.05,
            "profit_factor": 3.0,
            "never_selected_in_window": False,
        }
    }
    signals = {"BAJFINANCE-EQ": "BUY"}
    company_names = {"BAJFINANCE": "Bajaj Finance Ltd"}

    top5, least5 = ltm_build_boards(reports, signals, company_names=company_names)
    assert len(top5) == 1
    assert top5[0]["symbol"] == "BAJFINANCE"
    assert top5[0]["company_name"] == "Bajaj Finance Ltd"
    assert top5[0]["signal"] == "BUY"
