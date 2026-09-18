import type { ReactNode } from "react";
import type { AttributionPeriod } from "../utils/attributionPeriod";
import { periodNoun } from "../utils/attributionPeriod";
import { formatCompletedSessionPeriod } from "../utils/backtestPeriod";
import type { DataCoverage, UniverseAverage } from "../utils/universeAverage";
import { resolveUniverseAverage } from "../utils/universeAverage";

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "Unavailable";
  const pct = Number(value) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

export function StrategyAverageReturn({
  payload,
  displayName,
  testId = "strategy-average-return",
  periodKey = "3Y",
  average,
  coverage: coverageProp,
  periodLabel,
  toolbar,
}: {
  payload: Record<string, any> | null;
  displayName: string;
  testId?: string;
  periodKey?: AttributionPeriod;
  average?: UniverseAverage | null;
  coverage?: DataCoverage | null;
  periodLabel?: string;
  toolbar?: ReactNode;
}) {
  const resolved = average ? { average, coverage: coverageProp || null } : resolveUniverseAverage(payload);
  const avg = resolved.average;
  if (!avg) return null;
  const period = periodLabel || formatCompletedSessionPeriod(avg.window_start, avg.window_end, periodKey === "3Y" ? 3 : undefined);
  const coverage = resolved.coverage;
  const incomplete = Boolean(coverage?.ohlcv_start && avg.window_start && coverage.ohlcv_start > avg.window_start);
  const coverageNote =
    incomplete && coverage?.ohlcv_start
      ? `Stock OHLCV available ${coverage.ohlcv_start} → ${coverage.ohlcv_end || avg.window_end}. Bars before ${coverage.ohlcv_start} are not in the store.`
      : null;
  const tone =
    avg.average_return == null
      ? ""
      : avg.average_return > 0
        ? "bt-perf-table__num--pos"
        : avg.average_return < 0
          ? "bt-perf-table__num--neg"
          : "";

  return (
    <section className="panel bt-perf-card" data-testid={testId}>
      <header className="bt-perf-card__header">
        <div className="bt-perf-card__title-row">
          <h3 className="ds-title">{displayName} — Average Return</h3>
          {toolbar}
        </div>
        <p className="muted-copy bt-perf-card__period">
          Average {periodNoun(periodKey)} backtest return across all {avg.universe_size ?? 755} universe stocks
        </p>
        {period ? <p className="muted-copy bt-perf-card__period">{period}</p> : null}
      </header>
      <div className="w52-avg">
        <p className={`w52-avg__value ${tone}`} data-testid={`${testId}-value`}>
          {formatPct(avg.average_return)}
        </p>
        <dl className="w52-avg__meta">
          <div>
            <dt>Stocks Evaluated</dt>
            <dd>{avg.universe_size ?? "—"}</dd>
          </div>
          <div>
            <dt>Valid Backtests</dt>
            <dd>{avg.valid_backtests ?? "—"}</dd>
          </div>
          <div>
            <dt>Unavailable</dt>
            <dd>{avg.unavailable ?? "—"}</dd>
          </div>
          <div>
            <dt>Backtest Period</dt>
            <dd>{avg.window_start && avg.window_end ? `${avg.window_start} → ${avg.window_end}` : "—"}</dd>
          </div>
        </dl>
      </div>
      <p className="muted-copy bt-perf-card__foot">
        Average of names with a valid {avg.window || periodKey} book-trade return. Missing or failed backtests are omitted, not treated as 0%.
        {coverageNote ? ` ${coverageNote}` : ""}
      </p>
    </section>
  );
}
