import { memo, useMemo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

export type LabDonutSlice = {
  name: string;
  value: number;
  color: string;
};

type Props = {
  title: string;
  data: LabDonutSlice[];
  emptyLabel?: string;
  testId?: string;
};

export const LabDonutChart = memo(function LabDonutChart({
  title,
  data,
  emptyLabel = "No data yet",
  testId,
}: Props) {
  const total = useMemo(() => data.reduce((s, d) => s + (d.value || 0), 0), [data]);
  const hasData = total > 0;

  return (
    <section className="lab-card lab-donut" data-testid={testId}>
      <header className="lab-card__header">
        <h3 className="lab-card__title">{title}</h3>
      </header>
      {!hasData ? (
        <p className="lab-empty">{emptyLabel}</p>
      ) : (
        <div className="lab-donut__body">
          <div className="lab-donut__chart">
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={48}
                  outerRadius={72}
                  paddingAngle={2}
                  stroke="transparent"
                >
                  {data.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "#111827",
                    border: "1px solid #1F2937",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value: number, name: string) => [
                    `${value} (${total ? ((value / total) * 100).toFixed(1) : 0}%)`,
                    name,
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="lab-donut__legend">
            {data.map((d) => {
              const pct = total ? ((d.value / total) * 100).toFixed(1) : "0.0";
              return (
                <li key={d.name}>
                  <span className="lab-donut__swatch" style={{ background: d.color }} />
                  <span className="lab-donut__name">{d.name}</span>
                  <span className="lab-donut__pct">{pct}%</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
});
