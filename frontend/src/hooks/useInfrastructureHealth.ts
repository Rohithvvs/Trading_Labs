import { useEffect, useState } from "react";
import { apiUrl } from "../config";

export type ServiceBadgeState = "active" | "waking" | "offline" | "connecting" | "sleeping";

export interface ServiceStatus {
  label: string;
  key: string;
  status: ServiceBadgeState;
  meta?: string;
}

interface FullHealth {
  services: ServiceStatus[];
  lastCheckedAt: Date | null;
  error: string | null;
}

const POLL_INTERVAL_MS = 15_000;
/** Must exceed backend health probe budgets (DB 8s + Redis 1s + overhead). */
const REQUEST_TIMEOUT_MS = 15_000;
/** Process liveness only — must stay tiny; no DB/Redis. */
const LIVE_TIMEOUT_MS = 3_000;

const DEFAULT_SERVICES: ServiceStatus[] = [
  { label: "Render Server", key: "render", status: "sleeping" },
  { label: "Neon Database", key: "db", status: "sleeping" },
  { label: "Redis Cache", key: "redis", status: "sleeping" },
  { label: "Market Feed", key: "feed", status: "sleeping" },
  { label: "FYERS API", key: "fyers", status: "sleeping" },
  { label: "Scanner Workers", key: "scanner", status: "sleeping" },
  { label: "WebSocket", key: "ws", status: "sleeping" },
  { label: "Scheduler", key: "scheduler", status: "sleeping" },
];

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const name = (error as { name?: string }).name;
  const msg = String((error as { message?: string }).message || "");
  return name === "AbortError" || /aborted|signal is aborted/i.test(msg);
}

function mapComponentStatus(
  raw: unknown,
  opts?: { treatNotConfiguredAsActive?: boolean },
): { status: ServiceBadgeState; meta?: string } {
  const v = String(raw ?? "").toLowerCase();
  if (v === "ok" || v === "connected" || v === "active" || v === "idle") {
    return { status: "active", meta: v === "idle" ? "idle" : undefined };
  }
  if (v === "not_configured") {
    return {
      status: opts?.treatNotConfiguredAsActive ? "active" : "sleeping",
      meta: "n/a",
    };
  }
  if (v === "waking" || v === "connecting") {
    return { status: "waking", meta: v };
  }
  if (v === "disconnected") {
    return { status: "connecting", meta: "disconnected" };
  }
  if (v === "error" || v === "offline") {
    return { status: "offline" };
  }
  return { status: "sleeping" };
}

async function fetchJsonWithTimeout(
  path: string,
  timeoutMs: number,
  parentSignal?: AbortSignal,
): Promise<{ ok: boolean; status: number; latencyMs: number; data: Record<string, unknown>; timedOut: boolean; aborted: boolean }> {
  const controller = new AbortController();
  const onParentAbort = () => controller.abort();
  if (parentSignal) {
    if (parentSignal.aborted) {
      controller.abort();
    } else {
      parentSignal.addEventListener("abort", onParentAbort, { once: true });
    }
  }
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = performance.now();
  try {
    const response = await fetch(apiUrl(path), {
      method: "GET",
      credentials: "include",
      headers: { "Cache-Control": "no-cache", Accept: "application/json" },
      signal: controller.signal,
    });
    const latencyMs = Math.round(performance.now() - startedAt);
    let data: Record<string, unknown> = {};
    try {
      data = (await response.json()) as Record<string, unknown>;
    } catch {
      data = {};
    }
    return { ok: response.ok, status: response.status, latencyMs, data, timedOut: false, aborted: false };
  } catch (error) {
    const aborted = isAbortError(error);
    // Abort from timeout vs parent unmount: if parent aborted, mark aborted; else timeout.
    const timedOut = aborted && !(parentSignal?.aborted);
    return {
      ok: false,
      status: 0,
      latencyMs: Math.round(performance.now() - startedAt),
      data: {},
      timedOut,
      aborted: Boolean(parentSignal?.aborted),
    };
  } finally {
    window.clearTimeout(timeoutId);
    if (parentSignal) {
      parentSignal.removeEventListener("abort", onParentAbort);
    }
  }
}

export function useInfrastructureHealth() {
  const [health, setHealth] = useState<FullHealth>({
    services: DEFAULT_SERVICES.map((s) => ({ ...s })),
    lastCheckedAt: null,
    error: null,
  });

  useEffect(() => {
    let isMounted = true;
    let activeController: AbortController | null = null;

    async function pingHealth() {
      // Cancel any prior in-flight probe so we never stack polls.
      activeController?.abort();
      const controller = new AbortController();
      activeController = controller;
      const startedAt = performance.now();

      try {
        // 1) Pure process liveness — proves the server process/event loop can answer.
        console.info("[infra-health] live →", apiUrl("/health/live"));
        const live = await fetchJsonWithTimeout("/health/live", LIVE_TIMEOUT_MS, controller.signal);
        if (!isMounted || controller.signal.aborted) return;

        // 2) Full dependency probe (DB/Redis/engine flags).
        console.info("[infra-health] full →", apiUrl("/health"));
        const full = await fetchJsonWithTimeout("/health", REQUEST_TIMEOUT_MS, controller.signal);
        if (!isMounted || controller.signal.aborted) return;

        const totalMs = Math.round(performance.now() - startedAt);
        const now = new Date();

        // Case A: process is dead / unreachable (live failed hard or timed out).
        if (!live.ok && !live.aborted) {
          const failStatus: ServiceBadgeState = live.timedOut ? "waking" : "offline";
          const message = live.timedOut
            ? "Health check timed out — server may be waking up. Retrying…"
            : "Health check failed — server unreachable";
          console.warn("[infra-health] live failed", { timedOut: live.timedOut, message, liveMs: live.latencyMs });
          setHealth({
            services: DEFAULT_SERVICES.map((s) => ({
              ...s,
              status: failStatus,
              meta: live.timedOut ? "timeout" : undefined,
            })),
            lastCheckedAt: now,
            error: message,
          });
          return;
        }

        // Case B: process is alive. Never paint ALL services "Waking Up" just because
        // the dependency probe was slow (e.g. scanner CPU previously blocked the loop,
        // or Neon cold start). Show render/scanner as active; mark deps connecting.
        if (!full.ok) {
          const busyMeta = full.timedOut ? "busy" : "error";
          const message = full.timedOut
            ? "Dependency health slow — process is alive. Scanner may be busy. Retrying…"
            : "Dependency health failed — process is alive";
          console.warn("[infra-health] full failed while live ok", {
            timedOut: full.timedOut,
            liveMs: live.latencyMs,
            fullMs: full.latencyMs,
            totalMs,
          });
          setHealth({
            services: [
              {
                label: "Render Server",
                key: "render",
                status: "active",
                meta: `live ${live.latencyMs}ms`,
              },
              { label: "Neon Database", key: "db", status: "connecting", meta: busyMeta },
              { label: "Redis Cache", key: "redis", status: "connecting", meta: busyMeta },
              { label: "Market Feed", key: "feed", status: "connecting", meta: busyMeta },
              { label: "FYERS API", key: "fyers", status: "connecting", meta: busyMeta },
              { label: "Scanner Workers", key: "scanner", status: "active", meta: "process up" },
              { label: "WebSocket", key: "ws", status: "connecting", meta: busyMeta },
              { label: "Scheduler", key: "scheduler", status: "active", meta: "in-process" },
            ],
            lastCheckedAt: now,
            error: message,
          });
          return;
        }

        const healthData = full.data;
        const latencyMs = full.latencyMs;
        const db = mapComponentStatus(healthData?.database);
        const redis = mapComponentStatus(healthData?.redis, { treatNotConfiguredAsActive: true });
        const fyers = mapComponentStatus(healthData?.fyers);
        const ws = mapComponentStatus(healthData?.websocket);
        const scannerStatus: ServiceBadgeState = "active";
        const schedulerStatus: ServiceBadgeState = "active";

        const services: ServiceStatus[] = [
          {
            label: "Render Server",
            key: "render",
            status: "active",
            meta: `${latencyMs}ms`,
          },
          {
            label: "Neon Database",
            key: "db",
            status: db.status,
            meta: db.status === "active" ? `${latencyMs}ms` : db.meta,
          },
          {
            label: "Redis Cache",
            key: "redis",
            status: redis.status,
            meta: redis.meta ?? (redis.status === "active" ? "cached" : undefined),
          },
          {
            label: "Market Feed",
            key: "feed",
            status: fyers.status === "active" ? "active" : fyers.status === "offline" ? "connecting" : fyers.status,
            meta: fyers.status === "active" ? "ready" : "connecting...",
          },
          {
            label: "FYERS API",
            key: "fyers",
            status: fyers.status === "active" ? "active" : fyers.status === "sleeping" ? "connecting" : fyers.status,
            meta: fyers.meta,
          },
          {
            label: "Scanner Workers",
            key: "scanner",
            status: scannerStatus,
            meta: "ready",
          },
          {
            label: "WebSocket",
            key: "ws",
            status: ws.status === "active" ? "active" : ws.status === "offline" ? "connecting" : ws.status,
            meta: ws.meta ?? (ws.status === "active" ? "connected" : "connecting..."),
          },
          {
            label: "Scheduler",
            key: "scheduler",
            status: schedulerStatus,
            meta: "in-process",
          },
        ];

        console.info("[infra-health] ok", {
          liveMs: live.latencyMs,
          fullMs: latencyMs,
          totalMs,
          database: healthData?.database,
          redis: healthData?.redis,
        });
        setHealth({ services, lastCheckedAt: now, error: null });
      } catch (error) {
        if (!isMounted) return;
        const timedOut = isAbortError(error);
        const now = new Date();
        const failStatus: ServiceBadgeState = timedOut ? "waking" : "offline";
        const message = timedOut
          ? "Health check timed out — server may be waking up. Retrying…"
          : error instanceof Error
            ? error.message
            : "Health check failed";
        console.warn("[infra-health] failed", { timedOut, message });
        setHealth({
          services: DEFAULT_SERVICES.map((s) => ({
            ...s,
            status: failStatus,
            meta: timedOut ? "timeout" : undefined,
          })),
          lastCheckedAt: now,
          error: message,
        });
      } finally {
        if (activeController === controller) {
          activeController = null;
        }
      }
    }

    void pingHealth();
    const intervalId = window.setInterval(() => void pingHealth(), POLL_INTERVAL_MS);

    return () => {
      isMounted = false;
      activeController?.abort();
      window.clearInterval(intervalId);
    };
  }, []);

  return health;
}
