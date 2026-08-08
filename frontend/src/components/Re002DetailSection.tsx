import { useEffect, useState, type ReactNode } from "react";
import { fetchRe002SymbolLatest } from "../api";

export type Re002DecisionSummary = {
  recommendation_id?: string;
  engine_id?: string;
  engine_version?: string;
  experiment_id?: string | null;
  recommendation_state?: string;
  confidence_score?: number;
  strategy_name?: string | null;
  strategy_family?: string | null;
  explanation?: string | null;
  production_action?: string | null;
  reason_codes?: string[] | null;
  market_regime?: string | null;
  evidence?: Record<string, unknown> | null;
};

type Props = {
  decision?: Re002DecisionSummary | null;
  symbol?: string | null;
  emptyMessage?: string;
};

function mapLatestToSummary(raw: Record<string, unknown>): Re002DecisionSummary {
  return {
    recommendation_id: raw.recommendation_id != null ? String(raw.recommendation_id) : undefined,
    engine_id: raw.engine_id != null ? String(raw.engine_id) : "RE-002",
    engine_version: raw.engine_version != null ? String(raw.engine_version) : undefined,
    experiment_id: (raw.experiment_id as string | null | undefined) ?? null,
    recommendation_state:
      raw.recommendation_state != null ? String(raw.recommendation_state) : undefined,
    confidence_score:
      typeof raw.confidence_score === "number"
        ? raw.confidence_score
        : raw.confidence_score != null
          ? Number(raw.confidence_score)
          : undefined,
    strategy_name: (raw.strategy_name as string | null | undefined) ?? null,
    strategy_family: (raw.strategy_family as string | null | undefined) ?? null,
    explanation: (raw.explanation as string | null | undefined) ?? null,
    production_action: (raw.production_action as string | null | undefined) ?? null,
    reason_codes: Array.isArray(raw.reason_codes) ? (raw.reason_codes as string[]) : null,
    market_regime: (raw.market_regime as string | null | undefined) ?? null,
    evidence: (raw.evidence as Record<string, unknown> | null | undefined) ?? null,
  };
}

export function Re002DetailSection({
  decision,
  symbol,
  emptyMessage = "No RE-002 lab decision for this symbol.",
}: Props): ReactNode {
  const [fetched, setFetched] = useState<Re002DecisionSummary | null>(null);
  const [fetchAttempted, setFetchAttempted] = useState(false);

  useEffect(() => {
    if (decision) {
      setFetched(null);
      setFetchAttempted(false);
      return;
    }
    const sym = (symbol || "").trim();
    if (!sym) {
      setFetched(null);
      setFetchAttempted(true);
      return;
    }

    let mounted = true;
    setFetchAttempted(false);
    void fetchRe002SymbolLatest(sym)
      .then((raw) => {
        if (!mounted) return;
        setFetched(mapLatestToSummary(raw));
        setFetchAttempted(true);
      })
      .catch(() => {
        if (!mounted) return;
        setFetched(null);
        setFetchAttempted(true);
      });
    return () => {
      mounted = false;
    };
  }, [decision, symbol]);

  const resolved = decision ?? fetched;

  if (!resolved) {
    if (!decision && symbol && !fetchAttempted) {
      return (
        <section className="ds-card" data-testid="re002-detail-loading" aria-label="RE-002 lab decision">
          <p className="ds-label">Lab · Experimental · RE-002</p>
          <p className="text-sm opacity-70">Checking RS leadership decision…</p>
        </section>
      );
    }
    return (
      <section className="ds-card" data-testid="re002-detail-empty" aria-label="RE-002 lab decision">
        <p className="ds-label">Lab · Experimental · RE-002</p>
        <p className="text-sm opacity-70">{emptyMessage}</p>
      </section>
    );
  }

  const state = String(resolved.recommendation_state || "—").toUpperCase();
  const rs = resolved.evidence?.rs as Record<string, unknown> | undefined;
  const rsSummary =
    rs?.sector_rs_20 != null
      ? `RS20=${String(rs.sector_rs_20)}`
      : rs?.rs_vs_market != null
        ? `RS≈${String(rs.rs_vs_market)}`
        : null;

  return (
    <section className="ds-card" data-testid="re002-detail" aria-label="RE-002 lab decision">
      <p className="ds-label">Lab · Experimental · RE-002 · Relative Strength Momentum</p>
      <div className="flex flex-wrap gap-3 text-sm mt-2">
        <span>
          <strong>State:</strong> {state}
        </span>
        <span>
          <strong>Confidence:</strong>{" "}
          {resolved.confidence_score != null ? Number(resolved.confidence_score).toFixed(2) : "—"}
        </span>
        <span>
          <strong>Strategy:</strong> {resolved.strategy_name || "—"}
        </span>
        <span>
          <strong>Regime:</strong> {resolved.market_regime || "—"}
        </span>
        {rsSummary ? (
          <span>
            <strong>RS:</strong> {rsSummary}
          </span>
        ) : null}
        <span>
          <strong>vs Production:</strong> {resolved.production_action || "—"}
        </span>
      </div>
      {resolved.reason_codes && resolved.reason_codes.length > 0 ? (
        <p className="text-sm mt-2">
          <strong>Reasons:</strong> {resolved.reason_codes.join(", ")}
        </p>
      ) : null}
      {resolved.explanation ? (
        <p className="text-sm mt-2 opacity-80">{String(resolved.explanation)}</p>
      ) : null}
      {resolved.experiment_id ? (
        <p className="text-xs mt-2 opacity-60">Experiment: {resolved.experiment_id}</p>
      ) : null}
      <p className="text-xs mt-1 opacity-50">
        Engine {resolved.engine_id} v{resolved.engine_version || "?"} · not production advice
      </p>
    </section>
  );
}
