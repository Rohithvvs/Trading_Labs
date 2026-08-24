import { memo, useMemo } from "react";

const DEFAULT_WIDTH = 120;
const DEFAULT_HEIGHT = 40;

export function downsampleValues(values: number[], maxPoints = 32): number[] {
  if (values.length <= maxPoints) return values;
  const last = values.length - 1;
  const step = last / (maxPoints - 1);
  const out: number[] = [];
  for (let i = 0; i < maxPoints; i += 1) {
    out.push(values[Math.round(i * step)]);
  }
  return out;
}

export const Sparkline = memo(function Sparkline({
  values,
  width = DEFAULT_WIDTH,
  height = DEFAULT_HEIGHT,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  const path = useMemo(() => {
    const series = downsampleValues(values);
    if (series.length < 2) return "";
    let min = series[0];
    let max = series[0];
    for (let i = 1; i < series.length; i += 1) {
      if (series[i] < min) min = series[i];
      if (series[i] > max) max = series[i];
    }
    const span = max - min || 1;
    const n = series.length - 1;
    let d = "";
    for (let i = 0; i < series.length; i += 1) {
      const x = (i / n) * width;
      const y = height - ((series[i] - min) / span) * (height - 2) - 1;
      d += `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    }
    return d;
  }, [values, width, height]);

  if (!path) {
    return <span className="sparkline-empty">No chart data</span>;
  }

  return (
    <svg
      className="sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
      focusable="false"
    >
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
});
