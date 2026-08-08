import { memo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from "recharts";

const tooltipStyle = {
  background: "#111827",
  border: "1px solid #1F2937",
  borderRadius: 8,
  fontSize: 12,
};

export type LabLinePoint = { label: string; re001?: number; re002?: number; total?: number };
export type LabBarPoint = { name: string; value: number; color?: string };

export const LabPerformanceChart = memo(function LabPerformanceChart({
  data,
  title = "Experiment Performance (decisions)",
}: {
  data: LabLinePoint[];
  title?: string;
}) {
  return (
    <section className="lab-card lab-chart-card" data-testid="lab-performance-chart">
      <header className="lab-card__header">
        <h3 className="lab-card__title">{title}</h3>
      </header>
      {data.length === 0 ? (
        <p className="lab-empty">Load a scan cohort to chart decision volume.</p>
      ) : (
        <div className="lab-chart-card__canvas">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1F2937" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fill: "#9CA3AF", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#9CA3AF", fontSize: 11 }} axisLine={false} tickLine={false} width={36} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="total" name="Decisions" stroke="#2563EB" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="re001" name="RE-001" stroke="#22C55E" strokeWidth={1.5} dot={false} />
              <Line type="monotone" dataKey="re002" name="RE-002" stroke="#FACC15" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
});

export const LabConfidenceBarChart = memo(function LabConfidenceBarChart({
  data,
  title = "Avg Confidence by Engine",
}: {
  data: LabBarPoint[];
  title?: string;
}) {
  return (
    <section className="lab-card lab-chart-card" data-testid="lab-confidence-chart">
      <header className="lab-card__header">
        <h3 className="lab-card__title">{title}</h3>
      </header>
      {data.length === 0 ? (
        <p className="lab-empty">Comparison rows will populate confidence bars.</p>
      ) : (
        <div className="lab-chart-card__canvas">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1F2937" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: "#9CA3AF", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                domain={[0, 1]}
                tick={{ fill: "#9CA3AF", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={36}
              />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [v.toFixed(2), "Confidence"]} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} maxBarSize={48}>
                {data.map((d) => (
                  <Cell key={d.name} fill={d.color || "#2563EB"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
});
