import type { IndicatorFilter, IndicatorScanRow, IndicatorScanStatus } from "../api_indicator_scanner";
import type { RankedReturn, StrategyResultRow, StrategyRunStatus } from "../api_strategy_tester";
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
  const closeT252 = num(outputs["Close t-252"]);
  const momentum = num(outputs["Momentum 252"]);
  const returnPct =
    row.return_pct != null
      ? row.return_pct
      : momentum != null
        ? momentum * 100
        : close != null && closeT252
          ? (close / closeT252 - 1) * 100
          : 0;
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
    return_pct: returnPct,
    close,
    volume: num(row.ohlcv?.volume),
    avg_volume: null,
    rsi: null,
    sma_20: null,
    sma_50: null,
    sma_200: null,
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
