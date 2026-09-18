import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { InfoTooltip } from "./InfoTooltip";

export type BacktestRange = "1Y" | "3Y" | "5Y" | "ALL";
export type ChartView = "equity" | "benchmark" | "drawdown";

export type DashboardTrade = {
  entry_date?: string | null;
  exit_date?: string | null;
  type?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  pnl_percent?: number | null;
  holding_days?: number | null;
  reason?: string | null;
  open?: boolean;
};

export type BacktestDashboardModel = {
  window?: string;
  period_start?: string | null;
  period_end?: string | null;
  total_return?: number | null;
  cagr?: number | null;
  max_drawdown?: number | null;
  win_rate?: number | null;
  trade_count?: number | null;
  sharpe_ratio?: number | null;
  profit_factor?: number | null;
  profit_factor_infinite?: boolean;
  initial_capital?: number | null;
  ending_capital?: number | null;
  avg_trade_return?: number | null;
  max_consecutive_losses?: number | null;
  verdict?: string | null;
  equity_curve?: { date?: string; label?: string; equity: number }[];
  drawdown_curve?: { date?: string; label?: string; drawdown: number }[];
  benchmark_curve?: { date?: string; label?: string; close?: number; equity?: number }[];
  monthly_returns?: { month: string; return: number | null }[];
  trades?: DashboardTrade[];
  best_trade?: DashboardTrade | null;
  worst_trade?: DashboardTrade | null;
  top_winning?: DashboardTrade[];
  top_losing?: DashboardTrade[];
  never_selected_in_window?: boolean;
};

const UP = "#38b26d";
const DOWN = "#c05c54";
const BENCH = "#3b82f6";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

function fmtNum(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function fmtMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function fmtDate(value?: string | null): string {
  if (!value) return "--";
  return String(value).slice(0, 10);
}

function pnlClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return value >= 0 ? "bt-pos" : "bt-neg";
}

function heatColor(r: number | undefined): string {
  if (r === undefined || Number.isNaN(Number(r))) return "var(--bg-card)";
  if (r >= 0.1) return "var(--positive)";
  if (r >= 0.02) return "var(--positive-soft, rgba(56,178,109,0.55))";
  if (r > 0) return "rgba(56, 178, 109, 0.3)";
  if (r <= -0.1) return "var(--negative)";
  if (r <= -0.02) return "var(--negative-soft, rgba(192,92,84,0.55))";
  return "rgba(192, 92, 84, 0.3)";
}

export function BacktestAnalyticsDashboard({
  model,
  range,
  onRangeChange,
  loading,
  loadError,
}: {
  model: BacktestDashboardModel | null;
  range: BacktestRange;
  onRangeChange: (next: BacktestRange) => void;
  loading?: boolean;
  loadError?: string | null;
}) {
  const [chartView, setChartView] = useState<ChartView>("equity");
  const yearsLabel = range === "ALL" ? "All" : `${range.replace("Y", "")} Years`;

  const chartRows = useMemo(() => {
    const eq = model?.equity_curve || [];
    const dd = new Map((model?.drawdown_curve || []).map((p) => [p.date || p.label, p.drawdown]));
    const benchRaw = model?.benchmark_curve || [];
    const firstBench = benchRaw[0]?.close ?? benchRaw[0]?.equity;
    const benchMap = new Map(
      benchRaw.map((p) => {
        const key = p.date || p.label || "";
        const raw = p.close ?? p.equity;
        const ret = firstBench && raw != null ? ((Number(raw) / Number(firstBench)) - 1) * 100 : null;
        return [key, ret];
      }),
    );
    const trades = model?.trades || [];
    const entries = new Set(trades.map((t) => fmtDate(t.entry_date)));
    const exits = new Set(trades.map((t) => fmtDate(t.exit_date)));
    return eq.map((p) => {
      const key = p.date || p.label || "";
      return {
        label: key,
        equity: Number(p.equity),
        drawdown: dd.get(key) ?? null,
        benchmark: benchMap.get(key) ?? null,
        entry: entries.has(key),
        exit: exits.has(key),
      };
    });
  }, [model]);

  const heatmap = useMemo(() => {
    const data: Record<string, Record<string, number>> = {};
    for (const m of model?.monthly_returns || []) {
      const parts = String(m.month).split("-");
      if (parts.length < 2 || m.return === null || m.return === undefined) continue;
      const yr = parts[0];
      const mo = MONTHS[parseInt(parts[1], 10) - 1];
      if (!mo) continue;
      if (!data[yr]) data[yr] = {};
      data[yr][mo] = Number(m.return);
    }
    return Object.keys(data).sort().reverse().map((yr) => ({ yr, months: data[yr] }));
  }, [model]);

  const tradesNewest = useMemo(() => {
    const list = [...(model?.trades || [])];
    list.sort((a, b) => String(b.entry_date || "").localeCompare(String(a.entry_date || "")));
    return list.slice(0, 10);
  }, [model]);

  if (loading) {
    return <section className="subpanel"><p className="muted-copy">Loading backtest analytics…</p></section>;
  }
  if (loadError && !model) {
    return (
      <section className="subpanel" role="alert">
        <h3>Unable to load backtest data</h3>
        <p>{loadError}</p>
      </section>
    );
  }
  if (!model) {
    return (
      <section className="subpanel">
        <h3>No backtest support</h3>
        <p>The backend confirmed no historical backtest is available for this symbol and strategy.</p>
      </section>
    );
  }

  const pf = model.profit_factor_infinite ? "∞" : fmtNum(model.profit_factor);
  const hasSignals = (model.trades || []).some((t) => t.entry_date || t.exit_date);
  const hasBench = (model.benchmark_curve || []).length > 0;

  return (
    <div className="bt-dash" data-testid="backtest-analytics-dashboard">
      <section className="bt-dash__header">
        <div className="bt-dash__title-row">
          <h3>Backtest Performance ({yearsLabel})</h3>
          <InfoTooltip content="Analytics from the existing backtest engine for the selected period. Values are not forecasts." />
          <div className="bt-range" role="group" aria-label="Backtest period">
            {(["1Y", "3Y", "5Y", "ALL"] as BacktestRange[]).map((r) => (
              <button
                key={r}
                type="button"
                className={`bt-range__btn ${range === r ? "is-active" : ""}`}
                onClick={() => onRangeChange(r)}
              >
                {r === "ALL" ? "All" : r}
              </button>
            ))}
          </div>
        </div>
        <div className="bt-metrics-grid">
          <Metric label="Total Return" value={fmtPct(model.total_return)} tone={model.total_return ?? null} />
          <Metric label="CAGR" value={fmtPct(model.cagr)} tone={model.cagr ?? null} />
          <Metric label="Max Drawdown" value={fmtPct(model.max_drawdown)} tone={-1} />
          <Metric label="Win Rate" value={model.win_rate == null ? "--" : `${model.win_rate.toFixed(1)}%`} />
          <Metric label="Total Trades" value={model.trade_count == null ? "--" : String(model.trade_count)} />
          <Metric label="Sharpe" value={fmtNum(model.sharpe_ratio)} />
          <Metric label="Profit Factor" value={pf} />
        </div>
        {model.verdict ? (
          <p className="helper-text">Backtest strength: {model.verdict} ({yearsLabel})</p>
        ) : null}
      </section>

      <div className="bt-dash__charts">
        <section className="bt-chart-panel bt-dash__equity">
          <div className="bt-chart-panel__header">
            <h3>{chartView === "drawdown" ? "Drawdown" : chartView === "benchmark" ? "Benchmark (NIFTY 500)" : "Equity Curve"}</h3>
            <div className="bt-range" role="group" aria-label="Chart view">
              {([
                ["equity", "Equity Curve"],
                ["benchmark", "Benchmark (NIFTY 500)"],
                ["drawdown", "Drawdown"],
              ] as const).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`bt-range__btn ${chartView === id ? "is-active" : ""}`}
                  onClick={() => setChartView(id)}
                  disabled={id === "benchmark" && !hasBench}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {chartRows.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartRows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" vertical={false} stroke="var(--border-color)" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} stroke="var(--text-muted)" minTickGap={28} tickFormatter={(v) => {
                  const d = new Date(v);
                  return Number.isNaN(d.getTime()) ? "" : `${d.getMonth() + 1}/${String(d.getFullYear()).slice(2)}`;
                }} />
                <YAxis tickLine={false} axisLine={false} stroke="var(--text-muted)" width={56} tickFormatter={(v) => chartView === "drawdown" ? `${v}%` : `₹${Number(v).toLocaleString("en-IN", { notation: "compact" })}`} />
                <Tooltip contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: 6 }} />
                {chartView === "drawdown" ? (
                  <Area type="monotone" dataKey="drawdown" stroke={DOWN} fill={DOWN} fillOpacity={0.3} name="Drawdown %" />
                ) : (
                  <>
                    <Line type="monotone" dataKey="equity" stroke={UP} strokeWidth={2} dot={false} name="Strategy Equity" />
                    {hasBench && (chartView === "benchmark" || chartView === "equity") ? (
                      <Line type="monotone" dataKey="benchmark" stroke={BENCH} strokeWidth={2} dot={false} name="NIFTY 500 (Buy & Hold)" />
                    ) : null}
                  </>
                )}
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <p className="muted-copy">No equity series for this period.</p>
          )}
          <div className="bt-legend">
            <span><i style={{ background: UP }} /> Strategy Equity</span>
            {hasBench ? <span><i style={{ background: BENCH }} /> NIFTY 500 (Buy & Hold)</span> : null}
          </div>
        </section>

        <section className="bt-chart-panel bt-dash__dd">
          <div className="bt-chart-panel__header">
            <h3>Drawdown Chart</h3>
            <span className="bt-neg">Max DD: {fmtPct(model.max_drawdown)}</span>
          </div>
          {chartRows.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={chartRows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" vertical={false} stroke="var(--border-color)" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} stroke="var(--text-muted)" minTickGap={32} tickFormatter={(v) => {
                  const d = new Date(v);
                  return Number.isNaN(d.getTime()) ? "" : `${d.getMonth() + 1}/${String(d.getFullYear()).slice(2)}`;
                }} />
                <YAxis tickLine={false} axisLine={false} stroke="var(--text-muted)" width={48} tickFormatter={(v) => `${v}%`} />
                <Tooltip contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: 6 }} formatter={(v: number) => [`${v}%`, "Drawdown"]} />
                <Area type="monotone" dataKey="drawdown" stroke={DOWN} fill={DOWN} fillOpacity={0.35} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <p className="muted-copy">No drawdown series for this period.</p>
          )}
        </section>
      </div>

      <div className="bt-dash__mid">
        <section className="bt-chart-panel">
          <div className="bt-chart-panel__header"><h3>Monthly Returns (%)</h3></div>
          {heatmap.length ? (
            <div className="bt-heat-wrap">
              <table className="bt-heat">
                <thead>
                  <tr>
                    <th>Year</th>
                    {MONTHS.map((m) => <th key={m}>{m}</th>)}
                    <th>Year</th>
                  </tr>
                </thead>
                <tbody>
                  {heatmap.map(({ yr, months }) => {
                    let prod = 1;
                    let any = false;
                    return (
                      <tr key={yr}>
                        <td>{yr}</td>
                        {MONTHS.map((m) => {
                          const r = months[m];
                          if (r !== undefined) {
                            prod *= 1 + r;
                            any = true;
                          }
                          return (
                            <td key={m} style={{ background: heatColor(r), color: r === undefined ? "var(--text-muted)" : "#fff" }}>
                              {r === undefined ? "–" : `${(r * 100).toFixed(1)}`}
                            </td>
                          );
                        })}
                        <td style={{ background: any ? heatColor(prod - 1) : "var(--bg-card)", color: any ? "#fff" : "var(--text-muted)" }}>
                          {any ? `${((prod - 1) * 100).toFixed(1)}` : "–"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted-copy">Monthly returns not available.</p>
          )}
        </section>

        <section className="bt-chart-panel">
          <div className="bt-chart-panel__header"><h3>Backtest Summary</h3></div>
          <dl className="bt-summary">
            <div><dt>Backtest Period</dt><dd>{fmtDate(model.period_start)} → {fmtDate(model.period_end)}</dd></div>
            <div><dt>Initial Capital</dt><dd>{fmtMoney(model.initial_capital)}</dd></div>
            <div><dt>Ending Capital</dt><dd>{fmtMoney(model.ending_capital)}</dd></div>
            <div><dt>Total Return</dt><dd className={pnlClass(model.total_return)}>{fmtPct(model.total_return)}</dd></div>
            <div><dt>Best Trade</dt><dd className="bt-pos">{model.best_trade?.pnl_percent == null ? "--" : fmtPct(model.best_trade.pnl_percent)}</dd></div>
            <div><dt>Worst Trade</dt><dd className="bt-neg">{model.worst_trade?.pnl_percent == null ? "--" : fmtPct(model.worst_trade.pnl_percent)}</dd></div>
            <div><dt>Average Trade Return</dt><dd>{fmtPct(model.avg_trade_return)}</dd></div>
            <div><dt>Max Consecutive Losses</dt><dd>{model.max_consecutive_losses == null ? "--" : String(model.max_consecutive_losses)}</dd></div>
          </dl>
        </section>
      </div>

      {hasSignals ? (
        <section className="bt-chart-panel">
          <div className="bt-chart-panel__header"><h3>Trade Signals</h3></div>
          <div className="bt-legend">
            <span><i style={{ background: UP }} /> Long Entry</span>
            <span><i style={{ background: DOWN }} /> Exit</span>
          </div>
          <ResponsiveContainer width="100%" height={72}>
            <ComposedChart data={chartRows}>
              <XAxis dataKey="label" hide />
              <YAxis hide domain={[0, 1]} />
              <Line type="monotone" dataKey="equity" stroke="transparent" dot={(props: any) => {
                const { cx, cy, payload } = props;
                if (payload.entry) return <path key={`e-${payload.label}`} d={`M${cx},${8} l-4,8 l8,0 Z`} fill={UP} />;
                if (payload.exit) return <path key={`x-${payload.label}`} d={`M${cx},${24} l-4,-8 l8,0 Z`} fill={DOWN} />;
                return <g key={`n-${payload.label}`} />;
              }} />
            </ComposedChart>
          </ResponsiveContainer>
        </section>
      ) : null}

      <section className="bt-chart-panel">
        <div className="bt-chart-panel__header"><h3>Trade Log (Last 10 Trades)</h3></div>
        {tradesNewest.length ? (
          <div className="bt-table-wrap">
            <table className="data-table bt-log">
              <thead>
                <tr>
                  <th>#</th><th>Entry Date</th><th>Exit Date</th><th>Type</th>
                  <th>Entry Price</th><th>Exit Price</th><th>Return %</th><th>Holding Days</th><th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {tradesNewest.map((t, i) => (
                  <tr key={`${t.entry_date}-${i}`}>
                    <td>{i + 1}</td>
                    <td>{fmtDate(t.entry_date)}</td>
                    <td>{t.open ? "open" : fmtDate(t.exit_date)}</td>
                    <td>{t.type || "LONG"}</td>
                    <td>{t.entry_price == null ? "--" : Number(t.entry_price).toFixed(2)}</td>
                    <td>{t.exit_price == null ? "--" : Number(t.exit_price).toFixed(2)}</td>
                    <td className={pnlClass(t.pnl_percent)}>{t.pnl_percent == null ? "--" : fmtPct(t.pnl_percent)}</td>
                    <td>{t.holding_days == null ? "--" : t.holding_days}</td>
                    <td>{t.reason || "--"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted-copy">No completed trades for this period.</p>
        )}
      </section>

      <div className="bt-dash__bottom">
        <TradeCard title="Best Trade" trade={model.best_trade} positive />
        <TradeCard title="Worst Trade" trade={model.worst_trade} />
        <RankList title="Top 5 Winning Trades" trades={model.top_winning || []} empty="No winning trades." />
        <RankList title="Top 5 Losing Trades" trades={model.top_losing || []} empty="No losing trades." losing />
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: number | null }) {
  const cls = tone == null ? "" : tone >= 0 ? "bt-pos" : "bt-neg";
  return (
    <div className="metric-tile">
      <span>{label}</span>
      <strong className={cls}>{value}</strong>
    </div>
  );
}

function TradeCard({ title, trade, positive }: { title: string; trade?: DashboardTrade | null; positive?: boolean }) {
  return (
    <section className="bt-chart-panel" style={{ borderLeft: trade ? `4px solid ${positive ? UP : DOWN}` : undefined }}>
      <h3>{title}</h3>
      {trade && trade.pnl_percent != null ? (
        <>
          <p className="muted-copy">{fmtDate(trade.entry_date)} → {fmtDate(trade.exit_date)}</p>
          <strong className={positive ? "bt-pos" : "bt-neg"}>{fmtPct(trade.pnl_percent)}</strong>
        </>
      ) : (
        <p className="muted-copy">No completed trades for this period.</p>
      )}
    </section>
  );
}

function RankList({ title, trades, empty, losing }: { title: string; trades: DashboardTrade[]; empty: string; losing?: boolean }) {
  return (
    <section className="bt-chart-panel">
      <h3>{title}</h3>
      {trades.length ? (
        <ol className="bt-rank">
          {trades.slice(0, 5).map((t, i) => (
            <li key={`${t.entry_date}-${i}`} className={losing ? "bt-neg" : "bt-pos"}>
              {fmtDate(t.entry_date)} → {fmtDate(t.exit_date)}
              <span>{fmtPct(t.pnl_percent)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted-copy">{empty}</p>
      )}
    </section>
  );
}
