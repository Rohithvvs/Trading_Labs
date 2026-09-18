/** Strategy scanner run lifecycle — backend/DB is the source of truth. */

import type { StrategyScanStatus } from "../types";

export type { StrategyScanStatus };

export const STRATEGY_RUN_ACTIVE = new Set([
  "queued",
  "evaluating",
  "backtesting",
  "publishing",
  "starting",
]);

export const STRATEGY_RUN_FAILED = new Set(["failed", "blocked_stale", "cancelled"]);

export function strategyRunStatus(payload: Record<string, unknown> | null | undefined): string {
  if (!payload) return "";
  return String(payload.run_status || payload.status || "");
}

export function isStrategyRunActive(payload: Record<string, unknown> | null | undefined): boolean {
  return STRATEGY_RUN_ACTIVE.has(strategyRunStatus(payload));
}

export function isStrategyRunFailed(payload: Record<string, unknown> | null | undefined): boolean {
  return STRATEGY_RUN_FAILED.has(strategyRunStatus(payload));
}

export function mapStrategyStage(stage?: string | null): string {
  const s = String(stage || "").toLowerCase();
  if (s.includes("evaluat") || s.includes("univers") || s.includes("scann")) return "Scanning universe...";
  if (s.includes("backtest")) return "Running portfolio backtest...";
  if (s.includes("publish")) return "Publishing results...";
  if (s.includes("queued") || s.includes("start")) return "Starting scan...";
  return stage || "Running...";
}

export function startedAtMs(payload: Record<string, unknown> | null | undefined): number | null {
  const raw = payload?.started_at;
  if (!raw) return null;
  const t = Date.parse(String(raw));
  return Number.isNaN(t) ? null : t;
}

/**
 * A GET-latest row is the *current* scan completing only when status is
 * completed AND (if we know the scan we started) the scan_id matches.
 * Previous completed rows must not look like the new run finished.
 */
export function isCurrentScanCompleted(
  payload: Record<string, unknown> | null | undefined,
  expectedScanId?: string | null,
  startedAt?: number | null,
): boolean {
  if (!payload) return false;
  if (strategyRunStatus(payload) !== "completed") return false;
  if (expectedScanId) {
    const got = payload.scan_id ? String(payload.scan_id) : "";
    if (!got || got !== expectedScanId) return false;
    return true;
  }
  if (startedAt) {
    const rowStarted = startedAtMs(payload);
    if (rowStarted != null && rowStarted < startedAt - 5000) return false;
    const completed = payload.completed_at ? Date.parse(String(payload.completed_at)) : NaN;
    if (!Number.isNaN(completed) && completed < startedAt - 5000) return false;
  }
  return !startedAt;
}

export function isCurrentScanFailed(
  payload: Record<string, unknown> | null | undefined,
  expectedScanId?: string | null,
): boolean {
  if (!payload || !isStrategyRunFailed(payload)) return false;
  if (expectedScanId) {
    const got = payload.scan_id ? String(payload.scan_id) : "";
    if (got && got !== expectedScanId) return false;
  }
  return true;
}

export function hasDisplayableStrategyResults(
  payload: Record<string, unknown> | null | undefined,
  opts: { inFlight: boolean },
): boolean {
  if (!payload || opts.inFlight) return false;
  if (payload.recommendations_final === true) return true;
  return Boolean(payload.completed_at && Array.isArray(payload.recommendations));
}

export function readStoredScannerStrategy(): "production" | "17_long_term_mom" | "09_52w_breakout" {
  try {
    const v = sessionStorage.getItem("scanner.strategy");
    if (v === "09_52w_breakout" || v === "17_long_term_mom" || v === "production") return v;
  } catch {
    /* ignore */
  }
  return "17_long_term_mom";
}

export function storeScannerStrategy(id: string): void {
  try {
    sessionStorage.setItem("scanner.strategy", id);
  } catch {
    /* ignore */
  }
}
