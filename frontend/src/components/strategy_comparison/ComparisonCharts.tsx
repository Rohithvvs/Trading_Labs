import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ComparisonPayload, ComparisonSlot } from "../../api_strategy_comparison";

export const SLOT_COLORS = ["#60a5fa", "#22c55e", "#a78bfa", "#f59e0b"];

type Props = {
  comparison: ComparisonPayload;
};

function mergeSeries(
  slots: ComparisonSlot[],
  pick: (slot: ComparisonSlot) => Array<{ date?: string; period?: string; value: number | null | undefined }>,
  keyName: "date" | "period",
) {
  const map = new Map<string, Record<string, number | string | null>>();
  slots.forEach((slot, index) => {
    for (const point of pick(slot)) {
      const key = String(point.date || point.period || "");
      if (!key) continue;
      const row = map.get(key) ?? { [keyName]: key };
      row[`s${index}`] = point.value ?? null;
      map.set(key, row);
    }
  });
  return Array.from(map.values()).sort((a, b) => String(a[keyName]).localeCompare(String(b[keyName])));
}

const tooltipStyle = {
  background: "#091022",
  border: "1px solid #15223e",
  borderRadius: 8,
  fontSize: 12,
};

export function ComparisonCharts({ comparison }: Props) {
  const { slots, has_equity } = comparison;

  const equityData = useMemo(
    () =>
      mergeSeries(
        slots,
        (slot) => slot.equity_curve.map((p) => ({ date: p.date, value: p.equity })),
        "date",
      ),
    [slots],
  );
  const ddData = useMemo(
    () =>
      mergeSeries(
        slots,
        (slot) =>
          (slot.drawdown_curve.length ? slot.drawdown_curve : slot.equity_curve).map((p) => ({
            date: p.date,
            value: p.drawdown_pct == null ? null : -Math.abs(p.drawdown_pct),
          })),
        "date",
      ),
    [slots],
  );
  const monthlyData = useMemo(
    () =>
      mergeSeries(
        slots,
        (slot) => slot.monthly_returns.map((p) => ({ period: p.period, value: p.return_pct })),
        "period",
      ),
    [slots],
  );
  const yearlyData = useMemo(
    () =>
      mergeSeries(
        slots,
        (slot) => slot.yearly_returns.map((p) => ({ period: p.period, value: p.return_pct })),
        "period",
      ),
    [slots],
  );
  const distData = useMemo(() => {
    const labels = slots[0]?.trade_distribution ?? [];
    return labels.map((bucket, idx) => {
      const row: Record<string, string | number> = { label: bucket.label };
      slots.forEach((slot, sIdx) => {
        row[`s${sIdx}`] = slot.trade_distribution[idx]?.count ?? 0;
      });
      return row;
    });
  }, [slots]);
  const emptyEquity = !has_equity || equityData.length === 0;
  const scanCountData = useMemo(() => {
    if (!slots.some((slot) => slot.scan_summary)) return [];
    return [
      { label: "BUY", ...Object.fromEntries(slots.map((slot, i) => [`s${i}`, slot.scan_summary?.buy ?? 0])) },
      { label: "WATCH", ...Object.fromEntries(slots.map((slot, i) => [`s${i}`, slot.scan_summary?.watch ?? 0])) },
      { label: "REJECT", ...Object.fromEntries(slots.map((slot, i) => [`s${i}`, slot.scan_summary?.reject ?? 0])) },
    ];
  }, [slots]);

  return (
    <section className="sc-section" data-testid="sc-charts">
      <h2 className="sc-section-title">Charts</h2>
      <p className="sc-section-note">
        Scan charts use completed Strategy Tester window returns. Equity, drawdown and monthly/yearly series appear when
        a LEAN backtest is selected. Missing series stay empty — they are not filled with calendar days.
      </p>
      <div className="sc-charts">
        {scanCountData.length > 0 ? (
          <div className="sc-chart-card">
            <h3>Scan signals</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={scanCountData}>
                <CartesianGrid stroke="#15223e" strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fill: "#64748b", fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                {slots.map((slot, i) => (
                  <Bar key={slot.slot_id} dataKey={`s${i}`} name={slot.strategy_name} fill={SLOT_COLORS[i]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {!emptyEquity ? (
          <div className="sc-chart-card sc-chart-card--wide">
            <h3>Equity curve comparison</h3>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={equityData}>
                <CartesianGrid stroke="#15223e" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} minTickGap={24} />
                <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend />
                {slots.map((slot, i) => (
                  <Line
                    key={slot.slot_id}
                    type="monotone"
                    dataKey={`s${i}`}
                    name={slot.strategy_name}
                    stroke={SLOT_COLORS[i]}
                    dot={false}
                    strokeWidth={2}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {!emptyEquity ? (
          <div className="sc-chart-card">
            <h3>Drawdown comparison</h3>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={ddData}>
                <CartesianGrid stroke="#15223e" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} minTickGap={24} />
                <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                {slots.map((slot, i) => (
                  <Area
                    key={slot.slot_id}
                    type="monotone"
                    dataKey={`s${i}`}
                    name={slot.strategy_name}
                    stroke={SLOT_COLORS[i]}
                    fill={SLOT_COLORS[i]}
                    fillOpacity={0.15}
                    connectNulls
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {monthlyData.length > 0 ? (
          <div className="sc-chart-card">
            <h3>Monthly returns</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={monthlyData}>
                <CartesianGrid stroke="#15223e" strokeDasharray="3 3" />
                <XAxis dataKey="period" tick={{ fill: "#64748b", fontSize: 11 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                {slots.map((slot, i) => (
                  <Bar key={slot.slot_id} dataKey={`s${i}`} name={slot.strategy_name} fill={SLOT_COLORS[i]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {yearlyData.length > 0 ? (
          <div className="sc-chart-card">
            <h3>Yearly returns</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={yearlyData}>
                <CartesianGrid stroke="#15223e" strokeDasharray="3 3" />
                <XAxis dataKey="period" tick={{ fill: "#64748b", fontSize: 11 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                {slots.map((slot, i) => (
                  <Bar key={slot.slot_id} dataKey={`s${i}`} name={slot.strategy_name} fill={SLOT_COLORS[i]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        <div className="sc-chart-card">
          <h3>Trade distribution</h3>
          {distData.every((row) => slots.every((_, i) => !row[`s${i}`])) ? (
            <div className="sc-chart-empty">No trade or window-return observations on the selected runs.</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={distData}>
                <CartesianGrid stroke="#15223e" strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 10 }} interval={0} />
                <YAxis allowDecimals={false} tick={{ fill: "#64748b", fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                {slots.map((slot, i) => (
                  <Bar key={slot.slot_id} dataKey={`s${i}`} name={slot.strategy_name} fill={SLOT_COLORS[i]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </section>
  );
}
