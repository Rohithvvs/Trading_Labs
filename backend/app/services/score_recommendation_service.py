"""Score-based recommendation builder (replaces the deleted RecommendationEngine).

The legacy Production / RE-001 / RE-002 recommendation engines were removed
from the codebase (audit-driven teardown).  This module is the lean, fully
deterministic replacement for the old ``RecommendationService``:

  * Composite score is computed with ``ScoringMatrixService.compute_composite_score``
    using the canonical matrix configuration (baseline, or rebalanced when the
    Market Breadth rule is active in production).
  * Final signal is classified ONLY by composite score (telemetry overlays such
    as FEAT-004 / FEAT-007 no longer run inside the recommendation path; sector
    and market-permission overlays are still applied by the orchestrator's
    challenger logic, which is shadow/compare only).
  * Mandatory preconditions (trusted data source, minimum swing candles, finite
    score/confidence, complete trade plan) must pass; otherwise the signal is
    REJECT with reason "Analysis Failed".

Thresholds (production, per RECOMMENDATION_ENGINE_ANALYSIS.md):
    score >= 70            -> BUY
    55 <= score < 70       -> WATCH
    score < 55             -> REJECT

NOTE on composite semantics: the pre-removal production path used dynamic
weights (tech 50% / backtest 25% / fundamental 25% / news 0%) when Market
Breadth was not promoted.  This rebuild always uses the canonical
ScoringMatrixService matrix (baseline: tech 35 / sentiment 25 / fundamental
25 / volume 15 / breadth 0; rebalanced when breadth is promoted).  Backtest
performance therefore no longer feeds the composite score — it is surfaced via
the ``backtest_score`` component field and reasoning bullets instead — and
sentiment/volume now influence the score.  This was a deliberate choice when
replacing the removed engines; the composite is not bit-for-bit equivalent to
pre-removal scoring.
"""

from __future__ import annotations

import logging
import math
from statistics import mean
from typing import Any

from ..schemas import (
    AnalysisMode,
    BacktestResult,
    FinalRecommendation,
    FundamentalAnalysisResult,
    OHLCVPoint,
    RecommendationReasoning,
    TechnicalAnalysisResult,
    TradePlan,
)

logger = logging.getLogger("app.score_recommendation_service")

# Pure score-based signal thresholds (production classification).
BUY_SCORE_THRESHOLD = 70.0
WATCH_SCORE_THRESHOLD = 55.0
ANALYSIS_FAILED_REASON = "Analysis Failed"


def classify_signal_from_score(score: float) -> str:
    """Classify BUY / WATCH / REJECT from composite score only.

    score >= 70 -> BUY
    55 <= score < 70 -> WATCH
    score < 55 -> REJECT
    """
    if math.isnan(score) or math.isinf(score):
        return "REJECT"
    if score >= BUY_SCORE_THRESHOLD:
        return "BUY"
    if score >= WATCH_SCORE_THRESHOLD:
        return "WATCH"
    return "REJECT"


def is_trade_plan_complete(plan: Any) -> bool:
    """True when entry, stop-loss, and target are present and usable."""
    if plan is None:
        return False
    try:
        entry_low = float(getattr(plan, "entry_low", 0) or 0)
        entry_high = float(getattr(plan, "entry_high", 0) or 0)
        stop_loss = float(getattr(plan, "stop_loss", 0) or 0)
        target_1 = float(getattr(plan, "target_1", 0) or 0)
    except (TypeError, ValueError):
        return False
    if entry_low <= 0 or entry_high <= 0 or stop_loss <= 0 or target_1 <= 0:
        return False
    if entry_high < entry_low:
        return False
    return True


def analysis_preconditions_ok(
    *,
    score: float,
    confidence: float | None,
    trade_plans: list[Any] | None,
    data_quality: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Mandatory preconditions before score-based signal assignment.

    Returns (ok, reason); reason is ANALYSIS_FAILED_REASON when not ok.
    """
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return False, ANALYSIS_FAILED_REASON
    if math.isnan(score_f) or math.isinf(score_f):
        return False, ANALYSIS_FAILED_REASON

    try:
        conf_f = float(confidence) if confidence is not None else float("nan")
    except (TypeError, ValueError):
        return False, ANALYSIS_FAILED_REASON
    if math.isnan(conf_f) or math.isinf(conf_f):
        return False, ANALYSIS_FAILED_REASON

    if data_quality is not None:
        if bool(data_quality.get("mock_warning")):
            return False, ANALYSIS_FAILED_REASON
        if not bool(data_quality.get("minimum_swing_candles_met")):
            return False, ANALYSIS_FAILED_REASON
        source = str(data_quality.get("source") or "")
        if source in {"MOCK_FALLBACK", "NO_DATA", "NONE"}:
            return False, ANALYSIS_FAILED_REASON

    plans = trade_plans or []
    if not plans:
        return False, ANALYSIS_FAILED_REASON
    if not any(is_trade_plan_complete(p) for p in plans):
        return False, ANALYSIS_FAILED_REASON

    return True, ""


class ScoreRecommendationService:
    """Build a FinalRecommendation from score components without any engine code."""

    def build(
        self,
        *,
        symbol: str,
        technical_results: list[TechnicalAnalysisResult],
        sentiment_score: float,
        fundamental_result: FundamentalAnalysisResult | None,
        backtests: list[BacktestResult],
        candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]],
        market_breadth_soft_score: float | None = None,
        breadth_active: bool | None = None,
        data_quality: dict[str, Any] | None = None,
    ) -> FinalRecommendation:
        technical_score = max((result.score for result in technical_results), default=0.0)
        best_backtest = max(backtests, key=lambda item: item.total_return) if backtests else None

        fundamental_score = fundamental_result.fundamental_score if fundamental_result else 0.0

        # Volume catalyst inputs.
        primary_technical = technical_results[0] if technical_results else None
        candles = candles_by_mode.get(primary_technical.mode, []) if primary_technical else []
        current_volume = candles[-1].volume if candles else 0
        avg_volume = mean([c.volume for c in candles[-20:]]) if len(candles) >= 20 else current_volume

        # Stage-2 Market Breadth gate (fail-open to baseline on any governance error).
        # Callers that already evaluated the rule (e.g. the orchestrator, which computes
        # market_breadth_soft_score only when the rule is active in production) can pass
        # breadth_active to avoid a duplicate RuleManager lookup per symbol.
        if breadth_active is None:
            try:
                from ..governance.rule_manager import RuleManager

                breadth_active = RuleManager().is_active_in_production("market_breadth")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "governance_fail_open | symbol=%s | rule=market_breadth | error=%s | action=baseline_scoring",
                    symbol,
                    exc,
                )
                breadth_active = False

        # Factor scores on a 0-100 scale.
        raw_tech = float(technical_score)  # 0-100
        raw_news = max(0.0, min(100.0, (float(sentiment_score) + 1.0) / 2.0 * 100.0))
        raw_fund = max(0.0, min(100.0, (float(fundamental_score) + 1.0) / 2.0 * 100.0))
        raw_vol = min(
            100.0,
            max(0.0, (current_volume / max(1.0, float(avg_volume))) * 50.0),
        )

        # Market Breadth soft contribution [-15, +15] -> factor score [0, 100] centered at 50.
        breadth_factor = 50.0
        if breadth_active:
            soft = market_breadth_soft_score
            if soft is None or (isinstance(soft, float) and (math.isnan(soft) or math.isinf(soft))):
                soft = 0.0
                logger.warning("breadth_soft_missing | symbol=%s | action=soft_score_0", symbol)
            soft_f = max(-15.0, min(15.0, float(soft)))
            breadth_factor = max(0.0, min(100.0, 50.0 + (soft_f / 15.0) * 50.0))

        from .scoring_matrix_service import ScoringMatrixService

        matrix_config = ScoringMatrixService.get_matrix_config(
            market_breadth_promoted=breadth_active
        )
        score = round(
            ScoringMatrixService.compute_composite_score(
                technical_score=raw_tech,
                sentiment_score=raw_news,
                fundamental_score=raw_fund,
                volume_score=raw_vol,
                market_breadth_score=breadth_factor,
                matrix_config=matrix_config,
            ),
            2,
        )
        if math.isnan(score) or math.isinf(score):
            logger.error(
                "composite_score_non_finite | symbol=%s | score=%s | fail_open=0",
                symbol,
                score,
            )
            score = 0.0
        score = max(0.0, min(100.0, score))

        confidence = round(min(0.95, max(0.35, score / 100)), 2)
        trade_plans = self._build_trade_plans(technical_results, backtests, candles_by_mode)

        # Final signal is ONLY score-based AFTER all analysis modules completed.
        preconditions_ok, _reason = analysis_preconditions_ok(
            score=score,
            confidence=confidence,
            trade_plans=trade_plans,
            data_quality=data_quality,
        )
        if not preconditions_ok:
            action = "REJECT"
            logger.info(
                "ANALYSIS_FAILED | symbol=%s | stage=score_recommendation_service | score=%.2f | plans=%s | reason=%s",
                symbol,
                score,
                len(trade_plans),
                ANALYSIS_FAILED_REASON,
            )
        else:
            action = classify_signal_from_score(score)

        reasoning = self._build_reasoning(
            symbol=symbol,
            action=action,
            score=score,
            raw_tech=raw_tech,
            raw_news=raw_news,
            raw_fund=raw_fund,
            raw_vol=raw_vol,
            best_backtest=best_backtest,
            confidence=confidence,
            preconditions_ok=preconditions_ok,
        )

        return FinalRecommendation(
            action=action,
            confidence=confidence,
            score=score,
            reasoning=reasoning,
            trade_plans=trade_plans,
            summary=(
                f"{symbol} is rated {action} with composite score {score:.2f} "
                f"and confidence {confidence:.2f}."
            ),
            # Component scores on the 0-100 scale for UI / persistence.
            technical_score=round(raw_tech, 2),
            backtest_score=round(self._backtest_component(best_backtest), 2),
            fundamental_score=round(raw_fund, 2),
        )

    # ------------------------------------------------------------------ #
    # Reasoning
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_reasoning(
        *,
        symbol: str,
        action: str,
        score: float,
        raw_tech: float,
        raw_news: float,
        raw_fund: float,
        raw_vol: float,
        best_backtest: BacktestResult | None,
        confidence: float,
        preconditions_ok: bool,
    ) -> RecommendationReasoning:
        bullets: list[str] = []
        risk_factors: list[str] = []
        invalidation_signals: list[str] = [
            "Close below the planned stop-loss on the primary timeframe",
            "Breakdown below the recent swing low / trend structure",
        ]

        if not preconditions_ok:
            bullets.append(f"Analysis Failed: {symbol} did not pass mandatory preconditions (data quality or trade plan).")
            risk_factors.append("Mandatory precondition failure (data quality / trade plan)")
        else:
            bullets.append(
                f"Composite score {score:.2f} classifies {symbol} as {action} "
                f"(BUY >= {BUY_SCORE_THRESHOLD:.0f}, WATCH {WATCH_SCORE_THRESHOLD:.0f}-{BUY_SCORE_THRESHOLD - 0.01:.2f})."
            )
            bullets.append(
                f"Component scores: technical {raw_tech:.1f} / news {raw_news:.1f} / "
                f"fundamental {raw_fund:.1f} / volume {raw_vol:.1f} (0-100 scale)."
            )
            if best_backtest is not None:
                bullets.append(
                    f"Best backtest: {best_backtest.strategy_name} | verdict={best_backtest.verdict} | "
                    f"return={best_backtest.total_return:.2f}% | trades={best_backtest.trade_count} | "
                    f"max_drawdown={best_backtest.max_drawdown:.2f}%."
                )
                if best_backtest.max_drawdown < -20:
                    risk_factors.append(
                        f"Backtest max drawdown {best_backtest.max_drawdown:.2f}% exceeds 20%"
                    )
                if best_backtest.trade_count < 5:
                    risk_factors.append(
                        f"Backtest trade count {best_backtest.trade_count} is below 5 (weak sample)"
                    )
            if raw_tech < BUY_SCORE_THRESHOLD:
                risk_factors.append(f"Technical score {raw_tech:.1f} is below the BUY threshold")
            if raw_vol < 50:
                risk_factors.append(f"Volume score {raw_vol:.1f} indicates below-average volume")
            if confidence < 0.5:
                risk_factors.append(f"Confidence {confidence:.2f} is low")

        return RecommendationReasoning(
            bullets=bullets,
            risk_factors=risk_factors,
            invalidation_signals=invalidation_signals,
        )

    # ------------------------------------------------------------------ #
    # Backtest / trade-plan helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _backtest_component(backtest: BacktestResult | None) -> float:
        """Backtest factor on the 0-100 scale, matching the pre-removal raw_backtest.

        total_return x4 clamped to [-20, 100], zero when the sample is too small.
        Kept identical to the legacy RecommendationService so consumers of the
        recommendation.backtest_score field see the same scale as before.
        """
        if backtest is None or backtest.verdict == "insufficient" or backtest.trade_count < 5:
            return 0.0
        value = backtest.total_return * 4
        return round(min(max(value, -20.0), 100.0), 2)

    def _build_trade_plans(
        self,
        technical_results: list[TechnicalAnalysisResult],
        backtests: list[BacktestResult],
        candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]],
    ) -> list[TradePlan]:
        plans: list[TradePlan] = []
        backtests_by_mode = {item.mode: item for item in backtests}

        for technical in technical_results:
            candles = candles_by_mode.get(technical.mode, [])
            if len(candles) < 5:
                continue
            current_price = candles[-1].close
            recent_ranges = [candle.high - candle.low for candle in candles[-10:]]
            avg_range = mean(recent_ranges) if recent_ranges else current_price * 0.01
            direction = 1 if technical.signal == "bullish" else -1 if technical.signal == "bearish" else 0
            setup_type = self._setup_type(technical.mode, technical.signal)
            timeframe = "intraday execution" if technical.mode == AnalysisMode.intraday else "multi-session swing"

            recent_lows = [c.low for c in candles[-10:]]
            recent_highs = [c.high for c in candles[-20:]]
            lowest_low = min(recent_lows) if recent_lows else current_price - avg_range
            highest_high = max(recent_highs) if recent_highs else current_price + avg_range

            if direction >= 0:
                entry_low = round(current_price - avg_range * 0.2, 2)
                entry_high = round(current_price + avg_range * 0.1, 2)
                stop_loss = round(min(entry_low - avg_range * 0.6, lowest_low - avg_range * 0.1), 2)
                target_1 = round(max(entry_high + avg_range * 1.6, highest_high + avg_range * 0.2), 2)
                target_2 = round(entry_high + (entry_high - stop_loss) * 2.0, 2)
                target_3 = round(entry_high + (entry_high - stop_loss) * 3.0, 2)
                bias = "long"
            else:
                entry_low = round(current_price - avg_range * 0.1, 2)
                entry_high = round(current_price + avg_range * 0.2, 2)
                stop_loss = round(max(entry_high + avg_range * 0.6, highest_high + avg_range * 0.1), 2)
                target_1 = round(min(entry_low - avg_range * 1.6, lowest_low - avg_range * 0.2), 2)
                target_2 = round(entry_low - (stop_loss - entry_low) * 2.0, 2)
                target_3 = round(entry_low - (stop_loss - entry_low) * 3.0, 2)
                bias = "short"

            if direction == 0:
                bias = "wait"
                stop_loss = round(current_price - avg_range if technical.mode == AnalysisMode.swing else current_price - (avg_range * 0.7), 2)

            risk = abs(((entry_low + entry_high) / 2) - stop_loss)
            reward = abs(target_1 - ((entry_low + entry_high) / 2))
            risk_reward_ratio = round(reward / risk, 2) if risk else 0.0
            backtest = backtests_by_mode.get(technical.mode)
            notes = (
                f"Use the {setup_type} setup with {technical.signal} bias. "
                f"Backtest verdict: {backtest.verdict if backtest else 'n/a'}."
            )

            plans.append(
                TradePlan(
                    mode=technical.mode,
                    strategy_name=backtest.strategy_name if backtest else setup_type,
                    setup_type=setup_type,
                    timeframe=timeframe,
                    bias=bias,
                    entry_low=entry_low,
                    entry_high=entry_high,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    target_3=target_3,
                    risk_reward_ratio=risk_reward_ratio,
                    notes=notes,
                )
            )

        return plans

    @staticmethod
    def _setup_type(mode: AnalysisMode, signal: str) -> str:
        if mode == AnalysisMode.intraday:
            return "VWAP continuation" if signal == "bullish" else "VWAP rejection"
        return "Trend pullback" if signal == "bullish" else "Breakdown retest"
