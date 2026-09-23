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
  hideHeader?: boolean;
};

function sourceLabel(source: string | undefined): string {
  if (source === "lean") return "Event engine";
  if (source === "indicator_scan") return "Indicator Scanner";
  return "Strategy Tester";
}

function AxisTick({ x, y, payload, textAnchor, cx, cy }: {
  x?: number;
  y?: number;
  cx?: number;
  cy?: number;
  payload?: { value?: string };
  textAnchor?: string;
}) {
  const dx = typeof x === "number" && typeof cx === "number" ? x - cx : 0;
  const dy = typeof y === "number" && typeof cy === "number" ? y - cy : 0;
  const len = Math.hypot(dx, dy) || 1;
  const bump = 14;
  const tx = (x ?? 0) + (dx / len) * bump;
  const ty = (y ?? 0) + (dy / len) * bump;
  return (
    <text
      x={tx}
      y={ty}
      textAnchor={textAnchor || "middle"}
      dominantBaseline="middle"
      fill="#d4d4d8"
      fontSize={13}
      fontWeight={500}
    >
      {payload?.value}
    </text>
  );
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

export function ComparisonRadar({ comparison, hideHeader = false }: Props) {
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

  const focusPicker = (index: number) => {
    const el = document.querySelector(`[data-testid="sc-slot-${index}"]`);
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      const search = el.querySelector("input, select, button") as HTMLElement | null;
      search?.focus();
    }
  };

  return (
    <section className={hideHeader ? "sc-radar-embed" : "sc-radar-panel"} data-testid="sc-radar">
      {hideHeader ? null : (
        <div
          className="sc-radar-head"
          style={{ gridTemplateColumns: `minmax(48px, 0.7fr) repeat(${slots.length}, minmax(0, 1fr))` }}
        >
          <div className="sc-radar-head-cell sc-radar-head-cell--empty" />
          {slots.map((slot, index) => (
            <button
              type="button"
              className="sc-radar-head-cell"
              key={slot.slot_id}
              onClick={() => focusPicker(index)}
              title="Change strategy"
            >
              <span className="sc-radar-head-swatch" style={{ background: SLOT_COLORS[index] }} />
              <span className="sc-radar-head-name">{slot.strategy_name}</span>
              <span className="sc-radar-head-chevron" aria-hidden>▾</span>
            </button>
          ))}
        </div>
      )}

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
            <ResponsiveContainer width="100%" height={520}>
              <RadarChart data={radarData} cx="52%" cy="50%" outerRadius="64%" margin={{ top: 36, right: 56, bottom: 36, left: 72 }}>
                <PolarGrid
                  gridType="polygon"
                  stroke="#3f4b63"
                  strokeWidth={1}
                  radialLines
                  polarRadius={[22, 44, 66, 88]}
                />
                <PolarAngleAxis dataKey="axis" tick={<AxisTick />} tickLine={false} />
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
                    fillOpacity={0.2}
                    strokeWidth={2}
                    dot={{ r: 5, fill: SLOT_COLORS[index], stroke: SLOT_COLORS[index], strokeWidth: 0 }}
                    activeDot={{ r: 7 }}
                    isAnimationActive={false}
                  />
                ))}
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
      {radar.note ? <p className="sc-radar-note">{radar.note}</p> : null}
    </section>
  );
}
