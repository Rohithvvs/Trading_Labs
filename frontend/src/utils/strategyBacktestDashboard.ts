import type { CandidateRow } from "../types";
import type {
  BacktestDashboardModel,
  BacktestRange,
  DashboardTrade,
} from "../components/BacktestAnalyticsDashboard";

function yearsAgo(range: BacktestRange): Date {
  const d = new Date();
  if (range === "1Y") d.setFullYear(d.getFullYear() - 1);
  else if (range === "3Y") d.setFullYear(d.getFullYear() - 3);
  else if (range === "5Y") d.setFullYear(d.getFullYear() - 5);
  else if (range === "8Y") d.setFullYear(d.getFullYear() - 8);
  else d.setFullYear(1970);
  return d;
}

export function asDashboardTrade(raw: any): DashboardTrade {
  const pnl =
    raw?.pnl_percent ??
    (raw?.pnl_pct != null ? Number(raw.pnl_pct) * (Math.abs(Number(raw.pnl_pct)) <= 2 ? 100 : 1) : null);
  return {
    trade_id: raw?.trade_id ?? null,
    entry_date: raw?.entry_date ?? null,
    exit_date: raw?.exit_date ?? null,
    type: raw?.type ?? raw?.direction ?? "LONG",
    entry_price: raw?.entry_price ?? null,
    exit_price: raw?.exit_price ?? null,
    pnl_percent: pnl,
    holding_days: raw?.holding_days ?? raw?.holding_period ?? null,
    reason: raw?.reason ?? raw?.exit_reason ?? null,
    exit_reason: raw?.exit_reason ?? raw?.reason ?? null,
    open: Boolean(raw?.open),
    outcome: raw?.outcome ?? null,
    net_pnl: raw?.net_pnl ?? null,
    commission: raw?.commission ?? null,
    slippage: raw?.slippage ?? null,
    signal_time: raw?.signal_time ?? null,
    entry_fill_time: raw?.entry_fill_time ?? null,
    exit_fill_time: raw?.exit_fill_time ?? null,
  };
}

function decToPct(value: unknown): number | null {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
  return Number(value) * 100;
}

function isCompleteDashboard(dash: unknown): dash is BacktestDashboardModel {
  if (!dash || typeof dash !== "object") return false;
  const d = dash as Record<string, unknown>;
  return d.trade_count != null || d.total_return != null || d.never_selected_in_window === true;
}

function lastEquity(curve: { equity?: number }[] | undefined): number | null {
  if (!Array.isArray(curve) || !curve.length) return null;
  const v = Number(curve[curve.length - 1]?.equity);
  return Number.isFinite(v) ? v : null;
}

/** True when the dashboard curve is the shared book series, not this name. */
export function looksLikeBookCurve(
  dashCurve: { equity?: number }[] | undefined,
  bookCurve: { equity?: number }[] | undefined,
): boolean {
  if (!Array.isArray(dashCurve) || !dashCurve.length) return false;
  if (!Array.isArray(bookCurve) || !bookCurve.length) return false;
  if (dashCurve.length !== bookCurve.length) return false;
  const a0 = Number(dashCurve[0]?.equity);
  const b0 = Number(bookCurve[0]?.equity);
  const a1 = Number(dashCurve[dashCurve.length - 1]?.equity);
  const b1 = Number(bookCurve[bookCurve.length - 1]?.equity);
  return a0 === b0 && a1 === b1;
}

export function equityCurveFromTrades(
  trades: DashboardTrade[],
  range: BacktestRange,
  initial: number,
): { date: string; label: string; equity: number }[] {
  const cutoff = yearsAgo(range);
  const events = trades
    .map((t) => ({
      date: String(t.exit_date || t.entry_date || ""),
      pnl: t.pnl_percent == null ? null : Number(t.pnl_percent) / 100,
    }))
    .filter((e) => e.date && e.pnl != null && !Number.isNaN(e.pnl) && new Date(e.date) >= cutoff)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (!events.length) return [];
  let equity = initial;
  const curve: { date: string; label: string; equity: number }[] = [];
  for (const e of events) {
    equity *= 1 + (e.pnl as number);
    curve.push({ date: e.date, label: e.date, equity: Number(equity.toFixed(4)) });
  }
  return curve;
}

function tradesForSymbol(pool: any[], symbol: string): DashboardTrade[] {
  const want = symbol.toUpperCase();
  const seen = new Set<string>();
  const out: DashboardTrade[] = [];
  for (const raw of pool) {
    const s = String(raw?.symbol || "").toUpperCase();
    if (s !== want) continue;
    const key = `${raw?.entry_date ?? ""}|${raw?.exit_date ?? ""}|${raw?.entry_price ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(asDashboardTrade(raw));
  }
  return out;
}

function withDerivedSeries(
  model: BacktestDashboardModel,
  equity: { date: string; label: string; equity: number }[],
  trades: DashboardTrade[],
): BacktestDashboardModel {
  let peak = -Infinity;
  const drawdown_curve = equity.map((p) => {
    peak = Math.max(peak, p.equity);
    const dd = peak ? ((p.equity - peak) / Math.abs(peak)) * 100 : 0;
    return { date: p.date, label: p.label, drawdown: Number(dd.toFixed(4)) };
  });
  const monthlyMap: Record<string, number[]> = {};
  for (const p of equity) {
    const m = p.date.slice(0, 7);
    if (m.length < 7) continue;
    (monthlyMap[m] ||= []).push(p.equity);
  }
  const months = Object.keys(monthlyMap).sort();
  let prev = equity[0]?.equity;
  const monthly_returns = months.map((month) => {
    const end = monthlyMap[month][monthlyMap[month].length - 1];
    const ret = prev ? end / prev - 1 : null;
    prev = end;
    return { month, return: ret };
  });
  const winners = trades
    .filter((t) => (t.pnl_percent ?? 0) > 0)
    .sort((a, b) => (b.pnl_percent ?? 0) - (a.pnl_percent ?? 0));
  const losers = trades
    .filter((t) => (t.pnl_percent ?? 0) < 0)
    .sort((a, b) => (a.pnl_percent ?? 0) - (b.pnl_percent ?? 0));
  return {
    ...model,
    equity_curve: equity,
    drawdown_curve,
    monthly_returns,
    trades,
    best_trade: winners[0] ?? null,
    worst_trade: losers[0] ?? null,
    top_winning: winners.slice(0, 5),
    top_losing: losers.slice(0, 5),
    trade_count: trades.length,
    never_selected_in_window: trades.length === 0,
    period_start: equity[0]?.date ?? model.period_start,
    period_end: equity[equity.length - 1]?.date ?? model.period_end,
    ending_capital: equity.length ? equity[equity.length - 1].equity : model.ending_capital,
    avg_trade_return: trades.length
      ? trades.reduce((s, t) => s + (t.pnl_percent ?? 0), 0) / trades.length
      : model.avg_trade_return,
  };
}

export function isSymbolWindowReplay(
  dash: Record<string, any> | null | undefined,
  symbol: string,
  range: BacktestRange,
): boolean {
  if (!dash || typeof dash !== "object") return false;
  const dashSym = String(dash.symbol || "").toUpperCase();
  if (dashSym && dashSym !== symbol.toUpperCase()) return false;
  if (dash.replay_kind !== "symbol_window") return false;
  if (range !== "CUSTOM" && dash.window && String(dash.window).toUpperCase() !== range) return false;
  if (range === "CUSTOM" && dash.window && String(dash.window).toUpperCase() !== "CUSTOM") return false;
  if (dash.unavailable_reason === "insufficient_history") return true;
  return isCompleteDashboard(dash) && Array.isArray(dash.equity_curve) && dash.equity_curve.length > 1;
}

/**
 * Accept only a symbol-stamped window replay. Never rebuild from the scan book.
 */
export function hydrateStrategyBacktest(
  row: CandidateRow | undefined,
  range: BacktestRange,
  api?: Record<string, any> | null,
): BacktestDashboardModel | null {
  if (!row?.symbol) return null;
  const dashRaw = api?.dashboard && typeof api.dashboard === "object" ? (api.dashboard as Record<string, any>) : null;
  if (row.w52 && !isSymbolWindowReplay(dashRaw, row.symbol, range)) return null;
  if (!row.w52 && !isCompleteDashboard(dashRaw)) return null;
  if (!dashRaw) return null;
  const model = { ...(dashRaw as BacktestDashboardModel) };
  if (model.initial_capital != null && model.ending_capital != null && model.total_return == null) {
    const initial = Number(model.initial_capital);
    const ending = Number(model.ending_capital);
    if (initial > 0) model.total_return = ((ending - initial) / initial) * 100;
  }
  return model;
}

export function lastCurveEquity(curve: { equity?: number }[] | undefined): number | null {
  return lastEquity(curve);
}
