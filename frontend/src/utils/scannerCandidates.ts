import type { CandidateRow, RecommendationPrefillRequest } from "../types";
import { completePaperLevels } from "./paperOrderLevels";
import { LTM_STRATEGY_ID, W52_STRATEGY_ID } from "./strategyIdentity";

function pos(n: number | null | undefined): number | null {
  return n != null && Number.isFinite(Number(n)) && Number(n) > 0 ? Number(n) : null;
}

function momentumPercent(raw: unknown): number | null {
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  return Math.round(raw * 1000) / 10;
}

function allowedSignal(raw: unknown, extra: string[] = []): CandidateRow["signal"] {
  const value = String(raw || "").toUpperCase();
  const allowed = new Set(["BUY", "HOLD", "WATCH", "REJECT", ...extra]);
  return (allowed.has(value) ? value : "REJECT") as CandidateRow["signal"];
}

const SPARKLINE_MAX_POINTS = 32;

function downsampleSparkline(points: { label: string; equity: number }[]): { label: string; equity: number }[] {
  if (points.length <= SPARKLINE_MAX_POINTS) return points;
  const last = points.length - 1;
  const step = last / (SPARKLINE_MAX_POINTS - 1);
  const out: { label: string; equity: number }[] = [];
  for (let i = 0; i < SPARKLINE_MAX_POINTS; i += 1) {
    out.push(points[Math.round(i * step)]);
  }
  return out;
}

function sparklineFromTrades(backtest: Record<string, any> | null | undefined): { label: string; equity: number }[] {
  const trades = Array.isArray(backtest?.trades) ? backtest.trades : [];
  if (!trades.length) return [];
  let equity = 100;
  const points = [{ label: "start", equity }];
  const limit = Math.min(trades.length, 200);
  for (let i = 0; i < limit; i += 1) {
    const trade = trades[i];
    const pnl = typeof trade?.pnl_pct === "number" && Number.isFinite(trade.pnl_pct) ? trade.pnl_pct : 0;
    equity *= 1 + pnl;
    points.push({
      label: String(trade.exit_date || trade.entry_date || points.length),
      equity,
    });
  }
  return downsampleSparkline(points);
}

function isW52ScreenerRow(r: any): boolean {
  if (r?.screener_pass || r?.buy_signal) return true;
  const signal = String(r?.signal || "").toUpperCase();
  return signal === "BUY" || signal === "WATCH" || signal === "HOLD";
}

export function buildW52CandidateRows(payload: Record<string, any> | null): CandidateRow[] {
  if (!Array.isArray(payload?.recommendations)) return [];
  if (!payload.recommendations_final && !payload.completed_at) return [];
  const order: Record<string, number> = { BUY: 0, WATCH: 1, HOLD: 2, REJECT: 3 };
  return payload.recommendations
    .filter(isW52ScreenerRow)
    .map((r: any) => {
    const close = pos(r.entry ?? r.close ?? r.technicals?.close_t);
    const stop = pos(r.stop_loss ?? r.technicals?.tsl);
    const target = pos(r.target);
    const rr = pos(r.risk_reward);
    const publishLevels = r.signal === "BUY" || r.signal === "HOLD" || r.signal === "WATCH";
    return {
      rank: r.rank ?? r.screener_rank ?? r.buy_rank ?? null,
      symbol: String(r.symbol || "").toUpperCase(),
      companyName: r.company_name ?? null,
      signal: allowedSignal(r.signal),
      score: null,
      scoreKind: "momentum_60" as const,
      scoreLabel: "Momentum 60",
      momentumValue: momentumPercent(r.mom60 ?? r.technicals?.mom60),
      strategyId: W52_STRATEGY_ID,
      confidence: null,
      entryLow: publishLevels ? close : null,
      entryHigh: publishLevels ? close : null,
      stopLoss: publishLevels ? stop : null,
      target1: publishLevels ? target : null,
      target2: null,
      riskReward: rr,
      trend: payload.book_status || "—",
      momentum:
        r.mom60 != null && typeof r.mom60 === "number"
          ? `${(r.mom60 * 100).toFixed(1)}%`
          : "unavailable",
      volume: r.volume != null ? String(r.volume) : "n/a",
      newsSentiment: "n/a",
      lastUpdated: payload.evaluation_date ?? null,
      tradeReadiness:
        r.signal === "BUY"
          ? "Review manually"
          : r.signal === "HOLD"
            ? "Hold"
            : r.signal === "WATCH"
              ? "Review manually"
              : "Avoid",
      recommendationSummary: r.first_failure
        ? `Rejected: ${r.first_failure}`
        : r.signal === "HOLD"
          ? "52-Week High Breakout holding"
          : "52-Week High Breakout selection",
      w52: {
        technicals: r.technicals,
        backtest_1y: r.backtest_1y,
        equity_curve: sparklineFromTrades(r.backtest_1y),
        initial_capital: payload.initial_capital ?? payload.book_metrics?.initial_capital ?? null,
        evaluation_date: payload.evaluation_date ?? null,
      },
    };
  }).sort((a, b) => {
    const da = order[a.signal] ?? 9;
    const db = order[b.signal] ?? 9;
    if (da !== db) return da - db;
    const ra = a.rank ?? 10_000;
    const rb = b.rank ?? 10_000;
    if (ra !== rb) return ra - rb;
    return a.symbol.localeCompare(b.symbol);
  });
}

export function buildLtmCandidateRows(payload: Record<string, any> | null): CandidateRow[] {
  if (!Array.isArray(payload?.recommendations)) return [];
  if (!payload.recommendations_final && !payload.completed_at) return [];
  const clock = payload.clock_status || "—";
  return payload.recommendations.map((r: any) => {
    const selected = Boolean(r.selected);
    const close = pos(r.entry ?? r.technicals?.close_t);
    const publishLevels = r.signal === "BUY" || r.signal === "WATCH";
    return {
      rank: r.rank ?? null,
      symbol: String(r.symbol || "").toUpperCase(),
      companyName: r.company_name ?? null,
      signal: allowedSignal(r.signal),
      score: null,
      scoreKind: "momentum_252" as const,
      scoreLabel: "Momentum 252",
      momentumValue: momentumPercent(r.momentum_252 ?? r.technicals?.momentum_252),
      strategyId: LTM_STRATEGY_ID,
      confidence: null,
      entryLow: publishLevels ? close : null,
      entryHigh: publishLevels ? close : null,
      stopLoss: pos(r.stop_loss),
      target1: pos(r.target),
      target2: null,
      riskReward: pos(r.risk_reward),
      trend: clock,
      momentum:
        r.momentum_252 != null && typeof r.momentum_252 === "number"
          ? `${(r.momentum_252 * 100).toFixed(1)}%`
          : "unavailable",
      volume: "n/a",
      newsSentiment: "n/a",
      lastUpdated: payload.evaluation_date ?? null,
      tradeReadiness: r.signal === "BUY" || r.signal === "WATCH" ? "Review manually" : "Avoid",
      recommendationSummary: r.first_failure
        ? `Rejected: ${r.first_failure}`
        : r.signal === "WATCH" && clock === "MID_CYCLE" && selected
          ? "Selected in the current 252-session book. Signal is WATCH until the next rebalance — BUY is issued only on rebalance day."
          : "Long-Term Buy & Hold Momentum selection",
      ltm: {
        technicals: r.technicals,
        backtest_1y: r.backtest_1y,
        equity_curve: sparklineFromTrades(r.backtest_1y),
        initial_capital: payload.initial_capital ?? payload.book_metrics?.initial_capital ?? null,
        evaluation_date: payload.evaluation_date ?? null,
      },
    };
  });
}

export function buildPaperTradingPrefill(
  row: CandidateRow,
  side?: "BUY" | "SELL",
): RecommendationPrefillRequest {
  const plan =
    row.analysisItem?.recommendation.trade_plans.find((item) => item.mode === "swing") ??
    row.analysisItem?.recommendation.trade_plans[0];
  let suggested_stop: number | null = pos(plan?.stop_loss ?? row.stopLoss);
  let suggested_targets: number[] = [plan?.target_1, plan?.target_2, row.target1, row.target2]
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value) && value > 0)
    .filter((value, index, arr) => arr.indexOf(value) === index);
  if (plan && side) {
    const needsSwap =
      (side === "BUY" && plan.bias === "short") || (side === "SELL" && plan.bias === "long");
    if (needsSwap && plan.target_1 != null && plan.stop_loss != null) {
      suggested_stop = pos(plan.target_1);
      suggested_targets = [plan.stop_loss, plan.target_2].filter(
        (value): value is number => typeof value === "number" && Number.isFinite(value) && value > 0,
      );
    }
  }
  let suggested_entry: number | null = null;
  if (plan) {
    const mid =
      plan.entry_low != null && plan.entry_high != null
        ? (Number(plan.entry_low) + Number(plan.entry_high)) / 2
        : Number(plan.entry_high ?? plan.entry_low);
    suggested_entry = pos(mid);
  }
  if (suggested_entry == null) {
    const mid =
      row.entryLow != null && row.entryHigh != null
        ? (Number(row.entryLow) + Number(row.entryHigh)) / 2
        : Number(row.entryHigh ?? row.entryLow);
    suggested_entry = pos(mid);
  }
  const scoreMeta =
    row.score != null && Number.isFinite(row.score)
      ? row.score
      : row.momentumValue != null && Number.isFinite(row.momentumValue)
        ? row.momentumValue
        : 0;
  const filled = completePaperLevels({
    entry: suggested_entry,
    side: side ?? "BUY",
    stop: suggested_stop,
    target: suggested_targets[0] ?? null,
  });
  return {
    symbol: row.symbol,
    suggested_entry,
    suggested_stop: filled.stopLoss,
    suggested_targets: filled.target != null ? [filled.target, ...suggested_targets.slice(1)] : suggested_targets,
    recommendation_meta: {
      signal: row.signal,
      score: scoreMeta,
      score_kind: row.scoreKind || "composite",
      score_label: row.scoreLabel || "Score",
      strategy_id: row.strategyId || "",
      stop_source: filled.derivedStop ? "limit_price" : suggested_stop != null ? "strategy" : "",
      target_source: filled.derivedTarget ? "limit_price" : suggested_targets[0] != null ? "strategy" : "",
      confidence: Math.round((row.confidence ?? 0) * 100) / 100,
    },
  };
}

export function preferredPaperEntry(
  prefill: RecommendationPrefillRequest,
  liveFallback?: number | null,
): number | null {
  return pos(prefill.suggested_entry) ?? pos(liveFallback);
}
