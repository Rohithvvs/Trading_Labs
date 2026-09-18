type BoardRow = {
  rank: number;
  symbol: string;
  signal: string;
  return: number | null;
  trades: number;
  win_rate: number | null;
  max_dd: number | null;
  profit_factor: number | null;
  profit_factor_infinite?: boolean;
};

function Board({ title, rows, period }: { title: string; rows: BoardRow[]; period?: string }) {
  return (
    <section className="panel">
      <h3 className="ds-title">{title}</h3>
      {period ? <p className="muted-copy">Period {period} · last 1 year of completed sessions</p> : null}
      <table className="data-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Symbol</th>
            <th>Signal</th>
            <th>Return</th>
            <th>Trades</th>
            <th>Win rate</th>
            <th>Max DD</th>
            <th>PF</th>
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((r) => (
              <tr key={r.symbol}>
                <td>{r.rank}</td>
                <td>{r.symbol}</td>
                <td>{r.signal}</td>
                <td>{r.return != null ? `${(r.return * 100).toFixed(1)}%` : "—"}</td>
                <td>{r.trades}</td>
                <td>{r.win_rate != null ? `${(r.win_rate * 100).toFixed(0)}%` : "—"}</td>
                <td>{r.max_dd != null ? `${(r.max_dd * 100).toFixed(1)}%` : "—"}</td>
                <td>{r.profit_factor_infinite ? "∞" : r.profit_factor != null ? r.profit_factor.toFixed(2) : "—"}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={8}>No completed 1-year book trades to rank.</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="muted-copy">Ranked by real Long-Term Buy & Hold Momentum book trades only. Never-selected names are omitted.</p>
    </section>
  );
}

export function LtmReturnBoards({ payload }: { payload: Record<string, any> | null }) {
  if (!payload?.recommendations_final) return null;
  const period =
    payload.top5_positive?.[0]?.window_start
      ? undefined
      : payload.evaluation_date
        ? `ending ${payload.evaluation_date}`
        : undefined;
  return (
    <div data-testid="ltm-return-boards">
      <Board title="Top 5 positive backtest returns" rows={payload.top5_positive || []} period={period} />
      <Board title="Least 5 backtest returns" rows={payload.least5 || []} period={period} />
    </div>
  );
}
