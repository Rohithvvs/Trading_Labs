import { memo, type ReactNode } from "react";

export type LabMetricCardProps = {
  label: string;
  value: ReactNode;
  subtitle?: string;
  trend?: string;
  trendTone?: "up" | "down" | "neutral";
  icon?: ReactNode;
  accent?: "blue" | "green" | "purple" | "amber" | "cyan";
  loading?: boolean;
  testId?: string;
};

export const LabMetricCard = memo(function LabMetricCard({
  label,
  value,
  subtitle,
  trend,
  trendTone = "neutral",
  icon,
  accent = "blue",
  loading,
  testId,
}: LabMetricCardProps) {
  return (
    <article
      className={`lab-metric lab-metric--${accent}${loading ? " lab-metric--loading" : ""}`}
      data-testid={testId}
    >
      <div className="lab-metric__top">
        <span className="lab-metric__label">{label}</span>
        {icon ? <span className="lab-metric__icon">{icon}</span> : null}
      </div>
      <div className="lab-metric__value">{loading ? "—" : value}</div>
      <div className="lab-metric__meta">
        {trend ? (
          <span className={`lab-metric__trend lab-metric__trend--${trendTone}`}>{trend}</span>
        ) : null}
        {subtitle ? <span className="lab-metric__sub">{subtitle}</span> : null}
      </div>
    </article>
  );
});
