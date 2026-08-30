import type { NavigateFunction } from "react-router-dom";

/** Canonical cash symbol for stock navigation. */
export function toCanonicalStockSymbol(raw: string | undefined | null): string {
  if (!raw) return "";
  let s = raw.trim().toUpperCase();
  if (s.startsWith("NSE:")) s = s.slice(4);
  else if (s.startsWith("BSE:")) s = s.slice(4);
  else if (s.includes(":")) s = s.split(":")[1] ?? s;
  if (s.endsWith("-EQ")) s = s.slice(0, -3);
  return s;
}

export type NavigateToStockOptions = {
  runId?: string | null;
  returnTo?: string;
  state?: Record<string, unknown>;
  replace?: boolean;
};

/**
 * Navigate to the dedicated full-page Stock Details page (/stock/:symbol).
 * Replaces right-side drawers and modals with client-side route navigation.
 */
export function navigateToStock(
  navigate: NavigateFunction,
  symbol: string,
  options: NavigateToStockOptions = {},
): void {
  const canonical = toCanonicalStockSymbol(symbol);
  if (!canonical) return;

  const returnTo =
    options.returnTo ??
    (typeof window !== "undefined"
      ? `${window.location.pathname}${window.location.search || ""}`
      : "/strategy-tester");

  const params = new URLSearchParams();
  if (options.runId) {
    params.set("runId", options.runId);
  }
  const qs = params.toString();
  const path = `/stock/${encodeURIComponent(canonical)}${qs ? `?${qs}` : ""}`;

  navigate(path, {
    replace: options.replace ?? false,
    state: {
      symbol: canonical,
      runId: options.runId ?? null,
      returnTo,
      ...options.state,
    },
  });
}
