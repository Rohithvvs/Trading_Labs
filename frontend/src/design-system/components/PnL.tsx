import type { ReactNode } from "react";

type Props = {
  value: number | null | undefined;
  /** Show currency prefix ₹ */
  currency?: boolean;
  /** Show percent sign */
  percent?: boolean;
  digits?: number;
  className?: string;
  /** Compact: arrow + value only */
  size?: "sm" | "md" | "lg";
  showBadge?: boolean;
};

/**
 * Colorblind-safe P&L: color + arrow + optional badge text.
 * Never relies on red/green alone.
 */
export function PnL({
  value,
  currency = true,
  percent = false,
  digits = 2,
  className = "",
  size = "md",
  showBadge = false,
}: Props) {
  if (value == null || Number.isNaN(Number(value))) {
    return <span className={`ds-pnl ds-pnl--flat ${className}`.trim()}>—</span>;
  }

  const n = Number(value);
  const direction = n > 0 ? "up" : n < 0 ? "down" : "flat";
  const abs = Math.abs(n);
  const formatted = abs.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const prefix = currency ? "₹" : "";
  const suffix = percent ? "%" : "";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";

  return (
    <span
      className={`ds-pnl ds-pnl--${direction} ds-pnl--${size} ${className}`.trim()}
      aria-label={`${direction === "up" ? "Profit" : direction === "down" ? "Loss" : "Unchanged"} ${sign}${prefix}${formatted}${suffix}`}
    >
      <span className="ds-pnl__arrow" aria-hidden>
        {direction === "up" ? "▲" : direction === "down" ? "▼" : "●"}
      </span>
      <span className="ds-pnl__value">
        {sign}
        {prefix}
        {formatted}
        {suffix}
      </span>
      {showBadge ? (
        <span className="ds-pnl__badge" aria-hidden>
          {direction === "up" ? "Profit" : direction === "down" ? "Loss" : "Flat"}
        </span>
      ) : null}
    </span>
  );
}

import { simplifySignal, getSignalTone, getSignalDescription } from "../../utils/signalUtils";

export function SignalBadge({ signal }: { signal: string }) {
  const display = simplifySignal(signal);
  const tone = getSignalTone(signal);
  const description = getSignalDescription(signal);
  let icon: ReactNode = "•";

  if (tone === "buy") {
    icon = "▲";
  } else if (tone === "sell") {
    icon = "▼";
  } else if (tone === "watch") {
    icon = "◆";
  }

  return (
    <span
      className={`ds-badge ds-badge--${tone}`}
      title={description}
      aria-label={`${display}: ${description}`}
    >
      <span className="ds-badge__icon" aria-hidden>
        {icon}
      </span>
      <span>{display}</span>
    </span>
  );
}

