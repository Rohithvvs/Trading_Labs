type Props = {
  payload: Record<string, any> | null;
};

export function W52ScanSummary({ payload }: Props) {
  if (!payload) return null;
  const s = payload.summary || {};
  const warmup = Boolean(payload.warmup) || payload.book_status === "WARMUP";
  const status = payload.book_status || "—";
  const emptyBuys = (s.buy ?? 0) === 0 && payload.recommendations_final;

  return (
    <section className="panel" data-testid="w52-scan-summary">
      <div className="subpanel-header">
        <h2 className="ds-title">52-Week High Breakout</h2>
        <span className="helper-chip">{status}</span>
        {payload.market_ok === false ? <span className="helper-chip">Market filter off</span> : null}
        {payload.survivorship_biased ? <span className="helper-chip">Survivorship-biased</span> : null}
        {payload.data_source ? <span className="helper-chip">Data: {payload.data_source}</span> : null}
        {payload.evaluation_date ? (
          <span className="helper-chip">
            Bar: {payload.evaluation_date}
            {payload.evaluation_bar === "live_session"
              ? " (live 1D bar, TradingView Pine)"
              : payload.evaluation_bar === "completed_history"
                ? " (last completed session, filled)"
                : " (last completed session)"}
          </span>
        ) : null}
      </div>
      {warmup ? (
        <p className="muted-copy">STATUS=WARMUP — no BUY entries until 252 sessions of history exist.</p>
      ) : null}
      {payload.evaluation_bar === "live_session" ? (
        <p className="muted-copy">
          Gate passers use today&apos;s live 1D close, prior 252-session high, and volume vs SMA20 — the same
          three legs as the TradingView Pine Screener. Current holdings stay in the book as HOLD even when
          they are not a new breakout today.
        </p>
      ) : payload.recommendations_final ? (
        <p className="muted-copy">
          This run used the last completed daily bar. A TradingView 1D screener during market hours uses the
          forming candle, so the name list can differ until you re-run after quotes overlay, or after 15:30 IST.
        </p>
      ) : null}
      {status === "MARKET_OFF" ? (
        <p className="muted-copy">
          Market filter is off. Existing holdings stay open and may EXIT on the trail. The book is not flattened.
        </p>
      ) : null}
      {emptyBuys && !warmup ? (
        <div className="panel error-state" role="status">
          <strong>No BUY candidates currently satisfy the strategy rules.</strong>
          <p>
            The scan completed, but no name received a new 10% slot today
            {(s.hold ?? 0) > 0 ? ` (${s.hold} existing HOLD)` : ""}
            {(s.watch ?? 0) > 0 ? ` (${s.watch} WATCH)` : ""}.
          </p>
        </div>
      ) : null}
      <div className="status-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(7rem,1fr))", gap: 8 }}>
        {[
          ["Total", s.total],
          ["Data valid", s.data_valid],
          ["Evaluated", s.evaluated],
          ["Final candidates", s.final_candidates],
          ["Gate passers", s.screener_matches ?? (payload.screener_matches || []).length],
          ["BUY", s.buy],
          ["HOLD", s.hold],
          ["WATCH", s.watch],
          ["REJECT", s.reject],
          ["Data failures", s.data_failures],
          ["Free slots", payload.free_slots],
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
                {h.symbol} · HWM {h.hwm ?? "—"} · TSL {h.tsl ?? "—"} · unrealized{" "}
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
