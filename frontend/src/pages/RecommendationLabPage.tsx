import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchRe001RecentScans,
  fetchRe001Registration,
  fetchRe001ScanComparison,
  fetchRe002Health,
  fetchRe002RecentScans,
  fetchRe002Registration,
  fetchRe002ScanComparison,
} from "../api";

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
  /** Backend-computed: side effects will actually run */
  active?: boolean | null;
};

function isEngineActive(reg: Registration | null): boolean {
  if (!reg) return false;
  // Prefer backend active flag when present (RE-002 experiment gate).
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

export default function RecommendationLabPage() {
  const [scanRunId, setScanRunId] = useState("");
  const [recent, setRecent] = useState<ScanSummary[]>([]);
  const [re001Rows, setRe001Rows] = useState<Re001ComparisonRow[]>([]);
  const [re002Rows, setRe002Rows] = useState<Re002ComparisonRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [registration, setRegistration] = useState<Registration | null>(null);
  const [re002Registration, setRe002Registration] = useState<Registration | null>(null);
  const [re002Health, setRe002Health] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [reg001, reg002] = await Promise.all([
          fetchRe001Registration().catch((e) => {
            throw e;
          }),
          fetchRe002Registration().catch(() => null),
        ]);
        setRegistration(reg001);
        if (reg002) setRe002Registration(reg002);

        const inactiveNotes: string[] = [];
        if (!reg001.enabled || !isEngineActive(reg001)) {
          inactiveNotes.push(
            `RE-001 is not active (enabled=${String(reg001.enabled)}, stage=${reg001.stage}). ` +
              `Set RE001_ENABLED=true and RE001_STAGE=LAB_SHADOW to write RE-001 lab rows.`,
          );
        }
        if (reg002 && (!reg002.enabled || !isEngineActive(reg002))) {
          inactiveNotes.push(
            `RE-002 is not active (enabled=${String(reg002.enabled)}, stage=${reg002.stage}). ` +
              `Set RE002_ENABLED=true and RE002_STAGE=LAB_SHADOW to write RE-002 lab rows.`,
          );
        }
        if (inactiveNotes.length) setInfo(inactiveNotes.join(" "));
      } catch (e) {
        setError(
          e instanceof Error
            ? `Cannot load lab registration: ${e.message}`
            : "Cannot load lab registration (backend down or permission denied).",
        );
      }

      try {
        void fetchRe002Health(7)
          .then((h) => setRe002Health(h))
          .catch(() => setRe002Health(null));
      } catch {
        setRe002Health(null);
      }

      try {
        // Multi-engine recent scans: union RE-001 + RE-002 cohorts (dedupe by scan_run_id).
        const [data001, data002] = await Promise.all([
          fetchRe001RecentScans(20, { minDecisions: 1, preferCohorts: true }).catch(
            () => ({ items: [] as ScanSummary[] }),
          ),
          fetchRe002RecentScans(20, { minDecisions: 1, preferCohorts: true }).catch(
            () => ({ items: [] as ScanSummary[] }),
          ),
        ]);
        const byId = new Map<string, ScanSummary>();
        for (const s of [...(data001.items || []), ...(data002.items || [])]) {
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
        const best =
          items.find((s) => (s.decision_count || 0) > 1) || items[0] || null;
        if (best?.scan_run_id) {
          setScanRunId((prev) => prev || best.scan_run_id);
          if ((best.decision_count || 0) <= 1) {
            setInfo(
              "Latest lab entries are single-symbol analyses (1 row each). " +
                "Select a scan with many decisions (e.g. 20) from the dropdown — that is a real Scanner shortlist. " +
                "Or run a new full Scanner to create a multi-symbol cohort.",
            );
          } else {
            setInfo(
              `Auto-selected cohort ${best.scan_run_id} with ${best.decision_count} lab decisions. Click Load comparison.`,
            );
          }
        } else {
          setInfo((prev) =>
            prev ||
            "No lab scans yet. Run a NEW Scanner after RE-001/RE-002 is active. Old production scans are not listed here.",
          );
        }
      } catch (e) {
        setError(
          e instanceof Error
            ? `Cannot load recent lab scans: ${e.message}`
            : "Cannot load recent lab scans.",
        );
      }
    })();
  }, []);

  const load = useCallback(async () => {
    if (!scanRunId.trim()) {
      setError("Enter or select a scan_run_id");
      return;
    }
    setLoading(true);
    setError(null);
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

  return (
    <div className="p-4 max-w-6xl mx-auto" data-testid="recommendation-lab-page">
      <h1 className="text-xl font-semibold mb-2">Recommendation Lab · Multi-engine</h1>
      <p className="text-sm opacity-70 mb-2">
        Experimental comparison of production vs RE-001 vs RE-002. Production scanner shortlists are unchanged.
      </p>

      {registration ? (
        <p
          className={`text-sm mb-1 ${active001 ? "text-green-700" : "text-amber-700"}`}
          data-testid="lab-registration-status"
        >
          RE-001: {registration.engine_id} · v{registration.engine_version} · enabled=
          {String(registration.enabled)} · stage={registration.stage} ·{" "}
          {active001 ? "ACTIVE" : "INACTIVE"}
        </p>
      ) : (
        <p className="text-sm mb-1 opacity-60">Loading RE-001 registration…</p>
      )}

      {re002Registration ? (
        <p
          className={`text-sm mb-4 ${active002 ? "text-green-700" : "text-amber-700"}`}
          data-testid="lab-re002-registration-status"
        >
          Lab · Experimental · RE-002: {re002Registration.engine_id} · v
          {re002Registration.engine_version} · enabled={String(re002Registration.enabled)} · stage=
          {re002Registration.stage}
          {re002Registration.experiment_id
            ? ` · experiment=${re002Registration.experiment_id}`
            : ""}{" "}
          · {active002 ? "ACTIVE" : "INACTIVE"}
        </p>
      ) : (
        <p className="text-sm mb-4 opacity-60">RE-002 registration unavailable (or UI gated).</p>
      )}

      {re002Health ? (
        <p className="text-xs opacity-70 mb-3" data-testid="lab-re002-health">
          RE-002 health (7d): BUY={String(re002Health.buy_count ?? 0)} · WATCH=
          {String(re002Health.watch_count ?? 0)} · REJECT={String(re002Health.reject_count ?? 0)} ·
          total={String(re002Health.total ?? 0)}
          {re002Health.avg_rs_of_buys != null
            ? ` · avg RS of BUYs=${String(re002Health.avg_rs_of_buys)}`
            : ""}
        </p>
      ) : null}

      <div className="flex gap-2 mb-4 flex-wrap items-center">
        <select
          className="border rounded px-2 py-1 min-w-[280px]"
          value={scanRunId}
          onChange={(e) => setScanRunId(e.target.value)}
          data-testid="lab-scan-run-select"
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
          className="border rounded px-2 py-1 min-w-[240px]"
          placeholder="or paste scan_run_id"
          value={scanRunId}
          onChange={(e) => setScanRunId(e.target.value)}
          data-testid="lab-scan-run-id"
        />
        <button type="button" className="ds-button" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Load comparison"}
        </button>
      </div>
      {error ? (
        <p className="text-sm text-red-600 mb-2" role="alert">
          {error}
        </p>
      ) : null}
      {info ? (
        <p className="text-sm text-amber-700 mb-2" role="status">
          {info}
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left border-b">
              <th className="py-2 pr-2">Symbol</th>
              <th className="py-2 pr-2">Production</th>
              <th className="py-2 pr-2">RE-001</th>
              <th className="py-2 pr-2">RE-002</th>
              <th className="py-2 pr-2">RE-002 strategy</th>
              <th className="py-2 pr-2">Experiment</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-4 opacity-60">
                  No lab rows for this scan.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr
                  key={`${r.symbol}-${r.re001_recommendation_id || ""}-${r.re002_recommendation_id || ""}`}
                  className="border-b border-opacity-20"
                >
                  <td className="py-2 pr-2 font-medium">{r.symbol}</td>
                  <td className="py-2 pr-2">
                    {r.production_action ?? "—"}
                    {r.production_score != null ? ` (${r.production_score.toFixed(1)})` : ""}
                  </td>
                  <td className="py-2 pr-2">
                    {r.re001_state
                      ? `${r.re001_state} (${r.re001_confidence?.toFixed?.(2) ?? r.re001_confidence ?? "—"})`
                      : "—"}
                  </td>
                  <td className="py-2 pr-2">
                    {r.re002_state
                      ? `${r.re002_state} (${r.re002_confidence?.toFixed?.(2) ?? r.re002_confidence ?? "—"})`
                      : "—"}
                  </td>
                  <td className="py-2 pr-2">{r.re002_strategy || "—"}</td>
                  <td className="py-2 pr-2 text-xs opacity-80">
                    {r.re002_experiment_id || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
