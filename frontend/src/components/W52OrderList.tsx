type Order = {
  side: string;
  symbol: string;
  shares?: number;
  reason?: string;
  close?: number;
  tsl?: number;
  tsl0?: number;
};

export function W52OrderList({ orders }: { orders?: Order[] }) {
  if (!orders?.length) return null;
  const exits = orders.filter((o) => o.side === "EXIT");
  const buys = orders.filter((o) => o.side === "BUY");
  const sorted = [...exits, ...buys];
  return (
    <section className="panel" data-testid="w52-order-list">
      <h3 className="ds-title">Today&apos;s orders</h3>
      <p className="muted-copy">Trailing-stop exits first, then ranked new entries.</p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Side</th>
            <th>Symbol</th>
            <th>Reason</th>
            <th>Close</th>
            <th>Stop</th>
            <th>Shares</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((o) => (
            <tr key={`${o.side}-${o.symbol}`}>
              <td>{o.side}</td>
              <td>{o.symbol}</td>
              <td>{o.reason || "—"}</td>
              <td>{o.close ?? "—"}</td>
              <td>{o.tsl ?? o.tsl0 ?? "—"}</td>
              <td>{o.shares ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
