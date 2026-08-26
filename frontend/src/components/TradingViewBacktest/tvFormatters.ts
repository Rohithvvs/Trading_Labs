/**
 * Helper formatting utilities for TradingView-style components.
 */

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function fmtTvDate(value?: string | null): string {
  if (!value) return "--";
  const str = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(str)) {
    const parts = str.slice(0, 10).split("-");
    const year = parts[0];
    const monthIdx = parseInt(parts[1], 10) - 1;
    const day = parseInt(parts[2], 10);
    if (monthIdx >= 0 && monthIdx < 12 && !Number.isNaN(day)) {
      return `${MONTH_NAMES[monthIdx]} ${day}, ${year}`;
    }
  }
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return str.slice(0, 10);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return str.slice(0, 10);
  }
}

export function fmtTvDateRange(start?: string | null, end?: string | null): string {
  if (!start && !end) return "All time";
  const s = fmtTvDate(start);
  const e = fmtTvDate(end);
  return `${s} — ${e}`;
}

export function fmtTvCapital(value: number | null | undefined, currency = "INR"): string {
  if (value == null || Number.isNaN(Number(value))) return `₹ 1,00,000 ${currency}`;
  const n = Number(value);
  if (n >= 1_000_000_000) {
    return `${(n / 1_000_000_000).toFixed(n % 1_000_000_000 === 0 ? 0 : 2)} B ${currency}`;
  }
  if (n >= 1_000_000) {
    return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)} M ${currency}`;
  }
  if (n >= 100_000) {
    return `₹ ${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })} ${currency}`;
  }
  if (n >= 1_000) {
    return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)} K ${currency}`;
  }
  return `₹ ${n.toFixed(0)} ${currency}`;
}

export function fmtTvPnl(value: number | null | undefined, includeSign = true): { formatted: string; isPositive: boolean; isNegative: boolean } {
  if (value == null || Number.isNaN(Number(value))) {
    return { formatted: "--", isPositive: false, isNegative: false };
  }
  const n = Number(value);
  const abs = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (n > 0) {
    return { formatted: `${includeSign ? "+" : ""}${abs}`, isPositive: true, isNegative: false };
  }
  if (n < 0) {
    return { formatted: `-${abs}`, isPositive: false, isNegative: true };
  }
  return { formatted: `${abs}`, isPositive: false, isNegative: false };
}

export function fmtTvPct(value: number | null | undefined, includeSign = true, digits = 2): { formatted: string; isPositive: boolean; isNegative: boolean } {
  if (value == null || Number.isNaN(Number(value))) {
    return { formatted: "--", isPositive: false, isNegative: false };
  }
  const n = Number(value);
  const abs = Math.abs(n).toFixed(digits);
  if (n > 0) {
    return { formatted: `${includeSign ? "+" : ""}${abs}%`, isPositive: true, isNegative: false };
  }
  if (n < 0) {
    return { formatted: `-${abs}%`, isPositive: false, isNegative: true };
  }
  return { formatted: `${abs}%`, isPositive: false, isNegative: false };
}

export function fmtTvPrice(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 2,
  });
}

export function fmtTvSize(qty: number, price?: number | null, currency = "INR"): { qtyStr: string; notionalStr: string } {
  const q = qty || 1;
  const p = price != null ? Number(price) : null;
  const notional = p != null ? q * p : null;

  let notionalStr = "--";
  if (notional != null) {
    if (notional >= 1_000_000) {
      notionalStr = `${(notional / 1_000_000).toFixed(2)} M ${currency}`;
    } else if (notional >= 1_000) {
      notionalStr = `${(notional / 1_000).toFixed(2)} K ${currency}`;
    } else {
      notionalStr = `${notional.toFixed(1)} ${currency}`;
    }
  }

  return {
    qtyStr: String(q),
    notionalStr,
  };
}
