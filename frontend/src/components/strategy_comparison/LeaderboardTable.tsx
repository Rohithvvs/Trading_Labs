import { SLOT_COLORS } from "./ComparisonCharts";
import { buildLeaderboard, LEADERBOARD_NOTE, type LeaderboardRow } from "./leaderboardModel";
import type { ComparisonPayload } from "../../api_strategy_comparison";

type Props = {
  comparison: ComparisonPayload;
  highlight: boolean;
};

function fmtNum(value: number | null | undefined, digits = 2, minDigits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: minDigits });
}

function fmtPct(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

function fmtInr(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function signed(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "";
  if (value > 0) return "sc-pos";
  if (value < 0) return "sc-neg";
  return "";
}

function metricOf(row: LeaderboardRow, key: string): number | null {
  switch (key) {
    case "score":
      return row.score;
    case "trades":
      return row.trades;
    case "winRate":
      return row.winRate;
    case "pf":
      return row.profitFactor;
    case "avgTrade":
      return row.avgTrade;
    case "cagr":
      return row.cagr;
    case "totalReturn":
      return row.totalReturn;
    case "maxDd":
      return row.maxDd;
    case "calmar":
      return row.calmar;
    default:
      return null;
  }
}

function bestIndexes(rows: LeaderboardRow[], key: string, higher: boolean): Set<number> {
  const present = rows
    .map((row, index) => {
      const value = metricOf(row, key);
      return value == null || Number.isNaN(value) ? null : { index, value };
    })
    .filter((item): item is { index: number; value: number } => item != null);
  if (present.length < 2) return new Set();
  const target = higher ? Math.max(...present.map((item) => item.value)) : Math.min(...present.map((item) => item.value));
  const hits = present.filter((item) => item.value === target).map((item) => item.index);
  if (hits.length === present.length) return new Set();
  return new Set(hits);
}

const COLUMNS: Array<{
  key: string;
  label: string;
  higher?: boolean;
  className?: string;
  render: (row: LeaderboardRow) => string;
  valueClass?: (row: LeaderboardRow) => string;
}> = [
  { key: "rank", label: "Rank", className: "sc-lb-sticky sc-lb-sticky--rank", render: (row) => String(row.rank) },
  { key: "strategy", label: "Strategy", className: "sc-lb-sticky sc-lb-sticky--name", render: (row) => row.slot.strategy_name },
  { key: "score", label: "Score", higher: true, render: (row) => (row.score == null ? "—" : row.score.toFixed(1)) },
  { key: "grade", label: "Grade", render: (row) => row.grade || "—" },
  { key: "trades", label: "Trades", higher: true, render: (row) => fmtNum(row.trades, 0) },
  { key: "winRate", label: "Win Rate", higher: true, render: (row) => fmtPct(row.winRate), valueClass: (row) => signed(row.winRate) },
  { key: "pf", label: "PF", higher: true, render: (row) => fmtNum(row.profitFactor, 2, 2) },
  {
    key: "avgTrade",
    label: "Avg Trade",
    higher: true,
    render: (row) => (row.avgTradeUnit === "pct" ? fmtPct(row.avgTrade) : fmtNum(row.avgTrade)),
    valueClass: (row) => signed(row.avgTrade),
  },
  { key: "cagr", label: "CAGR", higher: true, render: (row) => fmtPct(row.cagr), valueClass: (row) => signed(row.cagr) },
  { key: "totalReturn", label: "Total Return", higher: true, render: (row) => fmtPct(row.totalReturn), valueClass: (row) => signed(row.totalReturn) },
  {
    key: "maxDd",
    label: "Max DD",
    higher: false,
    render: (row) => (row.slot.metrics.max_drawdown_pct != null ? fmtPct(row.maxDd) : fmtInr(row.maxDd)),
    valueClass: (row) => (row.maxDd == null ? "" : "sc-neg"),
  },
  { key: "calmar", label: "Calmar", higher: true, render: (row) => fmtNum(row.calmar, 2, 2) },
  { key: "avgCash", label: "Avg Cash", render: (row) => fmtInr(row.avgCash) },
  { key: "avgExposure", label: "Avg Exposure", render: (row) => fmtPct(row.avgExposure, 1) },
  { key: "bestTrade", label: "Best Trade", className: "sc-lb-wide", render: (row) => row.bestTrade, valueClass: (row) => (row.bestTrade === "—" ? "" : "sc-pos") },
  { key: "worstTrade", label: "Worst Trade", className: "sc-lb-wide", render: (row) => row.worstTrade, valueClass: (row) => (row.worstTrade === "—" ? "" : "sc-neg") },
];

export function ComparisonLeaderboard({ comparison, highlight }: Props) {
  const rows = buildLeaderboard(comparison);
  const hi = Object.fromEntries(
    COLUMNS.filter((col) => col.higher != null).map((col) => [
      col.key,
      highlight ? bestIndexes(rows, col.key, col.higher === true) : new Set<number>(),
    ]),
  ) as Record<string, Set<number>>;

  return (
    <section className="sc-leaderboard" data-testid="sc-leaderboard">
      <div className="sc-leaderboard-scroll">
        <table className="sc-lb-table">
          <thead>
            <tr>
              {COLUMNS.map((col) => (
                <th key={col.key} className={col.className} data-testid={`sc-lb-col-${col.key}`}>
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.slot.slot_id} data-testid={`sc-lb-row-${row.slot.slot_id}`}>
                {COLUMNS.map((col) => {
                  const extra = col.key === "strategy" ? "" : col.valueClass?.(row) || "";
                  const hiClass = hi[col.key]?.has(index) ? "sc-cell--hi" : "";
                  return (
                    <td key={col.key} className={`${col.className || ""} ${extra} ${hiClass}`.trim()}>
                      {col.key === "rank" ? (
                        <span className={`sc-lb-rank sc-lb-rank--${row.rank}`}>{row.rank}</span>
                      ) : col.key === "strategy" ? (
                        <span className="sc-lb-strategy">
                          <span className="sc-dot" style={{ background: SLOT_COLORS[row.slotIndex] }} />
                          <span>
                            {row.slot.strategy_name}
                            <small>{row.slot.source === "lean" ? "LEAN" : "Scan"}</small>
                          </span>
                        </span>
                      ) : col.key === "grade" ? (
                        <span className={`sc-lb-grade sc-lb-grade--${(row.grade || "none").toLowerCase()}`}>{row.grade || "—"}</span>
                      ) : (
                        col.render(row)
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="sc-section-note" data-testid="sc-leaderboard-note">
        {LEADERBOARD_NOTE}
      </p>
    </section>
  );
}
