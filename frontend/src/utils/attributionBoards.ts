import {
  type AttributionPeriod,
  formatAttributionPeriod,
  periodWindowStart,
  tradeInRequestedPeriod,
} from "./attributionPeriod";
import type { BacktestPerformanceRow } from "../components/BacktestPerformanceTable";
import type { DataCoverage, UniverseAverage } from "./universeAverage";

type TradeLike = {
  symbol?: string;
  entry_date?: string;
  exit_date?: string | null;
  pnl_pct?: number | null;
  open?: boolean;
};

function isoDate(value: unknown): string | null {
  if (!value) return null;
  const text = String(value).slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : null;
}

function compoundReturns(pnls: number[]): number {
  let net = 1;
  for (const r of pnls) net *= 1 + r;
  return net - 1;
}

function inRequestedPeriod(entry: string, start: string, end: string): boolean {
  return tradeInRequestedPeriod(entry, start, end);
}

type NameReport = {
  symbol: string;
  company_name?: string | null;
  signal: string;
  net_return: number;
  trades: number;
  win_rate: number;
  max_dd: number;
  profit_factor: number | null;
  profit_factor_infinite: boolean;
};

function reportsFromBlotter(
  payload: Record<string, any>,
  start: string,
  end: string,
): NameReport[] {
  const recs = Array.isArray(payload.recommendations) ? payload.recommendations : [];
  const failed = new Set<string>();
  const signals = new Map<string, string>();
  const compNames = new Map<string, string>();
  for (const row of recs) {
    const symbol = String(row?.symbol || "").toUpperCase();
    if (!symbol) continue;
    signals.set(symbol, String(row?.signal || "REJECT"));
    if (row?.company_name) compNames.set(symbol, String(row.company_name));
    const bt = row?.backtest_1y || {};
    if (bt.failed || row?.first_failure === "data_source_failure") failed.add(symbol);
  }

  const bySym = new Map<string, number[]>();
  for (const raw of (payload.blotter || []) as TradeLike[]) {
    const symbol = String(raw?.symbol || "").toUpperCase();
    if (!symbol || failed.has(symbol)) continue;
    const entry = isoDate(raw.entry_date);
    if (!entry || !inRequestedPeriod(entry, start, end)) continue;
    if (raw.pnl_pct == null || Number.isNaN(Number(raw.pnl_pct))) continue;
    const list = bySym.get(symbol) || [];
    list.push(Number(raw.pnl_pct));
    bySym.set(symbol, list);
  }

  const reports: NameReport[] = [];
  for (const [symbol, rets] of bySym) {
    if (!rets.length) continue;
    const wins = rets.filter((r) => r > 0);
    const losses = rets.filter((r) => r <= 0);
    let profitFactor: number | null = null;
    let infinite = false;
    if (losses.length) {
      const lossAbs = Math.abs(losses.reduce((s, n) => s + n, 0));
      profitFactor = lossAbs ? wins.reduce((s, n) => s + n, 0) / lossAbs : 0;
    } else if (wins.length) {
      infinite = true;
    }
    reports.push({
      symbol,
      company_name: compNames.get(symbol) || null,
      signal: signals.get(symbol) || "REJECT",
      net_return: compoundReturns(rets),
      trades: rets.length,
      win_rate: wins.length / rets.length,
      max_dd: rets.filter((r) => r < 0).reduce((m, r) => Math.min(m, r), 0),
      profit_factor: profitFactor,
      profit_factor_infinite: infinite,
    });
  }
  return reports;
}

function toRow(rank: number, rep: NameReport, start: string, end: string): BacktestPerformanceRow {
  return {
    rank,
    symbol: rep.symbol,
    company_name: rep.company_name,
    signal: rep.signal,
    return: rep.net_return,
    trades: rep.trades,
    win_rate: rep.win_rate,
    max_dd: rep.max_dd,
    profit_factor: rep.profit_factor,
    profit_factor_infinite: rep.profit_factor_infinite,
    window_start: start,
    window_end: end,
  };
}

function buildBoards(reports: NameReport[], start: string, end: string, topN = 5) {
  const positive = reports.filter((r) => r.net_return > 0).sort((a, b) => {
    if (b.net_return !== a.net_return) return b.net_return - a.net_return;
    return a.symbol.localeCompare(b.symbol);
  });
  const least = [...reports].sort((a, b) => {
    if (a.net_return !== b.net_return) return a.net_return - b.net_return;
    return a.symbol.localeCompare(b.symbol);
  });
  return {
    top5: positive.slice(0, topN).map((r, i) => toRow(i + 1, r, start, end)),
    least5: least.slice(0, topN).map((r, i) => toRow(i + 1, r, start, end)),
  };
}

function coverageFromCurve(payload: Record<string, any>, start: string, end: string): DataCoverage {
  const dates = ((payload.equity_curve || []) as { date?: string; label?: string }[])
    .map((p) => isoDate(p.date || p.label))
    .filter((d): d is string => Boolean(d))
    .sort();
  const ohlcvStart = dates[0] || payload.data_coverage?.ohlcv_start || null;
  const ohlcvEnd = dates[dates.length - 1] || payload.data_coverage?.ohlcv_end || end;
  return {
    requested_start: start,
    requested_end: end,
    ohlcv_start: ohlcvStart,
    ohlcv_end: ohlcvEnd,
    sessions: dates.length || payload.data_coverage?.sessions || null,
    complete_3y: Boolean(ohlcvStart && ohlcvStart <= start),
  };
}

export type AttributionView = {
  period: AttributionPeriod;
  windowStart: string;
  windowEnd: string;
  periodLabel: string;
  top5: BacktestPerformanceRow[];
  least5: BacktestPerformanceRow[];
  average: UniverseAverage | null;
  coverage: DataCoverage | null;
};

export function resolveAttributionView(
  payload: Record<string, any> | null | undefined,
  period: AttributionPeriod,
): AttributionView | null {
  if (!payload) return null;
  const asof =
    isoDate(payload.evaluation_date) ||
    isoDate(payload.attribution_window_end) ||
    isoDate(payload.universe_average?.window_end);
  if (!asof) {
    if (period === "3Y" && (payload.top5_positive || payload.universe_average)) {
      const start = isoDate(payload.attribution_window_start) || isoDate(payload.universe_average?.window_start) || "";
      const end = isoDate(payload.attribution_window_end) || isoDate(payload.universe_average?.window_end) || "";
      return {
        period,
        windowStart: start,
        windowEnd: end,
        periodLabel: start && end ? formatAttributionPeriod(start, end, period) : "",
        top5: payload.top5_positive || [],
        least5: payload.least5 || [],
        average: payload.universe_average || null,
        coverage: payload.data_coverage || null,
      };
    }
    return null;
  }

  const start = periodWindowStart(asof, period);
  const blotter = Array.isArray(payload.blotter) ? payload.blotter : [];
  const reports = blotter.length ? reportsFromBlotter(payload, start, asof) : [];
  const boards = buildBoards(reports, start, asof);
  const recs = Array.isArray(payload.recommendations) ? payload.recommendations : [];
  const universe =
    recs.length ||
    Number(payload.summary?.total) ||
    Number(payload.summary?.evaluated) ||
    Number(payload.universe_average?.universe_size) ||
    755;
  const validN = reports.length;
  const computedAvg: UniverseAverage = {
    strategy_id: payload.strategy_id,
    window: period,
    window_start: start,
    window_end: asof,
    universe_size: universe,
    valid_backtests: validN,
    unavailable: Math.max(universe - validN, 0),
    average_return: validN ? reports.reduce((s, r) => s + r.net_return, 0) / validN : null,
    trade_count: reports.reduce((s, r) => s + r.trades, 0),
  };

  const usePayloadBoards = period === "3Y" && (payload.top5_positive || payload.least5) && !blotter.length;
  const usePayloadAvg = period === "3Y" && payload.universe_average?.window === "3Y";

  return {
    period,
    windowStart: usePayloadAvg ? payload.universe_average.window_start : start,
    windowEnd: usePayloadAvg ? payload.universe_average.window_end : asof,
    periodLabel: formatAttributionPeriod(
      usePayloadAvg ? payload.universe_average.window_start : start,
      usePayloadAvg ? payload.universe_average.window_end : asof,
      period,
    ),
    top5: usePayloadBoards ? payload.top5_positive || [] : boards.top5,
    least5: usePayloadBoards ? payload.least5 || [] : boards.least5,
    average: usePayloadAvg ? (payload.universe_average as UniverseAverage) : computedAvg,
    coverage: payload.data_coverage || coverageFromCurve(payload, start, asof),
  };
}
