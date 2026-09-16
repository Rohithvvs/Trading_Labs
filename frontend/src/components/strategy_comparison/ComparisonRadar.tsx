import { useMemo } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { ComparisonPayload } from "../../api_strategy_comparison";
import { SLOT_COLORS } from "./ComparisonCharts";

type Props = {
  comparison: ComparisonPayload;
};

function sourceLabel(source: string | undefined): string {
  return source === "lean" ? "LEAN backtest" : "Strategy Tester";
}

function formatRaw(key: string, raw: number | null | undefined): string {
  if (raw == null || Number.isNaN(Number(raw))) return "—";
  if (["win_rate", "total_return_pct", "cagr", "average_trade", "max_drawdown_pct", "best_trade"].includes(key)) {
    return `${Number(raw).toFixed(2)}%`;
  }
  if (["total_trades", "buy_count", "watch_count"].includes(key)) {
    return Number(raw).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }
  return Number(raw).toLocaleString("en-IN", { maximumFractionDigits: 3 });
}

export function ComparisonRadar({ comparison }: Props) {
  const { slots, radar } = comparison;

  const radarData = useMemo(() => {
    return (radar.axes || []).map((axis) => {
      const row: Record<string, string | number | null> = { axis: axis.label, key: axis.key };
      radar.series.forEach((series, index) => {
        row[`s${index}`] = series.values[axis.key] ?? 0;
      });
      return row;
    });
  }, [radar]);

  return (
    <section className="sc-radar-panel" data-testid="sc-radar">
      <div
        className="sc-radar-head"
        style={{ gridTemplateColumns: `minmax(72px, 0.55fr) repeat(${slots.length}, minmax(0, 1fr))` }}
      >
        <div className="sc-radar-head-cell sc-radar-head-cell--empty" />
        {slots.map((slot, index) => (
          <div className="sc-radar-head-cell" key={slot.slot_id}>
            <span className="sc-radar-head-swatch" style={{ background: SLOT_COLORS[index] }} />
            <span className="sc-radar-head-name">{slot.strategy_name}</span>
          </div>
        ))}
      </div>

      <div className="sc-radar-body">
        <div className="sc-radar-legend">
          {slots.map((slot, index) => (
            <div className="sc-radar-legend-item" key={slot.slot_id}>
              <span className="sc-radar-legend-swatch" style={{ background: SLOT_COLORS[index] }} />
              <div>
                <div className="sc-radar-legend-name">{slot.strategy_name}</div>
                <div className="sc-radar-legend-sub">
                  {sourceLabel(slot.source)}
                  {slot.config.universe ? ` · ${slot.config.universe}` : ""}
                </div>
              </div>
            </div>
          ))}
        </div>

        {radar.axes.length < 3 ? (
          <div className="sc-chart-empty" data-testid="sc-radar-empty">
            Not enough overlapping metrics for a profile chart.
          </div>
        ) : (
          <div className="sc-radar-chart" data-testid="sc-radar-chart">
            <ResponsiveContainer width="100%" height={460}>
              <RadarChart data={radarData} cx="50%" cy="52%" outerRadius="68%" margin={{ top: 32, right: 48, bottom: 32, left: 48 }}>
                <PolarGrid gridType="polygon" stroke="#243044" strokeWidth={1} polarRadius={[25, 50, 75, 100]} />
                <PolarAngleAxis
                  dataKey="axis"
                  tick={{ fill: "#cbd5e1", fontSize: 13, fontWeight: 500 }}
                  tickLine={false}
                />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} tickCount={5} />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const axis = radar.axes.find((item) => item.label === label);
                    return (
                      <div className="sc-radar-tooltip">
                        <div className="sc-radar-tooltip-title">{label}</div>
                        {payload.map((entry) => {
                          const match = String(entry.dataKey || "").match(/^s(\d+)$/);
                          const index = match ? Number(match[1]) : 0;
                          const series = radar.series[index];
                          const raw = axis && series ? series.raw[axis.key] : null;
                          return (
                            <div className="sc-radar-tooltip-row" key={String(entry.dataKey)} style={{ color: String(entry.color) }}>
                              <span>{series?.name || entry.name}</span>
                              <strong>{formatRaw(axis?.key || "", raw)}</strong>
                            </div>
                          );
                        })}
                      </div>
                    );
                  }}
                />
                {slots.map((slot, index) => (
                  <Radar
                    key={slot.slot_id}
                    name={slot.strategy_name}
                    dataKey={`s${index}`}
                    stroke={SLOT_COLORS[index]}
                    fill={SLOT_COLORS[index]}
                    fillOpacity={0.22}
                    strokeWidth={2}
                    dot={{ r: 4.5, fill: SLOT_COLORS[index], stroke: SLOT_COLORS[index], strokeWidth: 0 }}
                    activeDot={{ r: 6 }}
                    isAnimationActive={false}
                  />
                ))}
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
      <p className="sc-radar-note">{radar.note}</p>
    </section>
  );
}
