import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchRe001RecentScans,
  fetchRe001Registration,
  fetchRe001ScanComparison,
  fetchRe002Health,
  fetchRe002RecentScans,
  fetchRe002Registration,
  fetchRe002ScanComparison,
} from "../api";
import {
  IconActivity,
  IconBar,
  IconBrain,
  IconChart,
  IconCheck,
  IconEye,
  IconFlask,
  IconHistory,
  IconLayers,
  IconScale,
  IconTarget,
  IconTrending,
  IconTrophy,
  IconWallet,
  LabConfidenceBarChart,
  LabDonutChart,
  LabMetricCard,
  LabPerformanceChart,
  LabStatusBadge,
  type LabBarPoint,
  type LabDonutSlice,
  type LabLinePoint,
} from "../components/recommendation-lab";
import "../components/recommendation-lab/recommendationLab.css";

/* -------------------------------------------------------------------------- */
/* Types (unchanged data contracts)                                           */
/* -------------------------------------------------------------------------- */

type Re001ComparisonRow = {
  symbol: string;
  recommendation_id: string;
  production_action?: string | null;
  production_score?: number | null;
  re001_state: string;
  confidence_score: number;
  strategy_name?: string | null;
  is_mismatch?: boolean | null;
};

type Re002ComparisonRow = {
  symbol: string;
  recommendation_id: string;
  production_action?: string | null;
  production_score?: number | null;
  re002_state: string;
  confidence_score: number;
  strategy_name?: string | null;
  strategy_family?: string | null;
  is_mismatch?: boolean | null;
  experiment_id?: string | null;
};

type MergedRow = {
  symbol: string;
  production_action?: string | null;
  production_score?: number | null;
  re001_state?: string | null;
  re001_confidence?: number | null;
  re001_strategy?: string | null;
  re001_mismatch?: boolean | null;
  re001_recommendation_id?: string | null;
  re002_state?: string | null;
  re002_confidence?: number | null;
  re002_strategy?: string | null;
  re002_mismatch?: boolean | null;
  re002_recommendation_id?: string | null;
  re002_experiment_id?: string | null;
};

type ScanSummary = {
  scan_run_id: string;
  decision_count: number;
  latest_created_at?: string | null;
};

type Registration = {
  engine_id: string;
  name: string;
  engine_version: string;
  stage: string;
  enabled: boolean;
  experiment_id?: string | null;
  active?: boolean | null;
};

/* -------------------------------------------------------------------------- */
/* Pure helpers (same business rules as before)                               */
/* -------------------------------------------------------------------------- */

function isEngineActive(reg: Registration | null): boolean {
  if (!reg) return false;
  if (typeof reg.active === "boolean") return reg.active;
  if (!reg.enabled) return false;
  const stage = String(reg.stage || "OFF").toUpperCase();
  return stage === "LAB_SHADOW" || stage === "PAPER_LINKED";
}

function mergeComparisonRows(
  re001: Re001ComparisonRow[],
  re002: Re002ComparisonRow[],
): MergedRow[] {
  const bySymbol = new Map<string, MergedRow>();

  for (const r of re001) {
    const sym = String(r.symbol || "").toUpperCase();
    if (!sym) continue;
    bySymbol.set(sym, {
      symbol: sym,
      production_action: r.production_action,
      production_score: r.production_score,
      re001_state: r.re001_state,
      re001_confidence: r.confidence_score,
      re001_strategy: r.strategy_name,
      re001_mismatch: r.is_mismatch,
      re001_recommendation_id: r.recommendation_id,
    });
  }

  for (const r of re002) {
    const sym = String(r.symbol || "").toUpperCase();
    if (!sym) continue;
    const existing = bySymbol.get(sym) || { symbol: sym };
    bySymbol.set(sym, {
      ...existing,
      production_action: existing.production_action ?? r.production_action,
      production_score: existing.production_score ?? r.production_score,
      re002_state: r.re002_state,
      re002_confidence: r.confidence_score,
      re002_strategy: r.strategy_name,
      re002_mismatch: r.is_mismatch,
      re002_recommendation_id: r.recommendation_id,
      re002_experiment_id: r.experiment_id,
    });
  }

  return Array.from(bySymbol.values()).sort((a, b) => a.symbol.localeCompare(b.symbol));
}

function stageToStatus(reg: Registration | null): string {
  if (!reg) return "INACTIVE";
  if (isEngineActive(reg)) {
    const stage = String(reg.stage || "").toUpperCase();
    if (stage === "PAPER_LINKED") return "PRODUCTION";
    return "ACTIVE";
  }
  if (!reg.enabled) return "DRAFT";
  return "INACTIVE";
}

function formatWhen(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function relativeTime(iso?: string | null): string {
  if (!iso) return "";
  try {
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return "";
    const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 48) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
    const days = Math.round(hrs / 24);
    return `${days} day${days === 1 ? "" : "s"} ago`;
  } catch {
    return "";
  }
}

function avg(nums: number[]): number | null {
  if (!nums.length) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function confLabel(c?: number | null): string {
  if (c == null || Number.isNaN(c)) return "—";
  if (c >= 0.75) return "High";
  if (c >= 0.45) return "Medium";
  return "Low";
}

/* -------------------------------------------------------------------------- */
/* Page                                                                       */
/* -------------------------------------------------------------------------- */

export default function RecommendationLabPage() {
  const [scanRunId, setScanRunId] = useState("");
  const [recent, setRecent] = useState<ScanSummary[]>([]);
  const [re001Rows, setRe001Rows] = useState<Re001ComparisonRow[]>([]);
  const [re002Rows, setRe002Rows] = useState<Re002ComparisonRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [bootLoading, setBootLoading] = useState(true);
  const [registration, setRegistration] = useState<Registration | null>(null);
  const [re002Registration, setRe002Registration] = useState<Registration | null>(null);
  const [re002Health, setRe002Health] = useState<Record<string, unknown> | null>(null);
  const [tableFilter, setTableFilter] = useState("");
  const [page, setPage] = useState(0);
  const pageSize = 12;

  /* ---------- Progressive bootstrap (paint shell ASAP; no waterfall) ---------- */
  /* Phase A: registration + recent scans (KPIs / engines) — clears bootLoading     */
  /* Phase B: scan comparison (table) — uses `loading` only                         */
  /* Phase C: RE-002 health (non-blocking, does not gate shell)                     */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const t0 = performance.now();
      try {
        // Phase A — critical path for interactive shell
        const tA = performance.now();
        const [reg001Res, reg002Res, scans001Res, scans002Res] = await Promise.all([
          fetchRe001Registration().catch(() => null),
          fetchRe002Registration().catch(() => null),
          fetchRe001RecentScans(20, { minDecisions: 1, preferCohorts: true }).catch(() => ({
            items: [] as ScanSummary[],
          })),
          fetchRe002RecentScans(20, { minDecisions: 1, preferCohorts: true }).catch(() => ({
            items: [] as ScanSummary[],
          })),
        ]);

        if (cancelled) return;

        if (reg001Res) setRegistration(reg001Res);
        if (reg002Res) setRe002Registration(reg002Res);

        const inactiveNotes: string[] = [];
        if (reg001Res && (!reg001Res.enabled || !isEngineActive(reg001Res))) {
          inactiveNotes.push(
            `RE-001 is not active (enabled=${String(reg001Res.enabled)}, stage=${reg001Res.stage}). Set RE001_ENABLED=true and RE001_STAGE=LAB_SHADOW to write RE-001 lab rows.`,
          );
        }
        if (reg002Res && (!reg002Res.enabled || !isEngineActive(reg002Res))) {
          inactiveNotes.push(
            `RE-002 is not active (enabled=${String(reg002Res.enabled)}, stage=${reg002Res.stage}). Set RE002_ENABLED=true and RE002_STAGE=LAB_SHADOW to write RE-002 lab rows.`,
          );
        }
        if (inactiveNotes.length) setInfo(inactiveNotes.join(" "));

        const byId = new Map<string, ScanSummary>();
        for (const s of [...(scans001Res?.items || []), ...(scans002Res?.items || [])]) {
          if (!s?.scan_run_id) continue;
          const prev = byId.get(s.scan_run_id);
          if (!prev || (s.decision_count || 0) > (prev.decision_count || 0)) {
            byId.set(s.scan_run_id, s);
          }
        }
        const items = Array.from(byId.values()).sort(
          (a, b) => (b.decision_count || 0) - (a.decision_count || 0),
        );
        setRecent(items);

        // Shell + KPIs interactive — do not wait for comparison / health
        setBootLoading(false);
        console.debug(
          `[Perf] Recommendation Lab phase A (shell) in ${(performance.now() - tA).toFixed(1)}ms`,
        );

        // Phase C — health in background (does not block KPIs)
        void fetchRe002Health(7)
          .then((health002Res) => {
            if (!cancelled && health002Res) setRe002Health(health002Res);
          })
          .catch(() => undefined);

        const best = items.find((s) => (s.decision_count || 0) > 1) || items[0] || null;
        if (best?.scan_run_id) {
          setScanRunId(best.scan_run_id);
          setLoading(true);
          const tB = performance.now();
          // Phase B — comparison for auto-selected cohort (parallel engines)
          const [data001, data002] = await Promise.all([
            fetchRe001ScanComparison(best.scan_run_id).catch(() => ({
              items: [] as Re001ComparisonRow[],
            })),
            fetchRe002ScanComparison(best.scan_run_id).catch(() => ({
              items: [] as Re002ComparisonRow[],
            })),
          ]);
          if (!cancelled) {
            setRe001Rows(data001.items || []);
            setRe002Rows(data002.items || []);
            setLoading(false);
            console.debug(
              `[Perf] Recommendation Lab phase B (comparison) in ${(performance.now() - tB).toFixed(1)}ms`,
            );
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load recommendation lab data.");
          setBootLoading(false);
          setLoading(false);
        }
      } finally {
        if (!cancelled) {
          setBootLoading(false);
          console.debug(
            `[Perf] Recommendation Lab bootstrap complete in ${(performance.now() - t0).toFixed(1)}ms`,
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async () => {
    if (!scanRunId.trim()) {
      setError("Enter or select a scan_run_id");
      return;
    }
    setLoading(true);
    setError(null);
    setPage(0);
    const id = scanRunId.trim();
    try {
      const [data001, data002] = await Promise.all([
        fetchRe001ScanComparison(id).catch(() => ({ items: [] as Re001ComparisonRow[] })),
        fetchRe002ScanComparison(id).catch(() => ({ items: [] as Re002ComparisonRow[] })),
      ]);
      const items001 = data001.items || [];
      const items002 = data002.items || [];
      setRe001Rows(items001);
      setRe002Rows(items002);
      if (!items001.length && !items002.length) {
        setInfo(
          "This scan_run_id has no RE-001 or RE-002 decision rows. It must come from a scan that ran while a lab engine was active.",
        );
      } else {
        setInfo(null);
      }
    } catch (e) {
      setRe001Rows([]);
      setRe002Rows([]);
      setError(e instanceof Error ? e.message : "Failed to load lab comparison");
    } finally {
      setLoading(false);
    }
  }, [scanRunId]);

  const rows = useMemo(() => mergeComparisonRows(re001Rows, re002Rows), [re001Rows, re002Rows]);
  const active001 = isEngineActive(registration);
  const active002 = isEngineActive(re002Registration);

  /* ---------- derived analytics (presentation only) ---------- */
  const totalRecs = useMemo(
    () => recent.reduce((s, r) => s + (r.decision_count || 0), 0),
    [recent],
  );

  const healthBuy = Number(re002Health?.buy_count ?? 0) || 0;
  const healthWatch = Number(re002Health?.watch_count ?? 0) || 0;
  const healthReject = Number(re002Health?.reject_count ?? 0) || 0;
  const healthTotal = Number(re002Health?.total ?? 0) || healthBuy + healthWatch + healthReject;

  const avgConf001 = useMemo(
    () => avg(re001Rows.map((r) => Number(r.confidence_score)).filter((n) => Number.isFinite(n))),
    [re001Rows],
  );
  const avgConf002 = useMemo(
    () => avg(re002Rows.map((r) => Number(r.confidence_score)).filter((n) => Number.isFinite(n))),
    [re002Rows],
  );
  const avgProdScore = useMemo(
    () =>
      avg(
        rows
          .map((r) => (r.production_score != null ? Number(r.production_score) : NaN))
          .filter((n) => Number.isFinite(n)),
      ),
    [rows],
  );

  const bestEngine = useMemo(() => {
    const a = avgConf001 ?? -1;
    const b = avgConf002 ?? -1;
    if (a < 0 && b < 0) {
      if (active001 && !active002) return registration?.engine_id || "RE-001";
      if (active002 && !active001) return re002Registration?.engine_id || "RE-002";
      return "—";
    }
    if (b > a) return `${re002Registration?.engine_id || "RE-002"} v${re002Registration?.engine_version || "—"}`;
    return `${registration?.engine_id || "RE-001"} v${registration?.engine_version || "—"}`;
  }, [avgConf001, avgConf002, active001, active002, registration, re002Registration]);

  const engines = useMemo(() => {
    const list: Array<{
      id: string;
      name: string;
      version: string;
      type: string;
      status: string;
      created: string;
      recommendations: number;
      experimentId?: string | null;
      active: boolean;
    }> = [];
    if (registration) {
      list.push({
        id: registration.engine_id,
        name: registration.name || "RE-001 Trend Continuation",
        version: registration.engine_version,
        type: "Trend Continuation",
        status: stageToStatus(registration),
        created: "—",
        recommendations: re001Rows.length || recent[0]?.decision_count || 0,
        active: active001,
      });
    }
    if (re002Registration) {
      list.push({
        id: re002Registration.engine_id,
        name: re002Registration.name || "RE-002 RS Momentum",
        version: re002Registration.engine_version,
        type: "RS Momentum",
        status: stageToStatus(re002Registration),
        created: "—",
        recommendations: re002Rows.length || healthTotal || 0,
        experimentId: re002Registration.experiment_id,
        active: active002,
      });
    }
    return list;
  }, [
    registration,
    re002Registration,
    active001,
    active002,
    re001Rows.length,
    re002Rows.length,
    recent,
    healthTotal,
  ]);

  const signalDonut: LabDonutSlice[] = useMemo(() => {
    if (healthTotal > 0) {
      return [
        { name: "BUY", value: healthBuy, color: "#22C55E" },
        { name: "WATCH", value: healthWatch, color: "#FACC15" },
        { name: "REJECT", value: healthReject, color: "#EF4444" },
      ].filter((d) => d.value > 0);
    }
    const counts = { BUY: 0, WATCH: 0, SELL: 0, OTHER: 0 };
    for (const r of rows) {
      const s = String(r.re002_state || r.re001_state || r.production_action || "").toUpperCase();
      if (s.includes("BUY")) counts.BUY += 1;
      else if (s.includes("WATCH")) counts.WATCH += 1;
      else if (s.includes("SELL") || s.includes("REJECT")) counts.SELL += 1;
      else if (s) counts.OTHER += 1;
    }
    return [
      { name: "BUY", value: counts.BUY, color: "#22C55E" },
      { name: "WATCH", value: counts.WATCH, color: "#FACC15" },
      { name: "SELL / REJECT", value: counts.SELL, color: "#EF4444" },
      { name: "Other", value: counts.OTHER, color: "#64748B" },
    ].filter((d) => d.value > 0);
  }, [healthTotal, healthBuy, healthWatch, healthReject, rows]);

  const strategyDonut: LabDonutSlice[] = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of re002Rows) {
      const name = String(r.strategy_name || r.strategy_family || "Unspecified").trim() || "Unspecified";
      map.set(name, (map.get(name) || 0) + 1);
    }
    for (const r of re001Rows) {
      const name = String(r.strategy_name || "Trend Continuation").trim();
      map.set(name, (map.get(name) || 0) + 1);
    }
    const palette = ["#2563EB", "#22C55E", "#FACC15", "#EF4444", "#7C3AED", "#06B6D4"];
    return Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([name, value], i) => ({ name, value, color: palette[i % palette.length] }));
  }, [re001Rows, re002Rows]);

  const statusDonut: LabDonutSlice[] = useMemo(() => {
    const active = engines.filter((e) => e.status === "ACTIVE" || e.status === "PRODUCTION").length;
    const draft = engines.filter((e) => e.status === "DRAFT" || e.status === "INACTIVE").length;
    const completed = engines.filter((e) => e.status === "COMPLETED").length;
    return [
      { name: "Active", value: active, color: "#22C55E" },
      { name: "Draft / Inactive", value: draft, color: "#FACC15" },
      { name: "Completed", value: completed, color: "#64748B" },
    ].filter((d) => d.value > 0);
  }, [engines]);

  const performanceSeries: LabLinePoint[] = useMemo(() => {
    const sorted = [...recent]
      .filter((s) => s.latest_created_at || s.scan_run_id)
      .sort((a, b) => {
        const ta = a.latest_created_at ? new Date(a.latest_created_at).getTime() : 0;
        const tb = b.latest_created_at ? new Date(b.latest_created_at).getTime() : 0;
        return ta - tb;
      })
      .slice(-8);
    return sorted.map((s, i) => ({
      label: s.latest_created_at
        ? new Date(s.latest_created_at).toLocaleDateString(undefined, { day: "2-digit", month: "short" })
        : `S${i + 1}`,
      total: s.decision_count || 0,
    }));
  }, [recent]);

  const confidenceBars: LabBarPoint[] = useMemo(() => {
    const bars: LabBarPoint[] = [];
    if (avgConf001 != null) {
      bars.push({ name: "RE-001", value: Number(avgConf001.toFixed(3)), color: "#22C55E" });
    }
    if (avgConf002 != null) {
      bars.push({ name: "RE-002", value: Number(avgConf002.toFixed(3)), color: "#2563EB" });
    }
    return bars;
  }, [avgConf001, avgConf002]);

  const topRecs = useMemo(() => {
    return rows
      .map((r) => {
        const c002 = r.re002_confidence != null && Number.isFinite(r.re002_confidence) ? r.re002_confidence : null;
        const c001 = r.re001_confidence != null && Number.isFinite(r.re001_confidence) ? r.re001_confidence : null;
        let cProd: number | null = null;
        if (r.production_score != null && Number.isFinite(r.production_score)) {
          cProd = r.production_score > 1 ? r.production_score / 100 : r.production_score;
        }

        const val002 = c002 ?? -1;
        const val001 = c001 ?? -1;
        const valProd = cProd ?? -1;

        let bestEngineName = "—";
        let bestSignal = "—";
        let bestConf: number | null = null;
        let finalScore: number | null = null;

        if (val002 >= val001 && val002 >= valProd && r.re002_state) {
          bestEngineName = "RE-002";
          bestSignal = String(r.re002_state);
          bestConf = c002;
          finalScore = (c002 ?? 0) * 100;
        } else if (val001 >= valProd && r.re001_state) {
          bestEngineName = "RE-001";
          bestSignal = String(r.re001_state);
          bestConf = c001;
          finalScore = (c001 ?? 0) * 100;
        } else if (r.production_action) {
          bestEngineName = "Production";
          bestSignal = String(r.production_action);
          bestConf = cProd;
          finalScore = r.production_score != null ? r.production_score : (cProd ?? 0) * 100;
        } else if (r.re002_state) {
          bestEngineName = "RE-002";
          bestSignal = String(r.re002_state);
          bestConf = c002;
          finalScore = (c002 ?? 0) * 100;
        } else if (r.re001_state) {
          bestEngineName = "RE-001";
          bestSignal = String(r.re001_state);
          bestConf = c001;
          finalScore = (c001 ?? 0) * 100;
        }

        return {
          ...r,
          c002,
          c001,
          cProd,
          bestEngineName,
          bestSignal,
          bestConf,
          finalScore,
        };
      })
      .sort((a, b) => (b.finalScore ?? b.bestConf ?? -1) - (a.finalScore ?? a.bestConf ?? -1));
  }, [rows]);

  const filteredRows = useMemo(() => {
    const q = tableFilter.trim().toUpperCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.symbol.includes(q) ||
        String(r.re001_state || "").toUpperCase().includes(q) ||
        String(r.re002_state || "").toUpperCase().includes(q) ||
        String(r.re002_strategy || "").toUpperCase().includes(q) ||
        String(r.re002_experiment_id || "").toUpperCase().includes(q),
    );
  }, [rows, tableFilter]);

  const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const pagedRows = filteredRows.slice(page * pageSize, page * pageSize + pageSize);

  const activity = useMemo(() => {
    const items: Array<{ text: string; time: string; tone: "green" | "amber" | "blue" | "red" }> = [];
    for (const s of recent.slice(0, 4)) {
      items.push({
        text: `Lab cohort ${s.scan_run_id.slice(0, 8)}… · ${s.decision_count} decisions`,
        time: relativeTime(s.latest_created_at) || formatWhen(s.latest_created_at),
        tone: (s.decision_count || 0) > 1 ? "green" : "blue",
      });
    }
    if (registration) {
      items.push({
        text: `RE-001 registration · stage ${registration.stage} · ${active001 ? "active" : "inactive"}`,
        time: "live",
        tone: active001 ? "green" : "amber",
      });
    }
    if (re002Registration) {
      items.push({
        text: `RE-002 registration · stage ${re002Registration.stage}${
          re002Registration.experiment_id ? ` · exp ${re002Registration.experiment_id}` : ""
        }`,
        time: "live",
        tone: active002 ? "green" : "amber",
      });
    }
    if (rows.some((r) => r.re001_mismatch || r.re002_mismatch)) {
      items.push({
        text: "Mismatch detected between production and lab engines on loaded scan",
        time: "current",
        tone: "red",
      });
    }
    return items.slice(0, 6);
  }, [recent, registration, re002Registration, active001, active002, rows]);

  const alerts = useMemo(() => {
    const items: Array<{ text: string; time: string; tone: "green" | "amber" | "blue" | "red" }> = [];
    if (!active001) {
      items.push({
        text: "RE-001 inactive — enable LAB_SHADOW to write lab rows",
        time: "now",
        tone: "amber",
      });
    }
    if (re002Registration && !active002) {
      items.push({
        text: "RE-002 inactive — enable LAB_SHADOW for RS momentum lab",
        time: "now",
        tone: "amber",
      });
    }
    if (healthBuy > 0) {
      items.push({
        text: `RE-002 health: ${healthBuy} BUY decisions in last 7 days`,
        time: "7d",
        tone: "green",
      });
    }
    const high = topRecs.filter((r) => (r.conf ?? 0) >= 0.75).length;
    if (high > 0) {
      items.push({
        text: `${high} high-confidence lab signals on loaded comparison`,
        time: "scan",
        tone: "green",
      });
    }
    if (error) {
      items.push({ text: error, time: "error", tone: "red" });
    }
    if (!items.length) {
      items.push({
        text: "Platform quiet — load a multi-symbol cohort to surface alerts",
        time: "—",
        tone: "blue",
      });
    }
    return items.slice(0, 5);
  }, [active001, active002, re002Registration, healthBuy, topRecs, error]);

  const todayLabel = useMemo(
    () =>
      new Date().toLocaleDateString(undefined, {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }),
    [],
  );

  return (
    <div className="lab-dashboard" data-testid="recommendation-lab-page">
      {/* Header */}
      <header className="lab-header">
        <div>
          <h1 className="lab-header__title">Recommendation Lab</h1>
          <p className="lab-header__subtitle">
            AI-powered multi-engine recommendation research · Production vs RE-001 vs RE-002 ·
            Experiment-driven shadow analytics
          </p>
        </div>
        <div className="lab-header__meta">
          <span className="lab-chip">
            Market <strong>NSE</strong>
          </span>
          <span className="lab-chip lab-chip--live">
            Status <strong>RESEARCH</strong>
          </span>
          <span className="lab-chip">
            Date <strong>{todayLabel}</strong>
          </span>
        </div>
      </header>

      {/* Engine registration strip (preserves original test ids) */}
      <div className="lab-engine-strip">
        {registration ? (
          <div
            className={`lab-engine-pill ${active001 ? "lab-engine-pill--active" : "lab-engine-pill--inactive"}`}
            data-testid="lab-registration-status"
          >
            <LabStatusBadge status={active001 ? "ACTIVE" : "INACTIVE"} />
            <span>
              RE-001: {registration.engine_id} · v{registration.engine_version} · enabled=
              {String(registration.enabled)} · stage={registration.stage}
            </span>
          </div>
        ) : (
          <div className="lab-engine-pill">Loading RE-001 registration…</div>
        )}
        {re002Registration ? (
          <div
            className={`lab-engine-pill ${active002 ? "lab-engine-pill--active" : "lab-engine-pill--inactive"}`}
            data-testid="lab-re002-registration-status"
          >
            <LabStatusBadge status={active002 ? "ACTIVE" : "INACTIVE"} />
            <span>
              Lab · Experimental · RE-002: {re002Registration.engine_id} · v
              {re002Registration.engine_version} · enabled={String(re002Registration.enabled)} · stage=
              {re002Registration.stage}
              {re002Registration.experiment_id
                ? ` · experiment=${re002Registration.experiment_id}`
                : ""}
            </span>
          </div>
        ) : (
          <div className="lab-engine-pill">RE-002 registration unavailable (or UI gated).</div>
        )}
        {re002Health ? (
          <div className="lab-engine-pill" data-testid="lab-re002-health">
            RE-002 health (7d): BUY={String(re002Health.buy_count ?? 0)} · WATCH=
            {String(re002Health.watch_count ?? 0)} · REJECT={String(re002Health.reject_count ?? 0)} ·
            total={String(re002Health.total ?? 0)}
            {re002Health.avg_rs_of_buys != null
              ? ` · avg RS of BUYs=${String(re002Health.avg_rs_of_buys)}`
              : ""}
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="lab-banner lab-banner--error" role="alert">
          {error}
        </div>
      ) : null}
      {info ? (
        <div className="lab-banner lab-banner--info" role="status">
          {info}
        </div>
      ) : null}

      {/* KPI cards */}
      <section className="lab-kpi-row" aria-label="Recommendation lab KPIs">
        <LabMetricCard
          label="Lab Engines"
          value={engines.length}
          subtitle={`${engines.filter((e) => e.active).length} active · ${engines.filter((e) => !e.active).length} inactive`}
          icon={<IconFlask size={18} />}
          accent="blue"
          loading={bootLoading}
        />
        <LabMetricCard
          label="Total Recommendations"
          value={totalRecs.toLocaleString()}
          subtitle={`${recent.length} recent scan cohorts`}
          trend={rows.length ? `+${rows.length} loaded` : undefined}
          trendTone="up"
          icon={<IconLayers size={18} />}
          accent="cyan"
          loading={bootLoading}
        />
        <LabMetricCard
          label="RE-002 BUY (7d)"
          value={healthBuy.toLocaleString()}
          subtitle={`WATCH ${healthWatch} · REJECT ${healthReject}`}
          icon={<IconTrending size={18} />}
          accent="green"
        />
        <LabMetricCard
          label="Avg Confidence"
          value={
            avgConf001 != null || avgConf002 != null
              ? (
                  avg(
                    [avgConf001, avgConf002].filter((n): n is number => n != null && Number.isFinite(n)),
                  ) ?? 0
                ).toFixed(2)
              : "—"
          }
          subtitle={
            avgConf001 != null || avgConf002 != null
              ? `RE-001 ${avgConf001?.toFixed(2) ?? "—"} · RE-002 ${avgConf002?.toFixed(2) ?? "—"}`
              : "Load comparison"
          }
          icon={<IconTarget size={18} />}
          accent="purple"
        />
        <LabMetricCard
          label="Best Performing Engine"
          value={bestEngine}
          subtitle={avgProdScore != null ? `Avg prod score ${avgProdScore.toFixed(1)}` : "By avg lab confidence"}
          trend={avgConf001 != null || avgConf002 != null ? "ranked" : undefined}
          icon={<IconTrophy size={18} />}
          accent="amber"
        />
      </section>

      {/* Scan Comparison (100% width) */}
      <div className="lab-grid-main">
        <section className="lab-card" aria-label="Scan comparison controls">
          <header className="lab-card__header">
            <h3 className="lab-card__title">Scan Comparison</h3>
          </header>
          <div className="lab-controls">
            <select
              className="lab-select"
              value={scanRunId}
              onChange={(e) => setScanRunId(e.target.value)}
              data-testid="lab-scan-run-select"
              aria-label="Select recent scan"
            >
              <option value="">Select recent scan…</option>
              {recent.map((s) => (
                <option key={s.scan_run_id} value={s.scan_run_id}>
                  {s.decision_count > 1 ? "COHORT" : "SINGLE"} · {s.decision_count} symbols ·{" "}
                  {s.scan_run_id}
                </option>
              ))}
            </select>
            <input
              className="lab-input"
              placeholder="or paste scan_run_id"
              value={scanRunId}
              onChange={(e) => setScanRunId(e.target.value)}
              data-testid="lab-scan-run-id"
              aria-label="Scan run id"
            />
            <button
              type="button"
              className="lab-btn lab-btn--primary"
              onClick={() => void load()}
              disabled={loading}
            >
              {loading ? "Loading…" : "Load comparison"}
            </button>
          </div>

          <div className="lab-controls" style={{ marginBottom: 8 }}>
            <input
              className="lab-input"
              placeholder="Filter symbol / state / strategy…"
              value={tableFilter}
              onChange={(e) => {
                setTableFilter(e.target.value);
                setPage(0);
              }}
              aria-label="Filter comparison table"
            />
          </div>

          <div className="lab-table-wrap">
            <table className="lab-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Production</th>
                  <th>RE-001</th>
                  <th>RE-002</th>
                  <th>RE-002 strategy</th>
                  <th>Experiment</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="lab-empty">
                      No lab rows for this scan.
                    </td>
                  </tr>
                ) : (
                  pagedRows.map((r) => (
                    <tr
                      key={`${r.symbol}-${r.re001_recommendation_id || ""}-${r.re002_recommendation_id || ""}`}
                    >
                      <td className="lab-table__sym">{r.symbol}</td>
                      <td>
                        {r.production_action ? (
                          <LabStatusBadge status={String(r.production_action)} />
                        ) : (
                          "—"
                        )}
                        {r.production_score != null ? (
                          <span style={{ marginLeft: 6, color: "var(--lab-muted)" }}>
                            ({r.production_score.toFixed(1)})
                          </span>
                        ) : null}
                      </td>
                      <td>
                        {r.re001_state ? (
                          <>
                            <LabStatusBadge status={String(r.re001_state)} />{" "}
                            <span style={{ color: "var(--lab-muted)" }}>
                              ({r.re001_confidence?.toFixed?.(2) ?? r.re001_confidence ?? "—"})
                            </span>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        {r.re002_state ? (
                          <>
                            <LabStatusBadge status={String(r.re002_state)} />{" "}
                            <span style={{ color: "var(--lab-muted)" }}>
                              ({r.re002_confidence?.toFixed?.(2) ?? r.re002_confidence ?? "—"})
                            </span>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>{r.re002_strategy || "—"}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--lab-muted)" }}>
                        {r.re002_experiment_id || "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="lab-table__footer" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <span>
              Showing {filteredRows.length === 0 ? 0 : page * pageSize + 1}–
              {Math.min(filteredRows.length, (page + 1) * pageSize)} of {filteredRows.length}
            </span>
            <span style={{ display: "inline-flex", gap: 6 }}>
              <button
                type="button"
                className="lab-btn lab-btn--ghost"
                disabled={page <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                Prev
              </button>
              <button
                type="button"
                className="lab-btn lab-btn--ghost"
                disabled={page >= pageCount - 1}
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              >
                Next
              </button>
            </span>
          </div>
        </section>
      </div>

      {/* 2-Column Dashboard Rows (50% + 50%) */}
      <div className="lab-grid-2col">
        {/* Row 1: Signal Distribution | Strategy Distribution */}
        <LabDonutChart
          title="Signal Distribution"
          data={signalDonut}
          emptyLabel="Load comparison or wait for RE-002 health."
          testId="lab-signal-donut"
        />

        <LabDonutChart
          title="Strategy Distribution"
          data={strategyDonut}
          emptyLabel="Strategy mix appears after comparison load."
          testId="lab-strategy-donut"
        />

        {/* Row 2: Recent Experiment Activity | Engine Status Summary */}
        <section className="lab-card" data-testid="lab-recent-activity">
          <header className="lab-card__header">
            <h3 className="lab-card__title">Recent Experiment Activity</h3>
          </header>
          <ul className="lab-list">
            {activity.map((a, i) => (
              <li key={`${a.text}-${i}`} className="lab-list__item">
                <span className={`lab-list__dot lab-list__dot--${a.tone}`} />
                <span className="lab-list__title">{a.text}</span>
                <span className="lab-list__time">{a.time}</span>
              </li>
            ))}
          </ul>
        </section>

        <LabDonutChart
          title="Engine Status Summary"
          data={statusDonut}
          emptyLabel="No engines registered."
          testId="lab-status-donut"
        />

        {/* Row 3: Quick Actions | Recent Alerts */}
        <section className="lab-card" data-testid="lab-quick-actions">
          <header className="lab-card__header">
            <h3 className="lab-card__title">Quick Actions</h3>
          </header>
          <div className="lab-actions">
            <Link className="lab-action" to="/scanner">
              <span className="lab-action__icon">
                <IconFlask size={18} />
              </span>
              <span>
                <div className="lab-action__title">Run Scanner Cohort</div>
                <div className="lab-action__desc">Generate multi-symbol lab decisions</div>
              </span>
            </Link>
            <button type="button" className="lab-action" onClick={() => void load()}>
              <span className="lab-action__icon">
                <IconScale size={18} />
              </span>
              <span>
                <div className="lab-action__title">Compare Engines</div>
                <div className="lab-action__desc">Reload production vs RE-001 vs RE-002</div>
              </span>
            </button>
            <Link className="lab-action" to="/paper">
              <span className="lab-action__icon">
                <IconWallet size={18} />
              </span>
              <span>
                <div className="lab-action__title">Paper Trading</div>
                <div className="lab-action__desc">Execute from lab recommendations</div>
              </span>
            </Link>
            <Link className="lab-action" to="/performance">
              <span className="lab-action__icon">
                <IconBar size={18} />
              </span>
              <span>
                <div className="lab-action__title">Portfolio Analytics</div>
                <div className="lab-action__desc">View performance reports</div>
              </span>
            </Link>
            <button
              type="button"
              className="lab-action"
              onClick={() => {
                const blob = new Blob([JSON.stringify({ scanRunId, rows }, null, 2)], {
                  type: "application/json",
                });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `lab-comparison-${scanRunId || "export"}.json`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              <span className="lab-action__icon">
                <IconHistory size={18} />
              </span>
              <span>
                <div className="lab-action__title">Export Results</div>
                <div className="lab-action__desc">Download loaded comparison JSON</div>
              </span>
            </button>
          </div>
        </section>

        <section className="lab-card" data-testid="lab-alerts-panel">
          <header className="lab-card__header">
            <h3 className="lab-card__title">Recent Alerts</h3>
          </header>
          <ul className="lab-list">
            {alerts.map((a, i) => (
              <li key={`${a.text}-${i}`} className="lab-list__item">
                <span className={`lab-list__dot lab-list__dot--${a.tone}`} />
                <span className="lab-list__title">{a.text}</span>
                <span className="lab-list__time">{a.time}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* Experiments Overview */}
      <div className="lab-grid-main">
        <section className="lab-card" aria-label="Experiments overview">
          <header className="lab-card__header">
            <h3 className="lab-card__title">Experiments Overview</h3>
            <div className="lab-card__actions">
              <Link className="lab-btn lab-btn--primary" to="/scanner">
                + Run Scanner
              </Link>
            </div>
          </header>

          <div className="lab-table-wrap">
            <table className="lab-table">
              <thead>
                <tr>
                  <th>Experiment</th>
                  <th>Version</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Recommendations</th>
                  <th>Experiment ID</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {engines.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="lab-empty">
                      Loading engine registrations…
                    </td>
                  </tr>
                ) : (
                  engines.map((e) => (
                    <tr key={e.id}>
                      <td>
                        <strong>{e.name}</strong>
                        {e.status === "PRODUCTION" ? (
                          <>
                            {" "}
                            <LabStatusBadge status="PRODUCTION" />
                          </>
                        ) : null}
                      </td>
                      <td>{e.version}</td>
                      <td>{e.type}</td>
                      <td>
                        <LabStatusBadge status={e.status} />
                      </td>
                      <td>{e.recommendations.toLocaleString()}</td>
                      <td className="opacity-80" style={{ fontSize: "0.75rem" }}>
                        {e.experimentId || "—"}
                      </td>
                      <td>
                        <div className="lab-table-actions">
                          <button
                            type="button"
                            className="lab-icon-btn"
                            title="Load comparison for selected scan"
                            aria-label={`Focus ${e.id}`}
                            onClick={() => void load()}
                          >
                            <IconEye size={15} />
                          </button>
                          <button
                            type="button"
                            className="lab-icon-btn"
                            title="Analytics"
                            aria-label="Analytics"
                            onClick={() => {
                              const el = document.querySelector("[data-testid='lab-performance-chart']");
                              el?.scrollIntoView({ behavior: "smooth", block: "center" });
                            }}
                          >
                            <IconChart size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <p className="lab-table__footer">
            Showing {engines.length} registered lab engine{engines.length === 1 ? "" : "s"} · production
            scanner shortlists are unchanged
          </p>
        </section>
      </div>

      {/* Charts Row (50% + 50%) */}
      <div className="lab-grid-2col">
        <LabPerformanceChart data={performanceSeries} />
        <LabConfidenceBarChart data={confidenceBars} />
      </div>

      {/* Top Recommendations (Full Width 100% comparing Production, RE-001, RE-002) */}
      <section className="lab-card" data-testid="lab-top-recommendations" style={{ marginBottom: 14 }}>
        <header className="lab-card__header">
          <h3 className="lab-card__title">Top Recommendations</h3>
        </header>
        <div className="lab-table-wrap" style={{ maxHeight: 380 }}>
          <table className="lab-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Production</th>
                <th>RE-001</th>
                <th>RE-002</th>
                <th>Best Engine</th>
                <th>Best Signal</th>
                <th>Confidence</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {topRecs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="lab-empty">
                    Load a comparison to rank symbols.
                  </td>
                </tr>
              ) : (
                topRecs.map((r) => (
                  <tr key={`top-${r.symbol}-${r.re001_recommendation_id || r.re002_recommendation_id || r.symbol}`}>
                    <td className="lab-table__sym">{r.symbol}</td>
                    <td>
                      {r.production_action ? (
                        <>
                          <LabStatusBadge status={String(r.production_action)} />{" "}
                          <span style={{ color: "var(--lab-muted)", fontSize: "0.75rem" }}>
                            ({r.cProd != null ? r.cProd.toFixed(2) : "—"})
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {r.re001_state ? (
                        <>
                          <LabStatusBadge status={String(r.re001_state)} />{" "}
                          <span style={{ color: "var(--lab-muted)", fontSize: "0.75rem" }}>
                            ({r.c001 != null ? r.c001.toFixed(2) : "—"})
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {r.re002_state ? (
                        <>
                          <LabStatusBadge status={String(r.re002_state)} />{" "}
                          <span style={{ color: "var(--lab-muted)", fontSize: "0.75rem" }}>
                            ({r.c002 != null ? r.c002.toFixed(2) : "—"})
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <strong>{r.bestEngineName}</strong>
                    </td>
                    <td>
                      <LabStatusBadge status={r.bestSignal} />
                    </td>
                    <td>{confLabel(r.bestConf)}</td>
                    <td>
                      {r.finalScore != null ? r.finalScore.toFixed(0) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Footer status */}
      <footer className="lab-footer">
        <div className="lab-footer__left">
          <span className="lab-footer__item">
            <span className="lab-footer__dot" /> Production Ready Lab UI
          </span>
          <span className="lab-footer__item">
            <IconCheck size={14} /> Engine Health · RE-001 {active001 ? "OK" : "OFF"} · RE-002{" "}
            {active002 ? "OK" : "OFF"}
          </span>
          <span className="lab-footer__item">
            <IconActivity size={14} /> API · recommendation-lab
          </span>
          <span className="lab-footer__item">
            <IconBrain size={14} /> RE-001 v{registration?.engine_version || "—"} · RE-002 v
            {re002Registration?.engine_version || "—"}
          </span>
        </div>
        <span>Recommendation Lab · Multi-engine shadow research</span>
      </footer>
    </div>
  );
}
