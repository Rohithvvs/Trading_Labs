import type { CandidateRow } from "../types";

function fmt(n: unknown, digits = 4): string {
  if (n === null || n === undefined || n === "") return "—";
  const v = typeof n === "number" ? n : Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function fmtInt(n: unknown): string {
  if (n === null || n === undefined || n === "") return "—";
  const v = typeof n === "number" ? n : Number(n);
  if (!Number.isFinite(v)) return "—";
  return Math.round(v).toLocaleString();
}

function statusLabel(ok: unknown, pass = "PASS", fail = "FAIL"): string {
  if (ok === true) return pass;
  if (ok === false) return fail;
  return "—";
}

function statusClass(ok: unknown): string {
  if (ok === true) return "text-emerald-600";
  if (ok === false) return "text-rose-600";
  return "";
}

/** Display-only RE-002 Technicals — values come from backend technical_analysis. */
export function Re002TechnicalsWorkspace({ row }: { row: CandidateRow }) {
  // @ts-ignore - allow dynamic engine fields
  const engineData = row.analysisItem?.lab_engines?.["RE-002"];
  const tech = engineData?.technical_analysis;

  if (!tech || tech.status === "INSUFFICIENT_HISTORY" || tech.error) {
    return (
      <div className="detail-stack p-4">
        <p className="text-muted text-sm">
          {tech?.status === "INSUFFICIENT_HISTORY"
            ? `INSUFFICIENT_HISTORY: ${tech.error || "not enough aligned stock/benchmark sessions for CRS SMA21 + slope."}`
            : tech?.error
              ? `Engine technical analysis error: ${tech.error}`
              : "Engine-specific technical analysis is not available for this run."}
        </p>
        {tech?.detail && (
          <pre className="text-xs mt-2 opacity-70">{JSON.stringify(tech.detail, null, 2)}</pre>
        )}
      </div>
    );
  }

  const rs = tech.relative_strength || {};
  const vol = tech.volume || {};
  const mom = tech.momentum || {};
  const bm = tech.benchmark || {};
  const earn = tech.earnings || {};
  const risk = tech.volatility || {};
  const baseline = tech.baseline || {};
  const interp = tech.interpretation || {};

  return (
    <div className="detail-stack">
      <div className="detail-header mb-4">
        <h2>RE-002 Technicals Workspace</h2>
        <p className="detail-summary text-sm opacity-80">
          Relative Strength — values from backend RE-002 technical calculation (single source of truth)
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <section className="ds-card">
          <h3 className="ds-label mb-3">Relative Strength</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="ds-metric">
              <strong>Active Benchmark:</strong> {bm.symbol || baseline.active_benchmark || "—"}
            </div>
            <div className="ds-metric">
              <strong>Benchmark Close:</strong> {fmt(bm.close ?? baseline.benchmark_price, 2)}
            </div>
            <div className="ds-metric">
              <strong>Stock Close:</strong> {fmt(baseline.stock_price ?? risk.entry, 2)}
            </div>
            <div className="ds-metric">
              <strong>Session:</strong> {tech.session_date || baseline.session_date || "—"}
            </div>
            <div className="ds-metric">
              <strong>CRS:</strong> {fmt(rs.crs ?? baseline.crs, 6)}
            </div>
            <div className="ds-metric">
              <strong>CRS SMA21:</strong> {fmt(rs.crs_sma21 ?? baseline.crs_sma21 ?? baseline.crs_sma_21, 6)}
            </div>
            <div className="ds-metric">
              <strong>CRS 3-Period Slope:</strong>{" "}
              {fmt(rs.crs_slope_3 ?? baseline.crs_slope_3 ?? baseline.crs_3_period_slope, 6)}
            </div>
            <div className="ds-metric">
              <strong>Relative Breakout:</strong>{" "}
              <span className={statusClass(rs.relative_breakout ?? baseline.relative_breakout)}>
                {statusLabel(rs.relative_breakout ?? baseline.relative_breakout)}
              </span>
            </div>
            <div className="ds-metric col-span-2 text-xs opacity-70">
              Rule: CRS &gt; CRS SMA21
            </div>
          </div>
        </section>

        <section className="ds-card">
          <h3 className="ds-label mb-3">Stock Momentum</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="ds-metric">
              <strong>RSI14:</strong> {fmt(mom.stock_rsi14 ?? baseline.stock_rsi_14, 2)}
            </div>
            <div className="ds-metric">
              <strong>Lower Threshold:</strong> {fmt(mom.lower_threshold ?? 50, 0)}
            </div>
            <div className="ds-metric">
              <strong>Upper Threshold:</strong> {fmt(mom.upper_threshold ?? 70, 0)}
            </div>
            <div className="ds-metric">
              <strong>Condition:</strong>{" "}
              <span className={statusClass(mom.condition)}>
                {statusLabel(mom.condition)}
              </span>
            </div>
            <div className="ds-metric col-span-2 text-xs opacity-70">
              Rule: 50 ≤ RSI14 ≤ 70
            </div>
          </div>
        </section>
      </div>

      <div className="grid grid-cols-2 gap-4 mt-4">
        <section className="ds-card">
          <h3 className="ds-label mb-3">Volume</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="ds-metric">
              <strong>Current Volume:</strong> {fmtInt(vol.volume ?? baseline.volume)}
            </div>
            <div className="ds-metric">
              <strong>Volume SMA20:</strong> {fmtInt(vol.volume_sma20 ?? baseline.volume_sma20)}
            </div>
            <div className="ds-metric">
              <strong>Relative Volume:</strong>{" "}
              {fmt(vol.relative_volume ?? baseline.relative_volume, 3)}
            </div>
            <div className="ds-metric">
              <strong>Required:</strong> ≥ {fmt(vol.threshold ?? 1.2, 1)}x
            </div>
            <div className="ds-metric">
              <strong>Status:</strong>{" "}
              <span className={statusClass(vol.condition)}>
                {statusLabel(vol.condition)}
              </span>
            </div>
          </div>
        </section>

        <section className="ds-card">
          <h3 className="ds-label mb-3">Benchmark Health</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="ds-metric">
              <strong>Benchmark:</strong> {bm.symbol || baseline.active_benchmark || "NIFTY500"}
            </div>
            <div className="ds-metric">
              <strong>Benchmark RSI14:</strong> {fmt(bm.rsi14 ?? baseline.benchmark_rsi_14, 2)}
            </div>
            <div className="ds-metric">
              <strong>Threshold:</strong> ≥ {fmt(bm.rsi_threshold ?? 40, 0)}
            </div>
            <div className="ds-metric">
              <strong>Health Status:</strong>{" "}
              <span className={statusClass(bm.rsi_condition)}>
                {bm.health_status || statusLabel(bm.rsi_condition, "NORMAL", "FAIL")}
              </span>
            </div>
          </div>
        </section>
      </div>

      <div className="grid grid-cols-2 gap-4 mt-4">
        <section className="ds-card">
          <h3 className="ds-label mb-3">Earnings</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="ds-metric">
              <strong>Next Earnings:</strong>{" "}
              {earn.next_earnings_date || baseline.next_earnings_date || "—"}
            </div>
            <div className="ds-metric">
              <strong>Trading Sessions Until:</strong>{" "}
              {earn.trading_sessions_until != null ||
              baseline.trading_sessions_until_earnings != null
                ? String(earn.trading_sessions_until ?? baseline.trading_sessions_until_earnings)
                : "—"}
            </div>
            <div className="ds-metric">
              <strong>Required Min Distance:</strong> {fmt(earn.threshold ?? 7, 0)} sessions
            </div>
            <div className="ds-metric">
              <strong>Status:</strong>{" "}
              <span className={statusClass(earn.condition ?? baseline.earnings_condition)}>
                {statusLabel(earn.condition ?? baseline.earnings_condition)}
              </span>
            </div>
          </div>
        </section>

        <section className="ds-card">
          <h3 className="ds-label mb-3">Volatility / Risk Levels</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="ds-metric">
              <strong>ATR14:</strong> {fmt(risk.atr14 ?? baseline.atr_14, 2)}
            </div>
            <div className="ds-metric">
              <strong>ATR Multiplier:</strong> {fmt(risk.atr_multiplier ?? baseline.atr_multiplier ?? 2, 1)}
            </div>
            <div className="ds-metric">
              <strong>Entry (close):</strong> {fmt(risk.entry ?? baseline.stock_price, 2)}
            </div>
            <div className="ds-metric">
              <strong>ATR Stop:</strong> {fmt(risk.atr_stop ?? baseline.atr_stop, 2)}
            </div>
            <div className="ds-metric col-span-2 text-xs opacity-70">
              Rule: Entry − (2.0 × ATR14)
            </div>
          </div>
        </section>
      </div>

      {interp.status && (
        <section className="ds-card mt-4">
          <h3 className="ds-label mb-3">Condition Summary (backend)</h3>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div>
              Breakout:{" "}
              <span className={statusClass(interp.relative_breakout === "PASS")}>
                {interp.relative_breakout || "—"}
              </span>
            </div>
            <div>
              CRS Slope:{" "}
              <span className={statusClass(interp.crs_slope === "PASS")}>
                {interp.crs_slope || "—"}
              </span>
            </div>
            <div>
              Stock RSI:{" "}
              <span className={statusClass(interp.stock_rsi === "PASS")}>
                {interp.stock_rsi || "—"}
              </span>
            </div>
            <div>
              RVOL:{" "}
              <span className={statusClass(interp.relative_volume === "PASS")}>
                {interp.relative_volume || "—"}
              </span>
            </div>
            <div>
              Benchmark:{" "}
              <span className={statusClass(interp.benchmark_health === "NORMAL")}>
                {interp.benchmark_health || "—"}
              </span>
            </div>
            <div>
              Earnings:{" "}
              <span className={statusClass(interp.earnings === "PASS")}>
                {interp.earnings || "—"}
              </span>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
