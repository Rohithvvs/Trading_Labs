/**
 * Client-side Trading Hours utilities (mirrors backend TradingHoursService).
 *
 * Orders can be placed 24x7. When the market is closed the backend accepts the
 * order with status PENDING_MARKET_OPEN and executes at the next session open.
 * These helpers are for UX messaging only — the backend is authoritative.
 */

export type MarketSessionStatus =
  | "OPEN"
  | "PRE_OPEN"
  | "CLOSED"
  | "WEEKEND"
  | "HOLIDAY";

export interface MarketCheckResult {
  isOpen: boolean;
  status: MarketSessionStatus;
  reason: MarketSessionStatus;
  message: string;
  nextOpenHint: string;
}

const MARKET_OPEN_MINUTES = 9 * 60 + 15; // 09:15 IST
const MARKET_CLOSE_MINUTES = 15 * 60 + 30; // 15:30 IST

// Keep in sync with backend/data/nse_trading_holidays.json
const KNOWN_HOLIDAYS: Record<string, string[]> = {
  "2025": [
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-08-15", "2025-08-27",
    "2025-10-02", "2025-10-20", "2025-10-21", "2025-11-05", "2025-12-25",
  ],
  "2026": [
    "2026-01-15", "2026-01-26", "2026-02-15", "2026-03-03", "2026-03-21",
    "2026-03-26", "2026-03-31", "2026-04-03", "2026-04-14", "2026-05-01",
    "2026-05-28", "2026-06-26", "2026-08-15", "2026-09-14", "2026-10-02",
    "2026-10-20", "2026-11-08", "2026-11-10", "2026-11-24", "2026-12-25",
  ],
  "2027": [
    "2027-01-26", "2027-02-26", "2027-03-12", "2027-03-29", "2027-04-02",
    "2027-04-14", "2027-04-26", "2027-05-01", "2027-08-15", "2027-08-17",
    "2027-10-02", "2027-10-08", "2027-10-19", "2027-11-05", "2027-12-25",
  ],
};

/** Calendar date in Asia/Kolkata (YYYY-MM-DD). */
export function isoDateIST(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

function getISTDateParts(d: Date = new Date()) {
  const istFormatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = istFormatter.formatToParts(d);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";

  const year = get("year");
  const month = get("month");
  const day = get("day");
  const hour = parseInt(get("hour"), 10);
  const minute = parseInt(get("minute"), 10);
  const weekday = get("weekday");

  const dateStr = `${year}-${month}-${day}`;
  const minutesSinceMidnight = hour * 60 + minute;
  const isWeekend = weekday === "Sat" || weekday === "Sun";

  return { dateStr, year, minutesSinceMidnight, isWeekend };
}

function isKnownHoliday(dateStr: string, year: string): boolean {
  const list = KNOWN_HOLIDAYS[year] || [];
  return list.includes(dateStr);
}

function shiftIsoDate(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const cursor = new Date(Date.UTC(year, month - 1, day + days));
  return cursor.toISOString().slice(0, 10);
}

export function isNseHolidayISO(iso: string): boolean {
  return isKnownHoliday(iso, iso.slice(0, 4));
}

export function isTradingDayISO(iso: string): boolean {
  const [year, month, day] = iso.split("-").map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  if (weekday === 0 || weekday === 6) return false;
  return !isNseHolidayISO(iso);
}

/** Last completed NSE cash session in IST (weekends + holidays skipped). */
export function lastCompletedTradingDayIST(now: Date = new Date()): string {
  const { dateStr, minutesSinceMidnight } = getISTDateParts(now);
  if (isTradingDayISO(dateStr) && minutesSinceMidnight >= MARKET_CLOSE_MINUTES) {
    return dateStr;
  }
  let cursor = isTradingDayISO(dateStr) ? shiftIsoDate(dateStr, -1) : dateStr;
  for (let i = 0; i < 20; i += 1) {
    if (isTradingDayISO(cursor)) return cursor;
    cursor = shiftIsoDate(cursor, -1);
  }
  return cursor;
}

/**
 * NSE cash session the Indicator Scanner should default to:
 * today's IST date on a trading day (from midnight), else the last completed session.
 * Weekends and holidays stay on the previous cash session.
 */
export function currentCashSessionIST(now: Date = new Date()): string {
  const { dateStr, isWeekend } = getISTDateParts(now);
  if (!isWeekend && isTradingDayISO(dateStr)) {
    return dateStr;
  }
  return lastCompletedTradingDayIST(now);
}

/**
 * Returns the 1D session date that TradingView Pine Screener evaluates in IST:
 * - On trading days (during or after market hours): today's date (forming candle or completed EOD)
 * - On weekends or market holidays: the last completed trading day
 */
export function effectivePineScreenerSessionIST(now: Date = new Date()): string {
  const { dateStr, isWeekend, minutesSinceMidnight } = getISTDateParts(now);
  if (!isWeekend && isTradingDayISO(dateStr) && minutesSinceMidnight >= MARKET_OPEN_MINUTES) {
    return dateStr;
  }
  return lastCompletedTradingDayIST(now);
}

/** Whether NSE cash market is currently open (client clock / IST). */
export function isMarketOpen(now: Date = new Date()): boolean {
  return getMarketSession(now).isOpen;
}

export function getMarketSession(now: Date = new Date()): MarketCheckResult {
  const { dateStr, year, minutesSinceMidnight, isWeekend } = getISTDateParts(now);

  if (isWeekend) {
    return {
      isOpen: false,
      status: "WEEKEND",
      reason: "WEEKEND",
      message:
        "The market is currently closed (weekend). Your order will be accepted and executed automatically at the next market open.",
      nextOpenHint: "Next Market Open",
    };
  }

  if (isKnownHoliday(dateStr, year)) {
    return {
      isOpen: false,
      status: "HOLIDAY",
      reason: "HOLIDAY",
      message:
        "Today is an official market holiday. Your order will be accepted and executed automatically at the next trading session.",
      nextOpenHint: "Next Market Open",
    };
  }

  if (minutesSinceMidnight < MARKET_OPEN_MINUTES) {
    return {
      isOpen: false,
      status: "PRE_OPEN",
      reason: "PRE_OPEN",
      message:
        "Market has not opened yet (opens 9:15 AM IST). Your order will be accepted and executed when the market opens.",
      nextOpenHint: "Today 9:15 AM IST",
    };
  }

  if (minutesSinceMidnight > MARKET_CLOSE_MINUTES) {
    return {
      isOpen: false,
      status: "CLOSED",
      reason: "CLOSED",
      message:
        "The market is currently closed. Your order will be placed successfully and executed automatically when the market opens.",
      nextOpenHint: "Next Market Open",
    };
  }

  return {
    isOpen: true,
    status: "OPEN",
    reason: "OPEN",
    message: "Market is open. Orders execute immediately when filled.",
    nextOpenHint: "",
  };
}

/** Human-readable order status for the Orders table. */
export function formatOrderStatus(status: string | undefined | null): string {
  switch ((status || "").toUpperCase()) {
    case "WAITING_FOR_MARKET":
    case "PENDING_MARKET_OPEN": // legacy
      return "Waiting for Market";
    case "READY_TO_EXECUTE":
      return "Ready to Execute";
    case "FAILED":
      return "Failed";
    case "PENDING":
    case "OPEN":
      return "Pending";
    case "PARTIALLY_EXECUTED":
      return "Partially Executed";
    case "FILLED":
    case "EXECUTED":
      return "Executed";
    case "CANCELLED":
      return "Cancelled";
    case "REJECTED":
      return "Rejected";
    default:
      return status || "—";
  }
}

export function isPendingMarketOpen(status: string | undefined | null): boolean {
  const s = (status || "").toUpperCase();
  return s === "WAITING_FOR_MARKET" || s === "PENDING_MARKET_OPEN";
}

export function isOpenOrderStatus(status: string | undefined | null): boolean {
  const s = (status || "").toUpperCase();
  return (
    s === "PENDING" ||
    s === "WAITING_FOR_MARKET" ||
    s === "PENDING_MARKET_OPEN" ||
    s === "READY_TO_EXECUTE" ||
    s === "FAILED" ||
    s === "OPEN" ||
    s === "PARTIALLY_EXECUTED"
  );
}
