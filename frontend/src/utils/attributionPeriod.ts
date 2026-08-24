export const ATTRIBUTION_PERIODS = ["1D", "1W", "1M", "1Y", "3Y", "5Y", "7Y", "8Y", "18Y"] as const;

export type AttributionPeriod = (typeof ATTRIBUTION_PERIODS)[number];

export const DEFAULT_ATTRIBUTION_PERIOD: AttributionPeriod = "3Y";

export function isAttributionPeriod(value: string | null | undefined): value is AttributionPeriod {
  return ATTRIBUTION_PERIODS.includes(String(value || "").toUpperCase() as AttributionPeriod);
}

function utcDate(iso: string): Date | null {
  const text = String(iso || "").slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!m) return null;
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
}

function toIso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Inclusive window start for book-trade attribution. Calendar math, same family as the 3Y boards. */
export function periodWindowStart(end: string, period: AttributionPeriod): string {
  const dt = utcDate(end);
  if (!dt) return end;
  switch (period) {
    case "1D":
      return toIso(dt);
    case "1W":
      dt.setUTCDate(dt.getUTCDate() - 6);
      return toIso(dt);
    case "1M":
      dt.setUTCMonth(dt.getUTCMonth() - 1);
      return toIso(dt);
    case "1Y":
      dt.setUTCFullYear(dt.getUTCFullYear() - 1);
      return toIso(dt);
    case "3Y":
      dt.setUTCFullYear(dt.getUTCFullYear() - 3);
      return toIso(dt);
    case "5Y":
      dt.setUTCFullYear(dt.getUTCFullYear() - 5);
      return toIso(dt);
    case "7Y":
      dt.setUTCFullYear(dt.getUTCFullYear() - 7);
      return toIso(dt);
    case "8Y":
      dt.setUTCFullYear(dt.getUTCFullYear() - 8);
      return toIso(dt);
    case "18Y":
      dt.setUTCFullYear(dt.getUTCFullYear() - 18);
      return toIso(dt);
    default:
      return end;
  }
}

export function periodNoun(period: AttributionPeriod): string {
  switch (period) {
    case "1D":
      return "1-day";
    case "1W":
      return "1-week";
    case "1M":
      return "1-month";
    case "1Y":
      return "1-year";
    case "3Y":
      return "3-year";
    case "5Y":
      return "5-year";
    case "7Y":
      return "7-year";
    case "8Y":
      return "8-year";
    case "18Y":
      return "18-year";
    default:
      return period;
  }
}

export function periodSessionSpan(period: AttributionPeriod): string {
  switch (period) {
    case "1D":
      return "last 1 day of completed sessions";
    case "1W":
      return "last 1 week of completed sessions";
    case "1M":
      return "last 1 month of completed sessions";
    case "1Y":
      return "last 1 year of completed sessions";
    default:
      return `last ${period.replace("Y", "")} years of completed sessions`;
  }
}

export function formatAttributionPeriod(start: string, end: string, period: AttributionPeriod): string {
  return `Period ${start} → ${end} · ${periodSessionSpan(period)}`;
}

/** Count a trade iff it was opened inside the requested performance window. */
export function tradeInRequestedPeriod(entry: string | null | undefined, start: string, end: string): boolean {
  if (!entry) return false;
  return entry >= start && entry <= end;
}

export const SIGNAL_SEMANTICS =
  "Today's 52-Week High Breakout scan recommendation (BUY / HOLD / WATCH / REJECT). Independent of historical book-trade returns.";
