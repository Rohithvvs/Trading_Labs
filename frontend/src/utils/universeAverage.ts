export type UniverseAverage = {
  strategy_id?: string;
  window: string;
  window_start: string;
  window_end: string;
  universe_size: number;
  valid_backtests: number;
  unavailable: number;
  average_return: number | null;
  trade_count?: number;
};

export type DataCoverage = {
  requested_start: string;
  requested_end: string;
  ohlcv_start?: string | null;
  ohlcv_end?: string | null;
  sessions?: number | null;
  complete_3y?: boolean;
};

function isoDate(value: unknown): string | null {
  if (!value) return null;
  const text = String(value).slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : null;
}

export function windowStartIso(end: string, years: number): string {
  const [y, m, d] = end.split("-").map(Number);
  const start = new Date(Date.UTC(y - years, (m || 1) - 1, d || 1));
  return start.toISOString().slice(0, 10);
}

function compoundReturns(pnls: number[]): number {
  let net = 1;
  for (const r of pnls) net *= 1 + r;
  return net - 1;
}

function coverageFromCurve(payload: Record<string, any>, start: string, end: string): DataCoverage {
  const dates = ((payload.equity_curve || []) as { date?: string; label?: string }[])
    .map((p) => isoDate(p.date || p.label))
    .filter((d): d is string => Boolean(d))
    .sort();
  const ohlcvStart = dates[0] || null;
  const ohlcvEnd = dates[dates.length - 1] || end;
  return {
    requested_start: start,
    requested_end: end,
    ohlcv_start: ohlcvStart,
    ohlcv_end: ohlcvEnd,
    sessions: dates.length || null,
    complete_3y: Boolean(ohlcvStart && ohlcvStart <= start),
  };
}

/** 3Y average of valid per-name book returns. Missing names are omitted, not 0%. */
export function resolveUniverseAverage(payload: Record<string, any> | null | undefined): {
  average: UniverseAverage | null;
  coverage: DataCoverage | null;
} {
  if (!payload) return { average: null, coverage: null };
  const recs = Array.isArray(payload.recommendations) ? payload.recommendations : [];
  const asof =
    isoDate(payload.attribution_window_end) ||
    isoDate(payload.evaluation_date) ||
    isoDate(payload.universe_average?.window_end);
  if (!asof) {
    if (payload.universe_average) {
      return { average: payload.universe_average as UniverseAverage, coverage: payload.data_coverage || null };
    }
    return { average: null, coverage: null };
  }
  const start = isoDate(payload.attribution_window_start) || windowStartIso(asof, 3);
  const blotter = Array.isArray(payload.blotter) ? payload.blotter : [];
  const bySym = new Map<string, number[]>();
  for (const t of blotter) {
    const symbol = String(t?.symbol || "").toUpperCase();
    if (!symbol) continue;
    const entry = isoDate(t.entry_date);
    if (!entry || entry < start || entry > asof) continue;
    const pnl = t.pnl_pct;
    if (pnl == null || Number.isNaN(Number(pnl))) continue;
    const list = bySym.get(symbol) || [];
    list.push(Number(pnl));
    bySym.set(symbol, list);
  }

  const valid: number[] = [];
  if (bySym.size) {
    for (const pnls of bySym.values()) valid.push(compoundReturns(pnls));
  } else {
    for (const row of recs) {
      const bt = row?.backtest_1y || {};
      if (bt.failed || bt.net_return == null || Number.isNaN(Number(bt.net_return))) continue;
      valid.push(Number(bt.net_return));
    }
  }

  const universe =
    recs.length ||
    Number(payload.summary?.total) ||
    Number(payload.summary?.evaluated) ||
    Number(payload.universe_average?.universe_size) ||
    755;
  const validN = valid.length;
  const computed: UniverseAverage = {
    strategy_id: payload.strategy_id,
    window: "3Y",
    window_start: start,
    window_end: asof,
    universe_size: universe,
    valid_backtests: validN,
    unavailable: Math.max(universe - validN, 0),
    average_return: validN ? valid.reduce((sum, n) => sum + n, 0) / validN : null,
  };
  const coverage = payload.data_coverage || coverageFromCurve(payload, start, asof);
  if (payload.universe_average && payload.universe_average.window === "3Y") {
    return { average: payload.universe_average as UniverseAverage, coverage };
  }
  return { average: computed, coverage };
}
