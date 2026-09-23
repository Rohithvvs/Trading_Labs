import type { IndicatorFilter, IndicatorScanRow, IndicatorScanStatus } from "../api_indicator_scanner";
import type { RankedReturn, StrategyResultRow, StrategyRunStatus } from "../api_strategy_tester";
import type { SymbolDetail } from "../types";
import { absorbEntryConditions, isAggregateSignalFilter, looksLikeAggregateSignal } from "./indicatorAbsorb";

export function isIndicatorScanId(id: string | null | undefined): boolean {
  return Boolean(id && /^IND-/i.test(id.trim()));
}

export function isIndicatorScanContext(
  stock?: { source?: string | null } | null,
  runId?: string | null,
): boolean {
  if (stock?.source === "indicator_scanner") return true;
  return isIndicatorScanId(runId);
}

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function filterLabel(filter: IndicatorFilter): string {
  const field = filter.field || "";
  const op = filter.operator || "=";
  if (op === "between") return `${field} between ${filter.low} and ${filter.high}`;
  if (["is_true", "is_false", "is_null", "is_not_null"].includes(op)) {
    return `${field} ${op.replace(/_/g, " ")}`;
  }
  if (filter.value === undefined || filter.value === null || filter.value === "") return field;
  return `${field} ${op} ${filter.value}`;
}

export function mapIndicatorResultToStock(
  row: IndicatorScanRow & {
    filter_results?: Array<{ name: string; passed: boolean }>;
    signal?: string;
    company?: string | null;
    entry_price?: number | null;
    exit_price?: number | null;
    return_pct?: number | null;
    close?: number | null;
    evaluation_date?: string | null;
    source?: string;
    indicator_name?: string;
  },
  scan?: IndicatorScanStatus | null,
): StrategyResultRow {
  const outputs = row.outputs || {};
  const close = num(row.close) ?? num(outputs.Close) ?? num(row.ohlcv?.close);
  const momentum =
    num(outputs["Momentum 252"]) ??
    num(outputs["Mom 252"]) ??
    num(outputs["First-Year Return"]);
  const closeT252 =
    num(outputs["Close t-252"]) ??
    num((row as any).close_t252) ??
    (close != null && momentum != null ? Math.round((close / (1 + momentum)) * 100) / 100 : null);
  const returnPct =
    row.return_pct != null
      ? row.return_pct
      : momentum != null
        ? momentum * 100
        : close != null && closeT252
          ? (close / closeT252 - 1) * 100
          : 0;

  const sma20 = num(outputs["SMA 20"]) ?? num(outputs["sma20"]) ?? num(outputs.sma_20) ?? num((row as any).indicators?.sma_20);
  const sma50 = num(outputs["SMA 50"]) ?? num(outputs["sma50"]) ?? num(outputs.sma_50) ?? num((row as any).indicators?.sma_50);
  const sma200 = num(outputs["SMA 200"]) ?? num(outputs["sma200"]) ?? num(outputs.sma_200) ?? num((row as any).indicators?.sma_200);
  const ema20 = num(outputs["EMA 20"]) ?? num(outputs["ema20"]) ?? num(outputs.ema_20) ?? num((row as any).indicators?.ema_20);
  const ema50 = num(outputs["EMA 50"]) ?? num(outputs["ema50"]) ?? num(outputs.ema_50) ?? num((row as any).indicators?.ema_50);
  const avgVol = num(outputs["Avg Volume"]) ?? num(outputs["volSma20"]) ?? num(outputs.avg_volume_20) ?? num((row as any).indicators?.avg_volume);
  const rsi = num(outputs["RSI"]) ?? num(outputs["RSI (14)"]) ?? num(outputs.rsiSma) ?? num((row as any).indicators?.rsi);
  const atr = num(outputs["ATR"]) ?? num(outputs.atrSma14) ?? num((row as any).indicators?.atr);
  const macd = num(outputs["MACD"]) ?? num((row as any).indicators?.macd);
  const macdSignal = num(outputs["MACD Signal"]) ?? num((row as any).indicators?.macd_signal);

  const indicators: Record<string, any> = {
    ...outputs,
    ...((row as any).indicators || {}),
    ...(sma20 != null ? { sma_20: sma20 } : {}),
    ...(sma50 != null ? { sma_50: sma50 } : {}),
    ...(sma200 != null ? { sma_200: sma200 } : {}),
    ...(ema20 != null ? { ema_20: ema20 } : {}),
    ...(ema50 != null ? { ema_50: ema50 } : {}),
    ...(avgVol != null ? { avg_volume_20: avgVol, avg_volume: avgVol } : {}),
    ...(rsi != null ? { rsi_14: rsi, rsi } : {}),
    ...(atr != null ? { atr } : {}),
    ...(macd != null ? { macd } : {}),
    ...(macdSignal != null ? { macd_signal: macdSignal } : {}),
    ...(closeT252 != null ? { "Close t-252": closeT252 } : {}),
  };

  const storedResults = (row.filter_results || []).filter((item) => !looksLikeAggregateSignal(item.name));
  const strategyConditions = absorbEntryConditions({ entry_conditions: scan?.entry_conditions });
  const extraFilters = (scan?.filters || []).filter((filter: IndicatorFilter) => !isAggregateSignalFilter(filter));
  const filterResults =
    storedResults.length > 0
      ? storedResults
      : strategyConditions.length > 0
        ? strategyConditions.map((name) => ({ name, passed: Boolean(row.matched) }))
        : extraFilters.map((filter) => ({
            name: filterLabel(filter),
            passed: Boolean(row.matched),
          }));
  const passed = filterResults.filter((item) => item.passed).map((item) => item.name);
  const failed = filterResults.filter((item) => !item.passed).map((item) => item.name);
  return {
    rank: 1,
    symbol: row.symbol,
    company: row.company || row.display_name || `${row.symbol} Ltd.`,
    status: row.status === "ok" ? "ok" : row.status,
    signal:
      row.signal ||
      (row.status === "insufficient_history"
        ? "SKIPPED"
        : row.status === "ok"
          ? row.matched
            ? "MATCH"
            : "REJECT"
          : "REJECT"),
    evaluation_date: row.evaluation_date || row.as_of || null,
    entry_price: row.entry_price ?? closeT252,
    exit_price: row.exit_price ?? close,
    candidate_entry_price: close,
    return_pct: returnPct,
    close,
    volume: num(row.ohlcv?.volume),
    avg_volume: avgVol,
    rsi,
    sma_20: sma20,
    sma_50: sma50,
    sma_200: sma200,
    indicators,
    high_252: num(outputs["Prior 252 High"]),
    filters_passed: passed.length,
    filters_failed: failed.length,
    passed_filters: passed,
    failed_filters: failed,
    filter_results: filterResults,
    primary_failure_reason: row.matched ? null : row.error_detail || failed[0] || "Did not match indicator filters",
    source: "indicator_scanner",
    strategy_name: row.indicator_name || scan?.indicator_name,
  } as StrategyResultRow;
}

export function mapIndicatorScanToRunStatus(scan: IndicatorScanStatus): StrategyRunStatus {
  const matched = scan.matched_count ?? 0;
  const skipped = scan.skipped_count ?? 0;
  const unmatched = Math.max(0, (scan.success_count ?? 0) - matched);
  const summary = (scan.summary && typeof scan.summary === "object" ? scan.summary : {}) as Record<string, unknown>;
  return {
    id: scan.id,
    run_id: scan.scan_id,
    strategy_name: scan.indicator_name,
    status: scan.status,
    timeframe: scan.timeframe || "1D",
    universe: scan.universe_label || `${scan.universe_size || 755} Stocks`,
    universe_size: scan.universe_size,
    progress_pct: scan.progress_pct,
    processed_count: scan.processed_count,
    total_count: scan.total_count,
    start_date: null,
    end_date: scan.as_of || null,
    initial_capital: 100000,
    buy: matched,
    watch: skipped,
    reject: unmatched,
    started_at: scan.started_at,
    completed_at: scan.completed_at,
    elapsed_seconds: scan.elapsed_seconds,
    summary: {
      universe_size: scan.universe_size,
      stocks_scanned: Number(summary.stocks_scanned ?? scan.total_count ?? 0),
      evaluated: Number(summary.evaluated ?? scan.success_count ?? 0),
      buy: matched,
      watch: skipped,
      reject: unmatched,
      insufficient_data: skipped,
      failed_validation: 0,
      errors: scan.failed_count ?? 0,
      positive_returns: Number(summary.positive_returns ?? 0),
      negative_returns: Number(summary.negative_returns ?? 0),
      flat_returns: Number(summary.flat_returns ?? 0),
      average_return: typeof summary.average_return === "number" ? summary.average_return : 0,
      scan_as_of: typeof summary.scan_as_of === "string" ? summary.scan_as_of : scan.as_of || undefined,
      top_positive: Array.isArray(summary.top_positive) ? (summary.top_positive as RankedReturn[]) : [],
      top_negative: Array.isArray(summary.top_negative) ? (summary.top_negative as RankedReturn[]) : [],
    },
    strategy_snapshot: {
      position_rules: {
        side: "LONG",
        exit_rule: "Scan only — no trade is opened",
        return_method: "(Close / Close t-252 − 1) × 100",
      },
    },
  };
}

export type ResolveTradePlanOptions = {
  stock?: StrategyResultRow | null;
  symbolDetail?: SymbolDetail | null;
  runStatus?: StrategyRunStatus | null;
  runId?: string | null;
  side?: "BUY" | "SELL";
};

export type ResolvedTradePlan = {
  signal: string;
  position: "LONG" | "SHORT";
  entryPrice: number | null;
  exitPrice: number | null;
  displayEntryPrice: number | null;
  displayExitPrice: number | null;
  stopLoss: number | null;
  target: number | null;
  riskAmount: number | null;
  riskPct: number | null;
  rewardAmount: number | null;
  rewardPct: number | null;
  isIndicatorScan: boolean;
};

export function resolveTradePlanDetails(options: ResolveTradePlanOptions): ResolvedTradePlan {
  const { stock, symbolDetail, runStatus, runId, side } = options;

  const signal = (stock?.signal || "WATCH").toUpperCase();
  const isIndicatorScan =
    (stock as any)?.source === "indicator_scanner" ||
    isIndicatorScanId(runId) ||
    isIndicatorScanId((stock as any)?.run_id);

  const positionRules = (runStatus?.strategy_snapshot as any)?.position_rules || {};
  const defaultPosition = (positionRules.side || (runStatus?.strategy_snapshot as any)?.side || "LONG").toUpperCase() as "LONG" | "SHORT";
  const position: "LONG" | "SHORT" =
    side != null
      ? side === "SELL" ? "SHORT" : "LONG"
      : defaultPosition === "SHORT" ? "SHORT" : "LONG";

  const entryPrice = stock?.entry_price ?? null;
  const exitPrice = stock?.exit_price ?? null;
  const returnPct = stock?.return_pct ?? null;

  const closePrice =
    stock?.close ??
    (stock as any)?.ohlcv?.close ??
    (stock as any)?.candidate_entry_price ??
    (isIndicatorScan ? exitPrice : null) ??
    entryPrice;

  const displayEntryPrice = isIndicatorScan ? (closePrice ?? entryPrice) : (entryPrice ?? closePrice);
  const displayExitPrice = isIndicatorScan ? (exitPrice ?? closePrice) : (exitPrice ?? closePrice);

  const recStop = ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.stop_loss;
  const isRecStopValid =
    recStop != null &&
    displayEntryPrice != null &&
    (position === "SHORT" ? recStop > displayEntryPrice : recStop < displayEntryPrice);

  const sma50Val =
    stock?.sma_50 ??
    (stock?.indicators as any)?.sma_50 ??
    (stock?.indicators as any)?.["SMA 50"];
  const atrVal =
    stock?.indicators?.atr ??
    (stock?.indicators as any)?.["ATR"];

  const derivedStopLoss =
    displayEntryPrice != null
      ? position === "SHORT"
        ? Math.round(displayEntryPrice * 1.05 * 100) / 100
        : sma50Val != null && sma50Val < displayEntryPrice
          ? Math.round(sma50Val * 100) / 100
          : atrVal != null && atrVal > 0 && displayEntryPrice - 1.5 * atrVal > 0
            ? Math.round((displayEntryPrice - 1.5 * atrVal) * 100) / 100
            : Math.round(displayEntryPrice * 0.95 * 100) / 100
      : null;

  const stopLoss =
    (stock as any)?.stop_loss ??
    (isRecStopValid ? recStop : null) ??
    derivedStopLoss ??
    null;

  const recTarget =
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.target_1 ??
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.target;
  const isRecTargetValid =
    recTarget != null &&
    displayEntryPrice != null &&
    (position === "SHORT" ? recTarget < displayEntryPrice : recTarget > displayEntryPrice);

  const derivedTarget =
    displayEntryPrice != null && stopLoss != null
      ? position === "SHORT"
        ? Math.round((displayEntryPrice - 2 * Math.abs(stopLoss - displayEntryPrice)) * 100) / 100
        : Math.round((displayEntryPrice + 2 * Math.abs(displayEntryPrice - stopLoss)) * 100) / 100
      : null;

  const target =
    (stock as any)?.target ??
    (isRecTargetValid ? recTarget : null) ??
    derivedTarget ??
    null;

  const riskAmount =
    (stock as any)?.risk ??
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.risk ??
    (displayEntryPrice != null && stopLoss != null ? Math.abs(displayEntryPrice - stopLoss) : null);

  const riskPct =
    displayEntryPrice != null && riskAmount != null && displayEntryPrice > 0
      ? (riskAmount / displayEntryPrice) * 100
      : null;

  const rewardAmount =
    (stock as any)?.reward ??
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.reward ??
    (displayEntryPrice != null && target != null ? Math.abs(target - displayEntryPrice) : null);

  const rewardPct =
    displayEntryPrice != null && rewardAmount != null && displayEntryPrice > 0
      ? (rewardAmount / displayEntryPrice) * 100
      : null;

  return {
    signal,
    position,
    entryPrice,
    exitPrice,
    displayEntryPrice,
    displayExitPrice,
    stopLoss,
    target,
    riskAmount,
    riskPct,
    rewardAmount,
    rewardPct,
    isIndicatorScan,
  };
}

