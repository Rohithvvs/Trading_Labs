type Props = {
  payload: Record<string, any> | null;
};

export function LtmScanSummary({ payload }: Props) {
  if (!payload) return null;
  const s = payload.summary || {};
  const warmup = Boolean(payload.warmup);
  const clock = payload.clock_status || "—";
  const emptyBuys = (s.buy ?? 0) === 0 && (s.watch ?? 0) === 0 && payload.recommendations_final;

  return (
    <section className="panel" data-testid="ltm-scan-summary">
      <div className="subpanel-header">
        <h2 className="ds-title">Long-Term Buy & Hold Momentum</h2>
        <span className="helper-chip">{clock}</span>
        {payload.survivorship_biased ? <span className="helper-chip">Survivorship-biased</span> : null}
        {payload.data_source ? <span className="helper-chip">Data: {payload.data_source}</span> : null}
      </div>
      {warmup ? (
        <p className="muted-copy">STATUS=WARMUP — no BUY or WATCH entries until 252 sessions of history exist.</p>
      ) : null}
      {clock === "MID_CYCLE" ? (
        <p className="muted-copy">
          Mid-cycle: {payload.sessions_to_rebalance ?? "—"} sessions to next rebalance. Selected names stay WATCH
          until the next 252-session rebalance. BUY is issued only on rebalance day.
        </p>
      ) : null}
      {(s.buy ?? 0) === 0 && (s.watch ?? 0) > 0 && clock === "MID_CYCLE" ? (
        <div className="panel" role="status" data-testid="ltm-zero-buy-reason">
          <strong>No BUY candidates currently satisfy the strategy rules.</strong>
          <p className="muted-copy">
            {s.watch} name{s.watch === 1 ? "" : "s"} passed the +50% / top-10 gates and remain WATCH until
            rebalance. This is expected mid-cycle behavior, not a missing BUY filter.
          </p>
        </div>
      ) : null}
      {emptyBuys && !warmup ? (
        <div className="panel error-state" role="status">
          <strong>No Long-Term Buy & Hold Momentum BUY setups found</strong>
          <p>The scan completed, but no name passed the eligibility gates.</p>
        </div>
      ) : null}
      <div className="status-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(7rem,1fr))", gap: 8 }}>
        {[
          ["Total", s.total],
          ["Data valid", s.data_valid],
          ["Evaluated", s.evaluated],
          ["Final candidates", s.final_candidates],
          ["BUY", s.buy],
          ["WATCH", s.watch],
          ["REJECT", s.reject],
          ["Data failures", s.data_failures],
        ].map(([label, value]) => (
          <div key={String(label)} className="metric-card">
            <span className="section-label">{label}</span>
            <strong>{value ?? "—"}</strong>
          </div>
        ))}
      </div>
      {Array.isArray(payload.holdings) && payload.holdings.length ? (
        <div style={{ marginTop: 12 }}>
          <h3 className="ds-title">Current holdings</h3>
          <ul>
            {payload.holdings.map((h: any) => (
              <li key={h.symbol}>
                {h.symbol} · MTM {h.mark ?? "—"} · unrealized{" "}
                {h.unrealized_pct != null ? `${(h.unrealized_pct * 100).toFixed(1)}%` : "—"}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {Array.isArray(payload.limitations) ? (
        <details style={{ marginTop: 12 }}>
          <summary>Known limitations</summary>
          <ul>
            {payload.limitations.map((line: string) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
