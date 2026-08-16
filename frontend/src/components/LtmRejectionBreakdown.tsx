type Bucket = {
  code: string;
  label: string;
  count: number;
  pct: number;
  caption?: string;
};

export function LtmRejectionBreakdown({ buckets }: { buckets: Bucket[] }) {
  if (!buckets?.length) return null;
  return (
    <section className="panel" data-testid="ltm-rejection-breakdown">
      <details open>
        <summary>
          <strong>LTM REJECTION BREAKDOWN</strong>
        </summary>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(10rem,1fr))", gap: 10, marginTop: 12 }}>
          {buckets.map((b) => (
            <div key={b.code} className="metric-card">
              <span className="section-label">{b.label}</span>
              <strong>{b.count}</strong>
              <p className="muted-copy">{b.pct}%</p>
              <p className="muted-copy">{b.caption || "First failure"}</p>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}
