import React from "react";
import { Cell, Pie, PieChart } from "recharts";

interface SignalDistributionCardProps {
  buyCount?: number;
  watchCount?: number;
  rejectCount?: number;
  failedCount?: number;
  totalUniverse?: number;
  onSignalClick?: (signal: string) => void;
}

export const SignalDistributionCard: React.FC<SignalDistributionCardProps> = ({
  buyCount = 42,
  watchCount = 183,
  rejectCount = 530,
  failedCount = 0,
  totalUniverse = 755,
  onSignalClick,
}) => {
  const total = buyCount + watchCount + rejectCount + failedCount || totalUniverse || 755;

  // Strict order: BUY -> WATCH -> REJECT -> FAILED
  const data = [
    { name: "BUY", value: buyCount || 1, color: "#22c55e" },
    { name: "WATCH", value: watchCount || 1, color: "#eab308" },
    { name: "REJECT", value: rejectCount || 1, color: "#ef4444" },
    ...(failedCount > 0 ? [{ name: "FAILED", value: failedCount, color: "#64748b" }] : []),
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
              onClick={(entry) => onSignalClick?.(String(entry.name))}
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
            onClick={() => onSignalClick?.("BUY")}
            role="button"
            tabIndex={0}
            title="Filter by BUY"
          >
            <span className="st-legend-sq buy" />
            <span className="st-legend-text">
              BUY: <strong>{buyCount}</strong> ({buyPct}%)
            </span>
          </div>
          <div
            className="st-donut-legend-item"
            onClick={() => onSignalClick?.("WATCH")}
            role="button"
            tabIndex={0}
            title="Filter by WATCH"
          >
            <span className="st-legend-sq watch" />
            <span className="st-legend-text">
              WATCH: <strong>{watchCount}</strong> ({watchPct}%)
            </span>
          </div>
          <div
            className="st-donut-legend-item"
            onClick={() => onSignalClick?.("REJECT")}
            role="button"
            tabIndex={0}
            title="Filter by REJECT"
          >
            <span className="st-legend-sq reject" />
            <span className="st-legend-text">
              REJECT: <strong>{rejectCount}</strong> ({rejectPct}%)
            </span>
          </div>
          {failedCount > 0 ? (
            <div
              className="st-donut-legend-item"
              onClick={() => onSignalClick?.("FAILED")}
              role="button"
              tabIndex={0}
              title="Filter by FAILED"
            >
              <span className="st-legend-sq failed" />
              <span className="st-legend-text">
                FAILED: <strong>{failedCount}</strong> ({failedPct}%)
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
