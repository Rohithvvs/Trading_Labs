/**
 * Signal normalization and user-facing label simplification for Trading Labs.
 *
 * Normalizes multi-word, internal, or legacy indicators into the clean user triad:
 * - BUY (Bullish entry)
 * - WATCH (Setup forming / monitor / hold)
 * - REJECT (Filtered out / discard / bearish)
 */

export type SimplifiedSignal = "BUY" | "WATCH" | "REJECT" | "SELL" | "—";

export type SignalTone = "buy" | "watch" | "sell" | "neutral";

/**
 * Simplifies any raw internal or broker signal into a user-friendly label.
 */
export function simplifySignal(raw: unknown): SimplifiedSignal {
  if (raw == null) return "—";
  const str = String(raw).trim().toUpperCase();
  if (!str || str === "N/A" || str === "NONE" || str === "UNKNOWN" || str === "—") {
    return "—";
  }

  // BUY variants
  if (
    str === "BUY" ||
    str === "STRONG_BUY" ||
    str === "STRONG BUY" ||
    str === "WEAK_BUY" ||
    str === "WEAK BUY" ||
    str === "BULLISH" ||
    str === "LONG" ||
    str === "MATCH" ||
    str === "ENTRY"
  ) {
    return "BUY";
  }

  // WATCH variants (including HOLD, MONITOR, NEUTRAL)
  if (
    str === "WATCH" ||
    str === "MONITOR" ||
    str === "HOLD" ||
    str === "NEUTRAL" ||
    str === "SIDEWAYS" ||
    str === "WAIT" ||
    str === "PENDING" ||
    str === "ACCUMULATE"
  ) {
    return "WATCH";
  }

  // REJECT variants (including DISCARD, FAIL, AVOID, BLOCKED)
  if (
    str === "REJECT" ||
    str === "DISCARD" ||
    str === "AVOID" ||
    str === "BLOCKED" ||
    str === "FAIL" ||
    str === "FAILED" ||
    str === "DROP" ||
    str === "INACTIVE"
  ) {
    return "REJECT";
  }

  // SELL / SHORT variants
  if (str === "SELL" || str === "SHORT" || str === "BEARISH" || str === "EXIT") {
    return "SELL";
  }

  return (str as SimplifiedSignal) || "—";
}

/**
 * Returns design-system color tone for a given signal.
 */
export function getSignalTone(signal: unknown): SignalTone {
  const simplified = simplifySignal(signal);
  switch (simplified) {
    case "BUY":
      return "buy";
    case "WATCH":
      return "watch";
    case "REJECT":
    case "SELL":
      return "sell";
    default:
      return "neutral";
  }
}

/**
 * Returns an accessible explanation of what the signal means to a trader.
 */
export function getSignalDescription(signal: unknown): string {
  const simplified = simplifySignal(signal);
  switch (simplified) {
    case "BUY":
      return "Passed all screening criteria and technical checks. Ready for paper trade planning.";
    case "WATCH":
      return "Setup is forming or in rebalance window. Keep on watchlist and monitor for entry.";
    case "REJECT":
      return "Failed core trend, liquidity, or momentum filters. Discarded from active trade cohort.";
    case "SELL":
      return "Exit or short condition triggered.";
    default:
      return "Signal status not yet evaluated.";
  }
}
