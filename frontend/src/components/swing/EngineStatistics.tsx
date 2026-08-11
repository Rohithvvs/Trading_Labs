import { memo, useCallback, useEffect, useRef, useState } from "react";
import { fetchScannerStatistics } from "../../api";
import { Card, CardHeader, Button } from "../../design-system";
import { MetricCardSkeleton } from "../Skeleton";
import { StatCard } from "../../design-system/components/StatCard";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EngineStatus = "not_executed" | "executed" | "error";

interface EngineStats {
  status: EngineStatus;
  engine_id: string;
  engine_name?: string;
  scan_run_id?: string | null;
  scanned_at?: string | null;
  message?: string;
  total_candidates?: number;
  data_valid?: number;
  eligibility_matched?: number;
  relative_strength_matched?: number;
  technical_analysis_completed?: number;
  buy_ideas?: number;
  watch_ideas?: number;
  rejected?: number;
  high_confidence?: number;
  average_score?: number | null;
  highest_score?: number | null;
  average_confidence?: number | null;
  average_risk_reward?: number | null;
  gating_pass_rate?: number | null;
  technical_analysis_success_rate?: number | null;
}

interface ScannerStatisticsResponse {
  production: Record<string, unknown>;
  engines: {
    "RE-001": EngineStats;
    "RE-002": EngineStats;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(v: number | null | undefined, digits = 0): string {
  if (v == null) return "\u2014";
  return Number(v).toFixed(digits);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "\u2014";
  return `${Number(v).toFixed(1)}%`;
}

function fmtConf(v: number | null | undefined): string {
  if (v == null) return "\u2014";
  const val = v > 1 ? v : v * 100;
  return `${val.toFixed(0)}%`;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Engine accent colors (use CSS vars with fallback)
// ---------------------------------------------------------------------------

const RE001_COLOR = "var(--color-accent, #6366f1)";
const RE002_COLOR = "var(--color-teal, #14b8a6)";

// ---------------------------------------------------------------------------
// Single engine card
// ---------------------------------------------------------------------------

interface EngineCardProps {
  stats: EngineStats;
  engineLabel: string;
  accentColor: string;
}

const EngineCard = memo(function EngineCard({ stats, engineLabel, accentColor }: EngineCardProps) {
  const isRE002 = stats.engine_id === "RE-002";

  if (stats.status === "not_executed") {
    return (
      <div
        className="engine-stats-card engine-stats-card--not-executed"
        data-testid={`engine-card-${stats.engine_id}`}
      >
        <div className="engine-stats-card__header">
          <span className="engine-stats-card__badge" style={{ borderColor: accentColor, color: accentColor }}>
            {stats.engine_id}
          </span>
          <div>
            <h3 className="ds-title engine-stats-card__title">{engineLabel}</h3>
            <span className="ds-caption engine-stats-card__status engine-stats-card__status--not-executed">
              Not Executed
            </span>
          </div>
        </div>
        <p className="ds-muted" style={{ margin: "8px 0 0", fontSize: "0.85rem" }}>
          {stats.engine_id} has not been executed for the current scan. Run a scan that includes this engine to see statistics.
        </p>
      </div>
    );
  }

  if (stats.status === "error") {
    return (
      <div
        className="engine-stats-card engine-stats-card--error"
        data-testid={`engine-card-${stats.engine_id}`}
      >
        <div className="engine-stats-card__header">
          <span className="engine-stats-card__badge" style={{ borderColor: accentColor, color: accentColor }}>
            {stats.engine_id}
          </span>
          <h3 className="ds-title engine-stats-card__title">{engineLabel}</h3>
        </div>
        <p className="ds-muted" style={{ margin: "8px 0 0", fontSize: "0.85rem" }}>
          Could not load statistics for {stats.engine_id}.
        </p>
      </div>
    );
  }

  // status === "executed"
  const eligibilityCount = isRE002 ? stats.relative_strength_matched : stats.eligibility_matched;
  const eligibilityLabel = isRE002 ? "RS Matched" : "Trend Matched";
  const scannedAt = fmtDate(stats.scanned_at);

  return (
    <div className="engine-stats-card" data-testid={`engine-card-${stats.engine_id}`}>
      {/* Header row */}
      <div className="engine-stats-card__header">
        <span
          className="engine-stats-card__badge"
          style={{ borderColor: accentColor, color: accentColor, background: `color-mix(in srgb, ${accentColor} 12%, transparent)` }}
        >
          {stats.engine_id}
        </span>
        <div>
          <h3 className="ds-title engine-stats-card__title">{engineLabel}</h3>
          {scannedAt && (
            <span className="ds-caption engine-stats-card__meta">Last run: {scannedAt}</span>
          )}
        </div>
        <span className="engine-stats-card__status engine-stats-card__status--executed ds-caption">
          Executed
        </span>
      </div>

      {/* Row 1: Funnel counts */}
      <div className="engine-stats-grid">
        <StatCard label="Engine Evaluated" value={stats.total_candidates ?? "\u2014"} subtitle="Independent universe (not Production top-N)" compact />
        <StatCard label="Data Valid" value={stats.data_valid ?? "\u2014"} subtitle="Sufficient OHLCV / TA" compact />
        <StatCard label={eligibilityLabel} value={eligibilityCount ?? "\u2014"} subtitle={isRE002 ? "Passed RS filter" : "Passed trend filter"} tone="positive" compact />
        <StatCard label="TA Completed" value={stats.technical_analysis_completed ?? "\u2014"} subtitle="Full technicals done" compact />
      </div>

      {/* Row 2: Decision counts */}
      <div className="engine-stats-grid">
        <StatCard label="BUY Ideas" value={stats.buy_ideas ?? "\u2014"} subtitle="Actionable signals" tone="positive" compact />
        <StatCard label="WATCH Ideas" value={stats.watch_ideas ?? "\u2014"} subtitle="Needs confirmation" tone="warning" compact />
        <StatCard label="Rejected" value={stats.rejected ?? "\u2014"} subtitle="Failed engine filters" tone="negative" compact />
        <StatCard label="High Confidence" value={stats.high_confidence ?? "\u2014"} subtitle="\u226570% confidence" tone="positive" compact />
      </div>

      {/* Row 3: Score / confidence / RR */}
      <div className="engine-stats-grid">
        <StatCard label="Avg Score" value={fmt(stats.average_score, 1)} subtitle="Composite engine score" compact />
        <StatCard label="Highest Score" value={fmt(stats.highest_score, 1)} subtitle="Best in this scan" tone="positive" compact />
        <StatCard label="Avg Confidence" value={fmtConf(stats.average_confidence)} subtitle="Mean confidence" compact />
        <StatCard label="Avg Risk/Reward" value={fmt(stats.average_risk_reward, 2)} subtitle="Where available" compact />
      </div>

      {/* Row 4: Pass rates */}
      <div className="engine-stats-grid engine-stats-grid--2col">
        <StatCard
          label="Gating Pass Rate"
          value={fmtPct(stats.gating_pass_rate)}
          subtitle="Passed required gates"
          tone={stats.gating_pass_rate != null ? (stats.gating_pass_rate >= 50 ? "positive" : "warning") : "default"}
          compact
        />
        <StatCard
          label="TA Success Rate"
          value={fmtPct(stats.technical_analysis_success_rate)}
          subtitle="Full TA generated"
          tone={stats.technical_analysis_success_rate != null ? (stats.technical_analysis_success_rate >= 50 ? "positive" : "warning") : "default"}
          compact
        />
      </div>
    </div>
  );
});

// ---------------------------------------------------------------------------
// Comparison table
// ---------------------------------------------------------------------------

const ComparisonTable = memo(function ComparisonTable({
  re001,
  re002,
}: {
  re001: EngineStats;
  re002: EngineStats;
}) {
  if (re001.status !== "executed" && re002.status !== "executed") return null;

  const rows: Array<{ label: string; re001val: string; re002val: string }> = [
    { label: "Candidates", re001val: fmt(re001.total_candidates), re002val: fmt(re002.total_candidates) },
    { label: "Data Valid", re001val: fmt(re001.data_valid), re002val: fmt(re002.data_valid) },
    { label: "BUY", re001val: fmt(re001.buy_ideas), re002val: fmt(re002.buy_ideas) },
    { label: "WATCH", re001val: fmt(re001.watch_ideas), re002val: fmt(re002.watch_ideas) },
    { label: "Reject", re001val: fmt(re001.rejected), re002val: fmt(re002.rejected) },
    { label: "Avg Score", re001val: fmt(re001.average_score, 1), re002val: fmt(re002.average_score, 1) },
    { label: "Avg Confidence", re001val: fmtConf(re001.average_confidence), re002val: fmtConf(re002.average_confidence) },
    { label: "Avg Risk/Reward", re001val: fmt(re001.average_risk_reward, 2), re002val: fmt(re002.average_risk_reward, 2) },
    { label: "Gating Pass Rate", re001val: fmtPct(re001.gating_pass_rate), re002val: fmtPct(re002.gating_pass_rate) },
    { label: "TA Success Rate", re001val: fmtPct(re001.technical_analysis_success_rate), re002val: fmtPct(re002.technical_analysis_success_rate) },
  ];

  return (
    <div className="engine-comparison" data-testid="engine-comparison-table">
      <h4 className="ds-label engine-comparison__title">Engine Comparison</h4>
      <div className="engine-comparison__table-wrap">
        <table className="engine-comparison__table">
          <thead>
            <tr>
              <th>Metric</th>
              <th style={{ color: RE001_COLOR }}>RE-001</th>
              <th style={{ color: RE002_COLOR }}>RE-002</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <td className="ds-caption">{row.label}</td>
                <td>{re001.status === "executed" ? row.re001val : "\u2014"}</td>
                <td>{re002.status === "executed" ? row.re002val : "\u2014"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});

// ---------------------------------------------------------------------------
// Main exported component
// ---------------------------------------------------------------------------

export type EngineStatisticsProps = Record<string, never>;

/**
 * Engine-specific scanner statistics for RE-001 and RE-002.
 *
 * - Renders BELOW the production ScannerStatistics section (never replaces it).
 * - One consolidated API request: GET /scanner/statistics.
 * - Skeleton cards while loading; independent error/retry — never breaks production stats.
 * - "Not Executed" vs "Executed with 0 results" are clearly distinguished.
 */
export const EngineStatistics = memo(function EngineStatistics(_props: EngineStatisticsProps) {
  const [data, setData] = useState<ScannerStatisticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchScannerStatistics();
      if (!mounted.current) return;
      // API returns the consolidated production + engines payload; cast to UI shape.
      setData(result as ScannerStatisticsResponse);
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err.message : "Unable to load engine statistics.");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  return (
    <Card className="engine-statistics" aria-label="Engine statistics" data-testid="engine-statistics">
      <CardHeader
        label="Engine Statistics"
        title="Engine-specific scanner performance"
        description="RE-001 and RE-002 run independently on the validated universe (not Production top-N). Counts come from each engine's own decisions."
        actions={
          <Button variant="ghost" size="sm" onClick={() => void load()} disabled={loading}>
            {loading ? "Loading\u2026" : "Refresh"}
          </Button>
        }
      />

      {loading && !data ? (
        <div className="engine-statistics__loading">
          <MetricCardSkeleton count={8} />
          <MetricCardSkeleton count={8} />
        </div>
      ) : error ? (
        <div className="engine-statistics__error" role="alert" data-testid="engine-statistics-error">
          <p className="ds-muted">{error}</p>
          <Button variant="secondary" size="sm" onClick={() => void load()} style={{ marginTop: 8 }}>
            Retry
          </Button>
        </div>
      ) : data ? (
        <div className="engine-statistics__content">
          <EngineCard
            stats={data.engines["RE-001"]}
            engineLabel="Trend Continuation Engine"
            accentColor={RE001_COLOR}
          />
          <div className="engine-statistics__divider" role="separator" />
          <EngineCard
            stats={data.engines["RE-002"]}
            engineLabel="Relative Strength Engine"
            accentColor={RE002_COLOR}
          />
          <div className="engine-statistics__divider" role="separator" />
          <ComparisonTable re001={data.engines["RE-001"]} re002={data.engines["RE-002"]} />
        </div>
      ) : null}
    </Card>
  );
});
