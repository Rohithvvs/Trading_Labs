/**
 * Paper Order page performance instrumentation.
 * Collects API / cache / render timings and prints a ranked report.
 * Production-safe: console only, no network side-effects.
 */

export type PerfLaneStatus = "pending" | "cache_hit" | "ok" | "timeout" | "error" | "skipped";

export type PerfSample = {
  name: string;
  category: "api" | "cache" | "render" | "network" | "db" | "ui";
  durationMs: number;
  status: PerfLaneStatus;
  detail?: string;
  cacheHit?: boolean;
};

type Session = {
  pageStart: number;
  samples: PerfSample[];
  cacheHits: number;
  cacheMisses: number;
  firstPaintMs: number | null;
  interactiveMs: number | null;
};

const sessions = new Map<number, Session>();

function now(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

export function startPaperOrderPerf(gen: number): void {
  sessions.set(gen, {
    pageStart: now(),
    samples: [],
    cacheHits: 0,
    cacheMisses: 0,
    firstPaintMs: null,
    interactiveMs: null,
  });
  // Progressive shell paints synchronously — record immediately
  markFirstPaint(gen);
  markInteractive(gen);
}

export function markFirstPaint(gen: number): void {
  const s = sessions.get(gen);
  if (!s || s.firstPaintMs != null) return;
  s.firstPaintMs = Math.max(0, now() - s.pageStart);
  s.samples.push({
    name: "first_paint_shell",
    category: "render",
    durationMs: s.firstPaintMs,
    status: "ok",
    detail: "Header + form shell (sync)",
  });
}

export function markInteractive(gen: number): void {
  const s = sessions.get(gen);
  if (!s || s.interactiveMs != null) return;
  s.interactiveMs = Math.max(0, now() - s.pageStart);
  s.samples.push({
    name: "interactive_ui",
    category: "ui",
    durationMs: s.interactiveMs,
    status: "ok",
    detail: "Order form editable",
  });
}

export function recordCacheHit(gen: number, name: string, detail?: string): void {
  const s = sessions.get(gen);
  if (!s) return;
  s.cacheHits += 1;
  s.samples.push({
    name,
    category: "cache",
    durationMs: 0,
    status: "cache_hit",
    cacheHit: true,
    detail,
  });
}

export function recordCacheMiss(gen: number, name: string): void {
  const s = sessions.get(gen);
  if (!s) return;
  s.cacheMisses += 1;
  s.samples.push({
    name: `${name}_miss`,
    category: "cache",
    durationMs: 0,
    status: "pending",
    cacheHit: false,
  });
}

export function recordSample(gen: number, sample: PerfSample): void {
  const s = sessions.get(gen);
  if (!s) return;
  s.samples.push(sample);
  if (sample.cacheHit === true) s.cacheHits += 1;
  if (sample.cacheHit === false) s.cacheMisses += 1;
}

export async function timeLane<T>(
  gen: number,
  name: string,
  category: PerfSample["category"],
  fn: () => Promise<T>,
  opts?: { timeoutMs?: number; label?: string },
): Promise<{ value: T | null; timedOut: boolean; durationMs: number; error?: string }> {
  const started = now();
  const timeoutMs = opts?.timeoutMs;
  let timedOut = false;
  let error: string | undefined;
  let value: T | null = null;

  try {
    if (timeoutMs != null && timeoutMs > 0) {
      value = await Promise.race([
        fn(),
        new Promise<T>((_, reject) => {
          window.setTimeout(() => {
            timedOut = true;
            reject(new Error(`${opts?.label || name} timed out after ${timeoutMs}ms`));
          }, timeoutMs);
        }),
      ]);
    } else {
      value = await fn();
    }
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
    if (!timedOut && /timed out/i.test(error)) timedOut = true;
    value = null;
  }

  const durationMs = Math.round(now() - started);
  recordSample(gen, {
    name,
    category,
    durationMs,
    status: timedOut ? "timeout" : error ? "error" : "ok",
    detail: error,
  });
  return { value, timedOut, durationMs, error };
}

export function printRankedPerfReport(gen: number, extra?: Record<string, unknown>): void {
  const s = sessions.get(gen);
  if (!s) return;
  const totalMs = Math.round(now() - s.pageStart);
  const ranked = [...s.samples].sort((a, b) => b.durationMs - a.durationMs);
  const cacheTotal = s.cacheHits + s.cacheMisses;
  const hitRatio = cacheTotal > 0 ? Math.round((s.cacheHits / cacheTotal) * 100) : null;

  const lines = [
    "======== PAPER ORDER PERFORMANCE REPORT ========",
    `gen=${gen} total_ms=${totalMs}`,
    `first_paint_ms=${s.firstPaintMs ?? "n/a"} interactive_ms=${s.interactiveMs ?? "n/a"}`,
    `cache_hits=${s.cacheHits} cache_misses=${s.cacheMisses} hit_ratio=${hitRatio != null ? `${hitRatio}%` : "n/a"}`,
    "--- ranked by duration (slowest first) ---",
    ...ranked.map(
      (r, i) =>
        `${String(i + 1).padStart(2, " ")}. ${r.durationMs.toString().padStart(5, " ")}ms  [${r.category}] ${r.name} (${r.status})${r.detail ? ` — ${r.detail}` : ""}`,
    ),
    "================================================",
  ];

  console.info(lines.join("\n"), extra ?? {});
  // Keep session for a bit for retries; drop old gens
  for (const key of sessions.keys()) {
    if (key < gen - 2) sessions.delete(key);
  }
}

export function getPerfSnapshot(gen: number): Session | null {
  return sessions.get(gen) ?? null;
}
