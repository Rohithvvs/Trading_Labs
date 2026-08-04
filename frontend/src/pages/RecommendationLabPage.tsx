import { useCallback, useEffect, useState } from "react";
import {
  fetchRe001RecentScans,
  fetchRe001Registration,
  fetchRe001ScanComparison,
} from "../api";

type ComparisonRow = {
  symbol: string;
  recommendation_id: string;
  production_action?: string | null;
  production_score?: number | null;
  re001_state: string;
  confidence_score: number;
  strategy_name?: string | null;
  is_mismatch?: boolean | null;
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
};

function isEngineActive(reg: Registration | null): boolean {
  if (!reg?.enabled) return false;
  const stage = String(reg.stage || "OFF").toUpperCase();
  return stage === "LAB_SHADOW" || stage === "PAPER_LINKED";
}

export default function RecommendationLabPage() {
  const [scanRunId, setScanRunId] = useState("");
  const [recent, setRecent] = useState<ScanSummary[]>([]);
  const [rows, setRows] = useState<ComparisonRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [registration, setRegistration] = useState<Registration | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const reg = await fetchRe001Registration();
        setRegistration(reg);
        if (!reg.enabled || !isEngineActive(reg)) {
          setInfo(
            `RE-001 is not active (enabled=${String(reg.enabled)}, stage=${reg.stage}). ` +
              `Set RE001_ENABLED=true and RE001_STAGE=LAB_SHADOW, then restart the backend and run a new Scanner scan.`,
          );
        }
      } catch (e) {
        setError(
          e instanceof Error
            ? `Cannot load RE-001 registration: ${e.message}`
            : "Cannot load RE-001 registration (backend down or permission denied).",
        );
      }

      try {
        // Prefer multi-symbol screener cohorts (decision_count first).
        // Single-symbol stock-detail re-analyses create many 1-row full-* scan ids.
        const data = await fetchRe001RecentScans(20, {
          minDecisions: 1,
          preferCohorts: true,
        });
        const items = data.items || [];
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
              `Auto-selected cohort ${best.scan_run_id} with ${best.decision_count} RE-001 decisions. Click Load comparison.`,
            );
          }
        } else {
          setInfo((prev) =>
            prev ||
            "No RE-001 lab scans yet. Run a NEW Scanner (full screener) after RE-001 is active — old production scans are not listed here.",
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
    try {
      const data = await fetchRe001ScanComparison(scanRunId.trim());
      setRows(data.items || []);
      if (!(data.items || []).length) {
        setInfo(
          "This scan_run_id has no RE-001 decision rows. It must come from a scan that ran while RE-001 was active.",
        );
      } else {
        setInfo(null);
      }
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : "Failed to load lab comparison");
    } finally {
      setLoading(false);
    }
  }, [scanRunId]);

  const active = isEngineActive(registration);

  return (
    <div className="p-4 max-w-5xl mx-auto" data-testid="recommendation-lab-page">
      <h1 className="text-xl font-semibold mb-2">Recommendation Lab · RE-001</h1>
      <p className="text-sm opacity-70 mb-2">
        Experimental comparison of production vs RE-001. Production scanner shortlists are unchanged.
      </p>

      {registration ? (
        <p
          className={`text-sm mb-4 ${active ? "text-green-700" : "text-amber-700"}`}
          data-testid="lab-registration-status"
        >
          Engine: {registration.engine_id} · v{registration.engine_version} · enabled=
          {String(registration.enabled)} · stage={registration.stage} ·{" "}
          {active ? "ACTIVE (will write lab rows on next scan)" : "INACTIVE (will not write lab rows)"}
        </p>
      ) : (
        <p className="text-sm mb-4 opacity-60">Loading engine registration…</p>
      )}

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
              <th className="py-2 pr-2">Strategy</th>
              <th className="py-2 pr-2">Mismatch</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-4 opacity-60">
                  No lab rows for this scan.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.recommendation_id} className="border-b border-opacity-20">
                  <td className="py-2 pr-2 font-medium">{r.symbol}</td>
                  <td className="py-2 pr-2">
                    {r.production_action ?? "—"}
                    {r.production_score != null ? ` (${r.production_score.toFixed(1)})` : ""}
                  </td>
                  <td className="py-2 pr-2">
                    {r.re001_state} ({r.confidence_score?.toFixed?.(2) ?? r.confidence_score})
                  </td>
                  <td className="py-2 pr-2">{r.strategy_name || "—"}</td>
                  <td className="py-2 pr-2">{r.is_mismatch ? "Yes" : "No"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
