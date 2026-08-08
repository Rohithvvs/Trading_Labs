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
      const controller = new AbortController();
      activeController = controller;
      // Capture controller locally to avoid stale reference in timeout callback
      const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
      const startedAt = performance.now();

      try {
        const endpoint = apiUrl("/health");
        console.info("[infra-health] request →", endpoint);
        const response = await fetch(endpoint, {
          method: "GET",
          credentials: "include",
          headers: { "Cache-Control": "no-cache", Accept: "application/json" },
          signal: controller.signal,
        });

        const latencyMs = Math.round(performance.now() - startedAt);
        if (!isMounted) return;

        let healthData: Record<string, any> = {};
        try {
          healthData = await response.json();
        } catch {
          healthData = {};
        }

        const renderOk = response.ok;
        // Trust explicit backend component fields — never invent "ok" from latency alone.
        const db = mapComponentStatus(healthData?.database);
        const redis = mapComponentStatus(healthData?.redis, { treatNotConfiguredAsActive: true });
        const fyers = mapComponentStatus(healthData?.fyers);
        const ws = mapComponentStatus(healthData?.websocket);
        // Scanner workers / scheduler share process with API when /health is reachable.
        const scannerStatus: ServiceBadgeState = renderOk ? "active" : "offline";
        const schedulerStatus: ServiceBadgeState = renderOk ? "active" : "offline";

        const now = new Date();
        const services: ServiceStatus[] = [
          {
            label: "Render Server",
            key: "render",
            status: renderOk ? "active" : "offline",
            meta: renderOk ? `${latencyMs}ms` : undefined,
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
            meta: scannerStatus === "active" ? "ready" : undefined,
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
            meta: schedulerStatus === "active" ? "in-process" : undefined,
          },
        ];

        console.info("[infra-health] ok", { latencyMs, database: healthData?.database, redis: healthData?.redis });
        setHealth({ services, lastCheckedAt: now, error: null });
      } catch (error) {
        // Unmount cleanup aborts in-flight probes — do not paint the stack OFFLINE.
        if (!isMounted) return;
        const timedOut = isAbortError(error);
        const now = new Date();
        // Timeout → "waking" (cold start / slow network). Hard failure → offline.
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
        window.clearTimeout(timeoutId);
        activeController = null;
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
