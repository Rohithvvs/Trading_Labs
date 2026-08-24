import type { ReactNode } from "react";
import { Badge } from "../design-system";
import { periodLabelFromPayload } from "../utils/backtestPeriod";
import { displayCanonicalSymbol } from "../utils/canonicalSymbol";

export type BacktestPerformanceRow = {
  rank: number;
  symbol: string;
  company_name?: string | null;
  signal: string;
  return: number | null;
  trades: number | null;
  win_rate: number | null;
  max_dd: number | null;
  profit_factor: number | null;
  profit_factor_infinite?: boolean;
  window_start?: string;
  window_end?: string;
};

type Props = {
  title: string;
  subtitle?: string;
  rows: BacktestPerformanceRow[];
  variant: "top" | "least";
  footnote?: string;
  testId?: string;
  toolbar?: ReactNode;
};

function formatPct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const pct = Number(value) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(digits)}%`;
}

function formatWinRate(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  const pct = n <= 1.0001 ? n * 100 : n;
  return `${pct.toFixed(0)}%`;
}

function formatPf(row: BacktestPerformanceRow): string {
  if (row.profit_factor_infinite) return "∞";
  if (row.profit_factor == null || Number.isNaN(Number(row.profit_factor))) return "—";
  return Number(row.profit_factor).toFixed(2);
}

function signalTone(signal: string): "buy" | "watch" | "negative" | "neutral" {
  const s = (signal || "").toUpperCase();
  if (s === "BUY") return "buy";
  if (s === "WATCH" || s === "HOLD") return "watch";
  if (s === "REJECT") return "negative";
  return "neutral";
}

function returnClass(value: number | null): string {
  if (value == null) return "";
  return value > 0 ? "bt-perf-table__num--pos" : value < 0 ? "bt-perf-table__num--neg" : "";
}

export function BacktestPerformanceTable({ title, subtitle, rows, variant, footnote, testId, toolbar }: Props) {
  return (
    <section className={`panel bt-perf-card bt-perf-card--${variant}`} data-testid={testId}>
      <header className="bt-perf-card__header">
        <div className="bt-perf-card__title-row">
          <h3 className="ds-title">{title}</h3>
          {toolbar}
        </div>
        {subtitle ? <p className="muted-copy bt-perf-card__period">{subtitle}</p> : null}
      </header>
      <div className="bt-perf-table-wrap">
        <table className="bt-perf-table">
          <thead>
            <tr>
              <th className="bt-perf-table__rank">Rank</th>
              <th className="bt-perf-table__stock bt-perf-table__symbol" style={{ minWidth: "110px" }}>Symbol</th>
              <th title="Today's scan recommendation. Independent of historical book-trade returns.">Signal</th>
              <th className="bt-perf-table__num">Return</th>
              <th className="bt-perf-table__num">Trades</th>
              <th className="bt-perf-table__num">Win rate</th>
              <th className="bt-perf-table__num">Max DD</th>
              <th className="bt-perf-table__num">PF</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((r) => (
                <tr key={r.symbol}>
                  <td className="bt-perf-table__rank">{r.rank}</td>
                  <td className="bt-perf-table__stock bt-perf-table__symbol" data-testid="backtest-symbol">
                    {displayCanonicalSymbol(r.symbol) || r.symbol || "—"}
                  </td>
                  <td>
                    <Badge tone={signalTone(r.signal)}>{r.signal || "—"}</Badge>
                  </td>
                  <td className={`bt-perf-table__num ${returnClass(r.return)}`}>{formatPct(r.return)}</td>
                  <td className="bt-perf-table__num">{r.trades ?? "—"}</td>
                  <td className="bt-perf-table__num">{formatWinRate(r.win_rate)}</td>
                  <td className={`bt-perf-table__num ${returnClass(r.max_dd)}`}>{formatPct(r.max_dd)}</td>
                  <td className="bt-perf-table__num">{formatPf(r)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={8} className="bt-perf-table__empty">
                  No completed book trades to rank for this period.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {footnote ? <p className="muted-copy bt-perf-card__foot">{footnote}</p> : null}
    </section>
  );
}

export function periodLabel(payload: Record<string, any> | null): string | undefined {
  return periodLabelFromPayload(payload);
}
