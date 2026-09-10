import React from "react";
import { Cell, Pie, PieChart } from "recharts";

interface SignalDistributionCardProps {
  buyCount?: number;
  watchCount?: number;
  rejectCount?: number;
  failedCount?: number;
  totalUniverse?: number;
  onSignalClick?: (signal: string) => void;
  labels?: {
    buy?: string;
    watch?: string;
    reject?: string;
    failed?: string;
  };
}

export const SignalDistributionCard: React.FC<SignalDistributionCardProps> = ({
  buyCount = 42,
  watchCount = 183,
  rejectCount = 530,
  failedCount = 0,
  totalUniverse = 755,
  onSignalClick,
  labels,
}) => {
  const buyLabel = labels?.buy || "BUY";
  const watchLabel = labels?.watch || "WATCH";
  const rejectLabel = labels?.reject || "REJECT";
  const failedLabel = labels?.failed || "FAILED";
  const total = buyCount + watchCount + rejectCount + failedCount || totalUniverse || 755;

  const data = [
    { name: buyLabel, value: buyCount || 1, color: "#22c55e", signal: labels?.buy ? "MATCH" : "BUY" },
    { name: watchLabel, value: watchCount || 1, color: "#eab308", signal: labels?.watch ? "SKIPPED" : "WATCH" },
    { name: rejectLabel, value: rejectCount || 1, color: "#ef4444", signal: "REJECT" },
    ...(failedCount > 0 ? [{ name: failedLabel, value: failedCount, color: "#64748b", signal: "FAILED" }] : []),
  ];

  const buyPct = total > 0 ? ((buyCount / total) * 100).toFixed(1) : "0.0";
  const watchPct = total > 0 ? ((watchCount / total) * 100).toFixed(1) : "0.0";
  const rejectPct = total > 0 ? ((rejectCount / total) * 100).toFixed(1) : "0.0";
  const failedPct = total > 0 ? ((failedCount / total) * 100).toFixed(1) : "0.0";

  return (
    <div className="st-card st-signal-dist-card" data-testid="card-signal-distribution">
      <div className="st-card-title">Signal Distribution</div>

      <div className="st-donut-container">
        {/* Donut Chart with Center Text */}
        <div className="st-donut-chart-wrap">
          <PieChart width={140} height={140}>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={46}
              outerRadius={66}
              stroke="transparent"
              paddingAngle={2}
              onClick={(entry) => onSignalClick?.(String((entry as { signal?: string }).signal || entry.name))}
              cursor="pointer"
            >
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
          </PieChart>

          <div className="st-donut-center-text">
            <span className="st-donut-center-num">{totalUniverse}</span>
            <span className="st-donut-center-sub">Total Stocks</span>
          </div>
        </div>

        {/* Legend in strict BUY -> WATCH -> REJECT -> FAILED order */}
        <div className="st-donut-legend">
          <div
            className="st-donut-legend-item"
            onClick={() => onSignalClick?.(labels?.buy ? "MATCH" : "BUY")}
            role="button"
            tabIndex={0}
            title="Filter by BUY"
          >
            <span className="st-legend-sq buy" />
            <span className="st-legend-text">
              {buyLabel}: <strong>{buyCount}</strong> ({buyPct}%)
            </span>
          </div>
          <div
            className="st-donut-legend-item"
            onClick={() => onSignalClick?.(labels?.watch ? "SKIPPED" : "WATCH")}
            role="button"
            tabIndex={0}
            title={`Filter by ${watchLabel}`}
          >
            <span className="st-legend-sq watch" />
            <span className="st-legend-text">
              {watchLabel}: <strong>{watchCount}</strong> ({watchPct}%)
            </span>
          </div>
          <div
            className="st-donut-legend-item"
            onClick={() => onSignalClick?.("REJECT")}
            role="button"
            tabIndex={0}
            title={`Filter by ${rejectLabel}`}
          >
            <span className="st-legend-sq reject" />
            <span className="st-legend-text">
              {rejectLabel}: <strong>{rejectCount}</strong> ({rejectPct}%)
            </span>
          </div>
          {failedCount > 0 ? (
            <div
              className="st-donut-legend-item"
              onClick={() => onSignalClick?.("FAILED")}
              role="button"
              tabIndex={0}
              title={`Filter by ${failedLabel}`}
            >
              <span className="st-legend-sq failed" />
              <span className="st-legend-text">
                {failedLabel}: <strong>{failedCount}</strong> ({failedPct}%)
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
