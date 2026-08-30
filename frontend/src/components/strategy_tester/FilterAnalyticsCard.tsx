import React from "react";
import type { FilterStat } from "../../api_strategy_tester";

interface FilterAnalyticsCardProps {
  stats?: FilterStat[];
  totalUniverse: number;
}

const FALLBACK_STATS: FilterStat[] = [
  { filter_id: "1", label: "Close > SMA 50", filter_name: "Close > SMA 50", passed: 420, failed: 335, pass_pct: 55.6, fail_pct: 44.4, pass_rate: 55.6, fail_rate: 44.4 },
  { filter_id: "2", label: "SMA 50 > SMA 200", filter_name: "SMA 50 > SMA 200", passed: 310, failed: 445, pass_pct: 41.1, fail_pct: 58.9, pass_rate: 41.1, fail_rate: 58.9 },
  { filter_id: "3", label: "RSI > 55", filter_name: "RSI > 55", passed: 280, failed: 475, pass_pct: 37.1, fail_pct: 62.9, pass_rate: 37.1, fail_rate: 62.9 },
  { filter_id: "4", label: "Volume > Avg Volume", filter_name: "Volume > Avg Volume", passed: 195, failed: 560, pass_pct: 25.8, fail_pct: 74.2, pass_rate: 25.8, fail_rate: 74.2 },
];

export const FilterAnalyticsCard: React.FC<FilterAnalyticsCardProps> = ({
  stats,
  totalUniverse = 755,
}) => {
  const displayStats = stats && stats.length > 0 ? stats : FALLBACK_STATS;

  return (
    <div className="st-card" data-testid="card-filter-analytics">
      <div className="st-card-title">Filter Analytics (Independent)</div>

      <table className="st-micro-table">
        <thead>
          <tr>
            <th>Filter</th>
            <th style={{ textAlign: "right" }}>Passed</th>
            <th style={{ textAlign: "right" }}>Failed</th>
            <th style={{ textAlign: "right" }}>Pass %</th>
            <th style={{ textAlign: "right" }}>Fail %</th>
          </tr>
        </thead>
        <tbody>
          {displayStats.map((stat, idx) => {
            const passRate = Number(stat.pass_pct ?? stat.pass_rate ?? 0);
            const failRate = Number(stat.fail_pct ?? stat.fail_rate ?? 0);
            return (
            <tr key={stat.filter_id || idx}>
              <td style={{ color: "#e2e8f0", fontWeight: 500 }}>
                {stat.label || stat.filter_name || `Filter ${idx + 1}`}
              </td>
              <td style={{ textAlign: "right", color: "#f1f5f9" }}>{stat.passed}</td>
              <td style={{ textAlign: "right", color: "#f1f5f9" }}>{stat.failed}</td>
              <td style={{ textAlign: "right", color: "#4ade80", fontWeight: 600 }}>
                {passRate.toFixed(1)}%
              </td>
              <td style={{ textAlign: "right", color: "#f87171", fontWeight: 600 }}>
                {failRate.toFixed(1)}%
              </td>
            </tr>
            );
          })}
          {/* Total Row */}
          <tr style={{ borderTop: "1px solid #1e293b", fontWeight: 700 }}>
            <td style={{ color: "#ffffff" }}>Total</td>
            <td style={{ textAlign: "right", color: "#ffffff" }}>{totalUniverse}</td>
            <td style={{ textAlign: "right", color: "#ffffff" }}>{totalUniverse}</td>
            <td style={{ textAlign: "right", color: "#ffffff" }}>100%</td>
            <td style={{ textAlign: "right", color: "#ffffff" }}>100%</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};
