import { memo } from "react";

export type LabStatus =
  | "ACTIVE"
  | "PRODUCTION"
  | "DRAFT"
  | "COMPLETED"
  | "ARCHIVED"
  | "RUNNING"
  | "INACTIVE"
  | "BUY"
  | "SELL"
  | "WATCH"
  | "REJECT"
  | string;

const mapTone = (status: string): string => {
  const s = status.toUpperCase();
  if (s === "BUY" || s === "ACTIVE" || s === "PRODUCTION" || s === "RUNNING") return "green";
  if (s === "WATCH" || s === "DRAFT" || s === "INACTIVE") return "amber";
  if (s === "SELL" || s === "REJECT" || s === "ARCHIVED") return "red";
  if (s === "COMPLETED") return "blue";
  return "muted";
};

export const LabStatusBadge = memo(function LabStatusBadge({
  status,
  className = "",
}: {
  status: LabStatus;
  className?: string;
}) {
  const label = String(status || "—");
  const tone = mapTone(label);
  return (
    <span className={`lab-badge lab-badge--${tone} ${className}`.trim()} data-status={label}>
      {label}
    </span>
  );
});
