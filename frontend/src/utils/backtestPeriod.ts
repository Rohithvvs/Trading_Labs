export type BacktestWindowKey = "1Y" | "3Y" | "5Y" | "ALL";

export function inferCompletedYears(start?: string | null, end?: string | null): number | undefined {
  if (!start || !end) return undefined;
  const s = Date.parse(`${String(start).slice(0, 10)}T00:00:00Z`);
  const e = Date.parse(`${String(end).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return undefined;
  const days = (e - s) / 86_400_000;
  if (days >= 360 * 4.5) return 5;
  if (days >= 360 * 2.5) return 3;
  if (days >= 180) return 1;
  return undefined;
}

export function yearsFromWindow(window?: string | null, start?: string | null, end?: string | null): number | undefined {
  const key = String(window || "").toUpperCase();
  if (key === "1Y") return 1;
  if (key === "3Y") return 3;
  if (key === "5Y") return 5;
  return inferCompletedYears(start, end);
}

export function formatCompletedSessionPeriod(
  start?: string | null,
  end?: string | null,
  years?: number | null,
): string | undefined {
  if (!start || !end) return undefined;
  const y = years ?? inferCompletedYears(start, end);
  const span =
    y === 1 ? "last 1 year of completed sessions" : y ? `last ${y} years of completed sessions` : "completed sessions";
  return `Period ${String(start).slice(0, 10)} → ${String(end).slice(0, 10)} · ${span}`;
}

export function periodLabelFromPayload(payload: Record<string, any> | null | undefined): string | undefined {
  if (!payload) return undefined;
  const first = payload.top5_positive?.[0] || payload.least5?.[0] || payload.universe_average;
  const start =
    payload.attribution_window_start ||
    payload.universe_average?.window_start ||
    first?.window_start ||
    null;
  const end =
    payload.attribution_window_end ||
    payload.universe_average?.window_end ||
    first?.window_end ||
    payload.evaluation_date ||
    null;
  const years = yearsFromWindow(payload.attribution_window || payload.universe_average?.window, start, end);
  if (start && end) return formatCompletedSessionPeriod(start, end, years);
  if (payload.evaluation_date && years) {
    return `Period ending ${String(payload.evaluation_date).slice(0, 10)} · last ${years} year${years === 1 ? "" : "s"} of completed sessions`;
  }
  return undefined;
}
