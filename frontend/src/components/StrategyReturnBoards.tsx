import { useState } from "react";

import { resolveAttributionView } from "../utils/attributionBoards";
import { DEFAULT_ATTRIBUTION_PERIOD, type AttributionPeriod } from "../utils/attributionPeriod";
import { AttributionPeriodTabs } from "./AttributionPeriodTabs";
import { BacktestPerformanceTable } from "./BacktestPerformanceTable";
import { StrategyAverageReturn } from "./StrategyAverageReturn";

export function StrategyReturnBoards({
  payload,
  displayName,
  testId,
  averageTestId,
  footnoteStrategy,
}: {
  payload: Record<string, any> | null;
  displayName: string;
  testId: string;
  averageTestId: string;
  footnoteStrategy: string;
}) {
  const [period, setPeriod] = useState<AttributionPeriod>(DEFAULT_ATTRIBUTION_PERIOD);
  if (!payload?.recommendations_final) return null;
  const view = resolveAttributionView(payload, period);
  const tabs = (
    <AttributionPeriodTabs
      value={period}
      onChange={setPeriod}
      ariaLabel={`${displayName} attribution period`}
    />
  );
  const subtitle = view?.periodLabel;
  return (
    <div data-testid={testId} className="bt-perf-stack">
      <BacktestPerformanceTable
        title="Top 5 positive backtest returns"
        subtitle={subtitle}
        rows={view?.top5 || []}
        variant="top"
        toolbar={tabs}
        footnote={`Ranked by real ${footnoteStrategy} book trades opened in the selected period. Signal is today's scan recommendation (BUY / HOLD / WATCH / REJECT), independent of historical returns. Never-selected names are omitted.`}
      />
      <BacktestPerformanceTable
        title="Least 5 backtest returns"
        subtitle={subtitle}
        rows={view?.least5 || []}
        variant="least"
        toolbar={tabs}
        footnote={`Worst book-trade results for this strategy over the selected window. Signal is today's scan recommendation, not a backtest outcome. Never-selected names are omitted.`}
      />
      <StrategyAverageReturn
        payload={payload}
        displayName={displayName}
        testId={averageTestId}
        periodKey={period}
        average={view?.average}
        coverage={view?.coverage}
        periodLabel={subtitle}
        toolbar={tabs}
      />
    </div>
  );
}
