import { useMemo, useState } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type BacktestRange = "1Y" | "3Y" | "5Y" | "8Y" | "ALL" | "CUSTOM";
export type ChartView = "equity" | "benchmark" | "drawdown";
export type TradeFilter = "ALL" | "WINNERS" | "LOSERS" | "OPEN";
export type TradeTypeFilter = "ALL" | "LONG" | "SHORT";
export type SortColumn = "index" | "entry_date" | "exit_date" | "pnl_percent" | "holding_days" | "entry_price" | "exit_price";
export type SortDirection = "asc" | "desc";

export type DashboardTrade = {
  trade_id?: string | null;
  entry_date?: string | null;
  exit_date?: string | null;
  type?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  pnl_percent?: number | null;
  holding_days?: number | null;
  reason?: string | null;
  exit_reason?: string | null;
  open?: boolean;
  outcome?: string | null;
  net_pnl?: number | null;
  commission?: number | null;
  slippage?: number | null;
  signal_time?: string | null;
  entry_fill_time?: string | null;
  exit_fill_time?: string | null;
};

export type BacktestDashboardModel = {
  window?: string;
  period_start?: string | null;
  period_end?: string | null;
  total_return?: number | null;
  cagr?: number | null;
  max_drawdown?: number | null;
  max_drawdown_inr?: number | null;
  win_rate?: number | null;
  trade_count?: number | null;
  net_pnl?: number | null;
  gross_profit?: number | null;
  gross_loss?: number | null;
  commission?: number | null;
  outlier_pnl?: number | null;
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
  unavailable_reason?: string | null;
  replay_kind?: string | null;
  symbol?: string | null;
  data_hash?: string | null;
  coverage?: {
    requested_start?: string | null;
    requested_end?: string | null;
    actual_start?: string | null;
    actual_end?: string | null;
    candle_count?: number | null;
    expected_sessions?: number | null;
    coverage_ratio?: number | null;
  } | null;
  strategy_id?: string | null;
  strategy_name?: string | null;
  ledger?: {
    total_trades?: number;
    winning_trades?: number;
    losing_trades?: number;
    breakeven_trades?: number;
    win_rate?: number | null;
    average_profit?: number | null;
    average_loss?: number | null;
    expected_payoff?: number | null;
    expected_payoff_inr?: number | null;
    largest_profit?: number | null;
    largest_loss?: number | null;
    largest_profit_inr?: number | null;
    largest_loss_inr?: number | null;
    gross_profit?: number | null;
    gross_loss?: number | null;
    net_pnl?: number | null;
    commission?: number | null;
    outlier_pnl?: number | null;
    outlier_trades?: number;
    source?: string;
  } | null;
  execution?: {
    profile?: string;
    order_fill_delay?: string;
    historical_fill_mode?: string;
    trail_touch?: string;
  } | null;
  incomplete?: boolean;
  trade_distribution?: {
    total_trades?: number;
    winners?: number;
    losers?: number;
    breakevens?: number;
    open_trades?: number;
    source?: string;
  } | null;
  persisted?: boolean;
  strategy_tester?: {
    total_pnl?: number | null;
    max_drawdown?: number | null;
    total_trades?: number | null;
    profitable_trades?: number | null;
    losing_trades?: number | null;
    breakeven?: number | null;
    profit_factor?: number | null;
    gross_profit?: number | null;
    gross_loss?: number | null;
    commission?: number | null;
    expected_payoff?: number | null;
    largest_profit?: number | null;
    largest_loss?: number | null;
    average_winning_trade?: number | null;
    average_losing_trade?: number | null;
    outlier_pnl?: number | null;
  } | null;
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

function fmtPnl(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  const abs = Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n < 0) return `−₹${abs}`;
  if (n > 0) return `+₹${abs}`;
  return `₹${abs}`;
}

function fmtShare(count: number, total: number): string {
  if (!total) return `${count} / 0`;
  return `${count} / ${total} = ${((count / total) * 100).toFixed(2)}%`;
}

function fmtPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `₹${Number(value).toFixed(2)}`;
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
  if (r === undefined || Number.isNaN(Number(r))) return "var(--bg-card, var(--surface))";
  if (r >= 0.1) return "var(--positive, #38b26d)";
  if (r >= 0.04) return "rgba(56, 178, 109, 0.7)";
  if (r > 0) return "rgba(56, 178, 109, 0.35)";
  if (r <= -0.1) return "var(--negative, #c05c54)";
  if (r <= -0.04) return "rgba(192, 92, 84, 0.7)";
  return "rgba(192, 92, 84, 0.35)";
}

function deriveStrength(model: BacktestDashboardModel | null): { label: string; tone: "favorable" | "mixed" | "weak" | "insufficient" } {
  if (!model) return { label: "Insufficient Data", tone: "insufficient" };
  const reason = (model as { unavailable_reason?: string | null }).unavailable_reason;
  if (reason === "insufficient_history" || model.coverage?.coverage_ratio === 0 || (model.trade_count === 0 && !model.equity_curve?.length)) {
    return { label: "Insufficient Data", tone: "insufficient" };
  }
  const v = (model.verdict || "").toLowerCase();
  if (v === "favorable") return { label: "Favorable", tone: "favorable" };
  if (v === "weak" || reason === "backtest_failed") return { label: "Weak", tone: "weak" };
  if (v === "mixed") return { label: "Mixed", tone: "mixed" };

  if (model.total_return != null) {
    if (model.total_return > 0 && (model.win_rate ?? 0) >= 45 && (model.profit_factor ?? 0) >= 1) {
      return { label: "Favorable", tone: "favorable" };
    }
    if (model.total_return < 0 && (model.win_rate ?? 0) < 40) {
      return { label: "Weak", tone: "weak" };
    }
    return { label: "Mixed", tone: "mixed" };
  }
  return { label: "Insufficient Data", tone: "insufficient" };
}

export function BacktestAnalyticsDashboard({
  model,
  range,
  onRangeChange,
  startDate,
  endDate,
  onCustomRange,
  loading,
  loadError,
  symbol,
  strategyName,
  timeframe = "1D",
}: {
  model: BacktestDashboardModel | null;
  range: BacktestRange;
  onRangeChange: (next: BacktestRange) => void;
  startDate?: string;
  endDate?: string;
  onCustomRange?: (start: string, end: string) => void;
  loading?: boolean;
  loadError?: string | null;
  symbol?: string;
  strategyName?: string;
  timeframe?: string;
}) {
  const [chartView, setChartView] = useState<ChartView>("equity");
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [selectedTradeIndex, setSelectedTradeIndex] = useState<number | null>(null);

  // Trade Log state
  const [tradeFilter, setTradeFilter] = useState<TradeFilter>("ALL");
  const [tradeTypeFilter, setTradeTypeFilter] = useState<TradeTypeFilter>("ALL");
  const [tradeSearch, setTradeSearch] = useState("");
  const [sortCol, setSortCol] = useState<SortColumn>("entry_date");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  const currentSymbol = symbol || model?.symbol || "--";
  const currentStrategy = strategyName || model?.strategy_name || "52-Week High Breakout";
  const currentPeriodText = `${fmtDate(model?.period_start || startDate)} → ${fmtDate(model?.period_end || endDate)}`;
  const currentInitialCapital = fmtMoney(model?.initial_capital ?? 100000);

  const yearsLabel =
    range === "CUSTOM"
      ? `${fmtDate(startDate || model?.period_start)} → ${fmtDate(endDate || model?.period_end)}`
      : range === "ALL"
        ? "All"
        : `${range.replace("Y", "")} Years`;

  const strength = useMemo(() => deriveStrength(model), [model]);

  // Series for Equity, Benchmark, Drawdown, and Signals
  const chartRows = useMemo(() => {
    const eq = model?.equity_curve || [];
    const dd = new Map((model?.drawdown_curve || []).map((p) => [p.date || p.label, p.drawdown]));
    const benchRaw = model?.benchmark_curve || [];
    const firstBench = benchRaw[0]?.close ?? benchRaw[0]?.equity;
    const initialEq = model?.initial_capital || (eq[0]?.equity ?? 100000);

    const benchMap = new Map(
      benchRaw.map((p) => {
        const key = p.date || p.label || "";
        const raw = p.close ?? p.equity;
        const ret = firstBench && raw != null ? ((Number(raw) / Number(firstBench)) - 1) * 100 : null;
        const normalizedEquity = firstBench && raw != null ? Number(initialEq) * (Number(raw) / Number(firstBench)) : null;
        return [key, { ret, equity: normalizedEquity }];
      }),
    );

    const trades = model?.trades || [];
    const entryMap = new Map<string, DashboardTrade[]>();
    const exitMap = new Map<string, DashboardTrade[]>();
    trades.forEach((t) => {
      if (t.entry_date) {
        const d = fmtDate(t.entry_date);
        const list = entryMap.get(d) || [];
        list.push(t);
        entryMap.set(d, list);
      }
      if (t.exit_date && !t.open) {
        const d = fmtDate(t.exit_date);
        const list = exitMap.get(d) || [];
        list.push(t);
        exitMap.set(d, list);
      }
    });

    return eq.map((p) => {
      const key = p.date || p.label || "";
      const benchItem = benchMap.get(key);
      const entries = entryMap.get(key);
      const exits = exitMap.get(key);
      return {
        label: key,
        date: key,
        equity: Number(p.equity),
        drawdown: dd.get(key) ?? null,
        benchmarkEquity: benchItem?.equity ?? null,
        benchmarkReturn: benchItem?.ret ?? null,
        entryTrade: entries?.[0] || null,
        exitTrade: exits?.[0] || null,
      };
    });
  }, [model]);

  // Benchmark stats
  const benchmarkStats = useMemo(() => {
    const benchRaw = model?.benchmark_curve || [];
    if (!benchRaw.length) return null;
    const first = Number(benchRaw[0]?.close ?? benchRaw[0]?.equity ?? 0);
    const last = Number(benchRaw[benchRaw.length - 1]?.close ?? benchRaw[benchRaw.length - 1]?.equity ?? 0);
    if (!first || !last) return null;
    const benchmarkReturn = ((last - first) / first) * 100;
    const stratReturn = model?.total_return ?? null;
    const alpha = stratReturn != null ? stratReturn - benchmarkReturn : null;
    return {
      benchmarkReturn,
      stratReturn,
      alpha,
    };
  }, [model]);

  // Monthly Returns Heatmap matrix
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

  // Trade Statistics — canonical closed-trade ledger only. Never mix in
  // signals, open marks, or another backtest's trade list.
  const tradeStats = useMemo(() => {
    const tester = model?.strategy_tester;
    const ledger = model?.ledger;
    const dist = model?.trade_distribution;
    const trades = (model?.trades || []).filter((t) => !t.open);
    const classified = (outcome: string, fallback: (t: DashboardTrade) => boolean) =>
      trades.filter((t) => (t.outcome ? t.outcome === outcome : fallback(t)));
    const winners = classified("winner", (t) => (t.pnl_percent ?? 0) > 0);
    const losers = classified("loser", (t) => (t.pnl_percent ?? 0) < 0);
    const breakEven = classified("breakeven", (t) => (t.pnl_percent ?? 0) === 0);

    const total = tester?.total_trades ?? dist?.total_trades ?? ledger?.total_trades ?? trades.length;
    const winCount = tester?.profitable_trades ?? dist?.winners ?? ledger?.winning_trades ?? winners.length;
    const lossCount = tester?.losing_trades ?? dist?.losers ?? ledger?.losing_trades ?? losers.length;
    const breakEvenCount = tester?.breakeven ?? dist?.breakevens ?? ledger?.breakeven_trades ?? breakEven.length;

    const winRate = ledger?.win_rate ?? (total > 0 ? (winCount / total) * 100 : model?.win_rate ?? null);
    const avgWin = tester?.average_winning_trade ?? ledger?.average_profit ?? (winCount > 0 ? winners.reduce((s, t) => s + (t.pnl_percent || 0), 0) / winCount : null);
    const avgLoss = tester?.average_losing_trade ?? ledger?.average_loss ?? (lossCount > 0 ? losers.reduce((s, t) => s + (t.pnl_percent || 0), 0) / lossCount : null);

    const largestProfit = tester?.largest_profit ?? ledger?.largest_profit ?? model?.best_trade?.pnl_percent ?? (winners.length ? Math.max(...winners.map((t) => t.pnl_percent || 0)) : null);
    const largestLoss = tester?.largest_loss ?? ledger?.largest_loss ?? model?.worst_trade?.pnl_percent ?? (losers.length ? Math.min(...losers.map((t) => t.pnl_percent || 0)) : null);

    let expectedPayoff: number | null = tester?.expected_payoff ?? ledger?.expected_payoff ?? null;
    if (expectedPayoff == null && total > 0 && winRate != null && avgWin != null && avgLoss != null) {
      expectedPayoff = ((winRate / 100) * avgWin) + (((100 - winRate) / 100) * avgLoss);
    } else if (expectedPayoff == null && model?.avg_trade_return != null) {
      expectedPayoff = model.avg_trade_return;
    }

    return {
      total,
      winCount,
      lossCount,
      breakEvenCount,
      winRate,
      avgWin,
      avgLoss,
      largestProfit,
      largestLoss,
      expectedPayoff,
      expectedPayoffInr: ledger?.expected_payoff_inr ?? null,
      netPnl: tester?.total_pnl ?? ledger?.net_pnl ?? model?.net_pnl ?? null,
      grossProfit: tester?.gross_profit ?? ledger?.gross_profit ?? model?.gross_profit ?? null,
      grossLoss: tester?.gross_loss ?? ledger?.gross_loss ?? model?.gross_loss ?? null,
      commission: tester?.commission ?? ledger?.commission ?? model?.commission ?? null,
      outlierPnl: tester?.outlier_pnl ?? ledger?.outlier_pnl ?? model?.outlier_pnl ?? null,
      outlierTrades: ledger?.outlier_trades ?? 0,
      largestProfitInr: ledger?.largest_profit_inr ?? null,
      largestLossInr: ledger?.largest_loss_inr ?? null,
      maxDrawdownInr: model?.max_drawdown_inr ?? null,
      winRatio: total > 0 ? (winCount / total) * 100 : 0,
      lossRatio: total > 0 ? (lossCount / total) * 100 : 0,
      breakEvenRatio: total > 0 ? (breakEvenCount / total) * 100 : 0,
    };
  }, [model]);

  // Returns Distribution Bins — closed trades from the same ledger list only.
  const returnDistribution = useMemo(() => {
    const trades = (model?.trades || []).filter((t) => t.pnl_percent != null && !t.open);
    if (!trades.length) return [];

    const bins = [
      { range: "<-15%", min: -Infinity, max: -15, count: 0, isPositive: false },
      { range: "-15% to -10%", min: -15, max: -10, count: 0, isPositive: false },
      { range: "-10% to -5%", min: -10, max: -5, count: 0, isPositive: false },
      { range: "-5% to 0%", min: -5, max: 0, count: 0, isPositive: false },
      { range: "0% to +5%", min: 0, max: 5, count: 0, isPositive: true },
      { range: "+5% to +10%", min: 5, max: 10, count: 0, isPositive: true },
      { range: "+10% to +15%", min: 10, max: 15, count: 0, isPositive: true },
      { range: ">+15%", min: 15, max: Infinity, count: 0, isPositive: true },
    ];

    trades.forEach((t) => {
      const pnl = Number(t.pnl_percent);
      for (const b of bins) {
        if (pnl >= b.min && pnl < b.max) {
          b.count += 1;
          break;
        }
      }
    });

    return bins.filter((b) => b.count > 0 || bins.some((x) => x.count > 0));
  }, [model]);

  // Filtered & Sorted Trade Log
  const allTrades = useMemo(() => {
    const raw = model?.trades || [];
    return raw.map((t, idx) => ({ ...t, originalIndex: idx + 1 }));
  }, [model]);

  const filteredTrades = useMemo(() => {
    return allTrades.filter((t) => {
      if (tradeFilter === "WINNERS" && (t.pnl_percent ?? 0) <= 0) return false;
      if (tradeFilter === "LOSERS" && (t.pnl_percent ?? 0) >= 0) return false;
      if (tradeFilter === "OPEN" && !t.open) return false;

      if (tradeTypeFilter === "LONG" && (t.type || "LONG").toUpperCase() !== "LONG") return false;
      if (tradeTypeFilter === "SHORT" && (t.type || "").toUpperCase() !== "SHORT") return false;

      if (tradeSearch.trim()) {
        const q = tradeSearch.toLowerCase();
        const matchesDate = String(t.entry_date || "").includes(q) || String(t.exit_date || "").includes(q);
        const matchesReason = String(t.reason || "").toLowerCase().includes(q);
        const matchesType = String(t.type || "").toLowerCase().includes(q);
        if (!matchesDate && !matchesReason && !matchesType) return false;
      }
      return true;
    });
  }, [allTrades, tradeFilter, tradeTypeFilter, tradeSearch]);

  const sortedTrades = useMemo(() => {
    const list = [...filteredTrades];
    list.sort((a, b) => {
      let valA: any = a[sortCol === "index" ? "originalIndex" : sortCol];
      let valB: any = b[sortCol === "index" ? "originalIndex" : sortCol];
      if (valA == null) return 1;
      if (valB == null) return -1;
      if (typeof valA === "string") {
        return sortDir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return sortDir === "asc" ? Number(valA) - Number(valB) : Number(valB) - Number(valA);
    });
    return list;
  }, [filteredTrades, sortCol, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sortedTrades.length / pageSize));
  const pagedTrades = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedTrades.slice(start, start + pageSize);
  }, [sortedTrades, currentPage, pageSize]);

  const handleSort = (col: SortColumn) => {
    if (sortCol === col) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortCol(col);
      setSortDir("desc");
    }
  };

  const handleTradeCardClick = (targetTrade?: DashboardTrade | null) => {
    if (!targetTrade) return;
    const idx = allTrades.findIndex(
      (t) => t.entry_date === targetTrade.entry_date && t.exit_date === targetTrade.exit_date,
    );
    if (idx !== -1) {
      setSelectedTradeIndex(idx + 1);
      setTradeFilter("ALL");
      setTradeTypeFilter("ALL");
      setTradeSearch("");
      const pageNumber = Math.floor(idx / pageSize) + 1;
      setCurrentPage(pageNumber);
      const logElement = document.getElementById("bt-trade-log-section");
      if (logElement) {
        logElement.scrollIntoView({ behavior: "smooth" });
      }
    }
  };

  const handleExportCSV = () => {
    if (!model?.trades || !model.trades.length) return;
    const headers = ["Index", "Symbol", "Type", "Entry Date", "Exit Date", "Entry Price", "Exit Price", "Return %", "Holding Days", "Exit Reason", "Status"];
    const rows = model.trades.map((t, i) => [
      i + 1,
      currentSymbol,
      t.type || "LONG",
      t.entry_date || "",
      t.open ? "OPEN" : t.exit_date || "",
      t.entry_price != null ? t.entry_price.toFixed(2) : "",
      t.exit_price != null ? t.exit_price.toFixed(2) : "",
      t.pnl_percent != null ? t.pnl_percent.toFixed(2) : "",
      t.holding_days != null ? t.holding_days : "",
      `"${(t.reason || "").replace(/"/g, '""')}"`,
      t.open ? "Open" : "Closed",
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `backtest_${currentSymbol}_${range}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const periodControls = (
    <div className="bt-range" role="group" aria-label="Backtest period">
      {(["1Y", "3Y", "5Y", "8Y", "ALL"] as BacktestRange[]).map((r) => (
        <button
          key={r}
          type="button"
          className={`bt-range__btn ${range === r ? "is-active" : ""}`}
          onClick={() => {
            setCurrentPage(1);
            onRangeChange(r);
          }}
        >
          {r === "ALL" ? "All" : r}
        </button>
      ))}
      <label className="bt-date">
        <span>From</span>
        <input
          type="date"
          aria-label="Backtest start date"
          value={startDate || ""}
          max={endDate || undefined}
          onChange={(e) => {
            const next = e.target.value;
            if (next && endDate) onCustomRange?.(next, endDate);
          }}
        />
      </label>
      <label className="bt-date">
        <span>To</span>
        <input
          type="date"
          aria-label="Backtest end date"
          value={endDate || ""}
          min={startDate || undefined}
          onChange={(e) => {
            const next = e.target.value;
            if (startDate && next) onCustomRange?.(startDate, next);
          }}
        />
      </label>
    </div>
  );

  // Loading State (Section 13)
  if (loading) {
    return (
      <div className="bt-dash bt-dash--loading" data-testid="backtest-loading-state">
        <section className="bt-header-card">
          <div className="bt-header-card__top">
            <div>
              <h2 className="bt-header-card__title">Backtest Performance</h2>
              <p className="bt-header-card__subtitle">Running {yearsLabel.toLowerCase()} backtest for {currentSymbol}...</p>
            </div>
            {periodControls}
          </div>
        </section>

        <div className="bt-metrics-grid">
          {[...Array(7)].map((_, i) => (
            <div key={i} className="bt-metric-card bt-metric-card--skeleton">
              <div className="skeleton skeleton--text" style={{ width: "60%" }} />
              <div className="skeleton skeleton--text" style={{ width: "80%", height: "24px", marginTop: "4px" }} />
            </div>
          ))}
        </div>

        <section className="bt-chart-panel" style={{ minHeight: "320px", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
          <div className="bt-spinner" aria-label="Loading backtest" />
          <p className="muted-copy" style={{ marginTop: "16px" }}>Running {yearsLabel.toLowerCase()} backtest...</p>
        </section>
      </div>
    );
  }

  // Load Error State
  if (loadError && !model) {
    return (
      <section className="subpanel" role="alert" data-testid="backtest-error-state">
        <h3>Unable to load backtest data</h3>
        <p>{loadError}</p>
        <div style={{ marginTop: "12px" }}>{periodControls}</div>
      </section>
    );
  }

  // Empty / No Model State
  if (!model) {
    return (
      <section className="subpanel" data-testid="backtest-empty-state">
        <h3>No backtest support</h3>
        <p>The backend confirmed no historical backtest is available for this symbol and strategy.</p>
        <div style={{ marginTop: "12px" }}>{periodControls}</div>
      </section>
    );
  }

  const pf = model.profit_factor_infinite ? "∞" : fmtNum(model.profit_factor);
  const hasSignals = (model.trades || []).some((t) => t.entry_date || t.exit_date);
  const hasBench = (model.benchmark_curve || []).length > 0;
  const cardsEmpty =
    model.total_return == null &&
    model.cagr == null &&
    model.max_drawdown == null &&
    model.win_rate == null &&
    model.trade_count == null &&
    model.sharpe_ratio == null &&
    model.profit_factor == null &&
    !model.profit_factor_infinite;

  const unavailableReason =
    (model as { unavailable_reason?: string | null }).unavailable_reason ||
    (model.never_selected_in_window ? "never_selected_in_window" : null);

  return (
    <div className="bt-dash" data-testid="backtest-analytics-dashboard">
      {/* Unavailable reason notice if present */}
      {(cardsEmpty || unavailableReason) && (
        <section className="subpanel bt-unavailable-alert" data-testid="backtest-unavailable">
          <div className="bt-unavailable-alert__content">
            <span className="bt-unavailable-alert__badge">Notice</span>
            <p>
              {unavailableReason === "never_selected_in_window"
                ? "Reason: this name was not selected in the strategy book during the selected window."
                : unavailableReason === "backtest_failed"
                  ? "Reason: attribution for this name failed."
                  : unavailableReason === "insufficient_history"
                    ? `Insufficient historical data for the requested ${yearsLabel.toLowerCase()} backtest.` +
                      (model.coverage?.requested_start
                        ? ` Requested: ${model.coverage.requested_start} → ${model.coverage.requested_end}. Available: ${model.coverage.actual_start ?? "none"} → ${model.coverage.actual_end ?? "none"} (${model.coverage.candle_count ?? 0} sessions).`
                        : "")
                    : cardsEmpty
                      ? "Reason: no completed backtest metrics were returned for this strategy and period."
                      : "Reason: backtest data unavailable."}
            </p>
          </div>
        </section>
      )}

      {/* SECTION 1: BACKTEST HEADER & CONFIGURATION SUMMARY */}
      <section className="bt-header-card">
        <div className="bt-header-card__top">
          <div className="bt-header-card__title-group">
            <div className="bt-header-card__title-row">
              <h2 className="bt-header-card__title">Backtest Performance</h2>
              <button
                type="button"
                className="bt-info-btn"
                onClick={() => setShowConfigModal(true)}
                title="View complete backtest configuration"
                aria-label="Backtest configuration details"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="16" x2="12" y2="12" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
              </button>
            </div>
            <p className="bt-header-card__subtitle">
              TradingView-style Strategy Tester presentation of historical execution engine results.
            </p>
          </div>
          {periodControls}
        </div>

        {/* Configuration Summary Pills */}
        <div className="bt-config-strip">
          <div className="bt-config-pill">
            <span className="bt-config-pill__label">Stock</span>
            <strong className="bt-config-pill__val">{currentSymbol}</strong>
          </div>
          <div className="bt-config-pill">
            <span className="bt-config-pill__label">Strategy</span>
            <strong className="bt-config-pill__val">{currentStrategy}</strong>
          </div>
          <div className="bt-config-pill">
            <span className="bt-config-pill__label">Timeframe</span>
            <strong className="bt-config-pill__val">{timeframe}</strong>
          </div>
          {model.execution?.order_fill_delay && (
            <div className="bt-config-pill">
              <span className="bt-config-pill__label">Fill</span>
              <strong className="bt-config-pill__val">{model.execution.order_fill_delay.replace(/_/g, " ")}</strong>
            </div>
          )}
          <div className="bt-config-pill">
            <span className="bt-config-pill__label">Backtest Period</span>
            <strong className="bt-config-pill__val">{currentPeriodText}</strong>
          </div>
          <div className="bt-config-pill">
            <span className="bt-config-pill__label">Initial Capital</span>
            <strong className="bt-config-pill__val">{currentInitialCapital}</strong>
          </div>
          <div className="bt-config-pill">
            <span className="bt-config-pill__label">Commission</span>
            <strong className="bt-config-pill__val">
              {tradeStats.commission == null ? "NSE delivery" : fmtPnl(tradeStats.commission)}
            </strong>
          </div>
        </div>
      </section>

      {/* SECTION 2 & 3: KEY PERFORMANCE CARDS & BACKTEST STRENGTH */}
      <section className="bt-metrics-section">
        <div className="bt-metrics-grid">
          <div className="bt-metric-card">
            <span className="bt-metric-card__label">Total P&L</span>
            <strong className={`bt-metric-card__value ${pnlClass(tradeStats.netPnl)}`}>
              {fmtPnl(tradeStats.netPnl)}
            </strong>
          </div>
          <div className="bt-metric-card">
            <span className="bt-metric-card__label">Total Return</span>
            <strong className={`bt-metric-card__value ${pnlClass(model.total_return)}`}>
              {fmtPct(model.total_return)}
            </strong>
          </div>
          <div className="bt-metric-card">
            <span className="bt-metric-card__label">CAGR</span>
            <strong className={`bt-metric-card__value ${pnlClass(model.cagr)}`}>
              {fmtPct(model.cagr)}
            </strong>
          </div>
          <div className="bt-metric-card">
            <span className="bt-metric-card__label">Max Drawdown</span>
            <strong className="bt-metric-card__value bt-neg">
              {model.max_drawdown == null ? "--" : (model.max_drawdown <= 0 ? fmtPct(model.max_drawdown) : `-${Number(model.max_drawdown).toFixed(2)}%`)}
            </strong>
            {tradeStats.maxDrawdownInr != null ? (
              <span className="bt-metric-card__sub">{fmtPnl(tradeStats.maxDrawdownInr)}</span>
            ) : null}
          </div>
          <div className="bt-metric-card">
            <span className="bt-metric-card__label">Win Rate</span>
            <strong className="bt-metric-card__value">
              {model.win_rate == null ? "--" : `${Number(model.win_rate).toFixed(1)}%`}
            </strong>
          </div>
          <div className="bt-metric-card">
            <span className="bt-metric-card__label">Total Trades</span>
            <strong className="bt-metric-card__value">
              {String(tradeStats.total)}
            </strong>
          </div>
          <div className="bt-metric-card">
            <span className="bt-metric-card__label">Sharpe Ratio</span>
            <strong className="bt-metric-card__value">
              {fmtNum(model.sharpe_ratio)}
            </strong>
          </div>
          <div className="bt-metric-card">
            <span className="bt-metric-card__label">Profit Factor</span>
            <strong className="bt-metric-card__value">
              {pf}
            </strong>
          </div>
        </div>

        {/* SECTION 3: BACKTEST STRENGTH BADGE */}
        <div className="bt-strength-bar">
          <div className="bt-strength-bar__left">
            <span className="bt-strength-bar__label">Backtest Strength</span>
            <div className={`bt-strength-badge bt-strength-badge--${strength.tone}`}>
              <span className="bt-strength-badge__dot" />
              <span>{strength.label}</span>
            </div>
          </div>
          <span className="bt-strength-bar__note">
            Derived from historical risk-adjusted metrics ({yearsLabel})
          </span>
        </div>
      </section>

      {/* SECTION 4, 11 & 12: CHART SECTION (EQUITY CURVE, BENCHMARK, DRAWDOWN) */}
      <section className="bt-chart-panel bt-main-chart-panel">
        <div className="bt-chart-panel__header-row">
          <div>
            <h3 className="bt-panel-title">
              {chartView === "drawdown"
                ? "Drawdown"
                : chartView === "benchmark"
                  ? "Benchmark (NIFTY 500)"
                  : "Equity Curve"}
            </h3>
            <p className="bt-panel-desc">
              {chartView === "drawdown"
                ? "Historical portfolio peak-to-trough equity drawdown percentage"
                : chartView === "benchmark"
                  ? "Strategy equity trajectory compared against NIFTY 500 Buy & Hold"
                  : "Cumulative strategy portfolio equity growth over time"}
            </p>
          </div>

          <div className="bt-range" role="group" aria-label="Chart view">
            <button
              type="button"
              className={`bt-range__btn ${chartView === "equity" ? "is-active" : ""}`}
              onClick={() => setChartView("equity")}
            >
              Equity Curve
            </button>
            <button
              type="button"
              className={`bt-range__btn ${chartView === "benchmark" ? "is-active" : ""}`}
              onClick={() => setChartView("benchmark")}
              disabled={!hasBench}
              title={!hasBench ? "Benchmark data unavailable" : undefined}
            >
              Benchmark
            </button>
            <button
              type="button"
              className={`bt-range__btn ${chartView === "drawdown" ? "is-active" : ""}`}
              onClick={() => setChartView("drawdown")}
            >
              Drawdown
            </button>
          </div>
        </div>

        {chartRows.length ? (
          <div className="bt-chart-container">
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={chartRows} margin={{ top: 12, right: 12, left: 12, bottom: 0 }}>
                <defs>
                  <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={UP} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={UP} stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={DOWN} stopOpacity={0.0} />
                    <stop offset="95%" stopColor={DOWN} stopOpacity={0.35} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
                  stroke="var(--text-muted, #94a3b8)"
                  minTickGap={32}
                  tickFormatter={(v) => {
                    const d = new Date(v);
                    return Number.isNaN(d.getTime()) ? "" : `${d.toLocaleString("default", { month: "short" })} '${String(d.getFullYear()).slice(2)}`;
                  }}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  stroke="var(--text-muted, #94a3b8)"
                  width={64}
                  domain={chartView === "drawdown" ? ["auto", 0] : ["auto", "auto"]}
                  tickFormatter={(v) =>
                    chartView === "drawdown"
                      ? `${Number(v).toFixed(1)}%`
                      : `₹${Number(v).toLocaleString("en-IN", { notation: "compact" })}`
                  }
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const item = payload[0]?.payload;
                    if (!item) return null;
                    return (
                      <div className="bt-chart-tooltip">
                        <div className="bt-chart-tooltip__date">{item.date}</div>
                        {chartView === "drawdown" ? (
                          <div className="bt-chart-tooltip__row">
                            <span className="bt-chart-tooltip__dot" style={{ background: DOWN }} />
                            <span>Drawdown:</span>
                            <strong className="bt-neg">{item.drawdown != null ? `${Number(item.drawdown).toFixed(2)}%` : "--"}</strong>
                          </div>
                        ) : (
                          <>
                            <div className="bt-chart-tooltip__row">
                              <span className="bt-chart-tooltip__dot" style={{ background: UP }} />
                              <span>Strategy:</span>
                              <strong>{fmtMoney(item.equity)}</strong>
                            </div>
                            {item.benchmarkEquity != null && (
                              <div className="bt-chart-tooltip__row">
                                <span className="bt-chart-tooltip__dot" style={{ background: BENCH }} />
                                <span>NIFTY 500:</span>
                                <strong>{fmtMoney(item.benchmarkEquity)} ({fmtPct(item.benchmarkReturn)})</strong>
                              </div>
                            )}
                          </>
                        )}
                        {item.entryTrade && (
                          <div className="bt-chart-tooltip__signal bt-chart-tooltip__signal--entry">
                            <span>▲ Long Entry:</span> {fmtPrice(item.entryTrade.entry_price)}
                          </div>
                        )}
                        {item.exitTrade && (
                          <div className="bt-chart-tooltip__signal bt-chart-tooltip__signal--exit">
                            <span>▼ Exit:</span> {fmtPrice(item.exitTrade.exit_price)} ({fmtPct(item.exitTrade.pnl_percent)})
                          </div>
                        )}
                      </div>
                    );
                  }}
                />
                {chartView === "drawdown" ? (
                  <Area
                    type="monotone"
                    dataKey="drawdown"
                    stroke={DOWN}
                    strokeWidth={2}
                    fill="url(#drawdownGradient)"
                    name="Drawdown %"
                    isAnimationActive={false}
                  />
                ) : (
                  <>
                    <Area
                      type="monotone"
                      dataKey="equity"
                      stroke={UP}
                      strokeWidth={2.2}
                      fill="url(#equityGradient)"
                      name="Strategy Equity"
                      isAnimationActive={false}
                    />
                    {hasBench && (chartView === "benchmark" || chartView === "equity") && (
                      <Line
                        type="monotone"
                        dataKey="benchmarkEquity"
                        stroke={BENCH}
                        strokeWidth={1.8}
                        strokeDasharray="3 3"
                        dot={false}
                        name="NIFTY 500 (Buy & Hold)"
                        isAnimationActive={false}
                      />
                    )}
                  </>
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="muted-copy">No equity curve series available for this period.</p>
        )}

        {/* Legend & Benchmarking Pill */}
        <div className="bt-chart-footer">
          <div className="bt-legend">
            {chartView === "drawdown" ? (
              <span><i style={{ background: DOWN }} /> Strategy Drawdown %</span>
            ) : (
              <>
                <span><i style={{ background: UP }} /> Strategy Equity</span>
                {hasBench && (
                  <span><i style={{ background: BENCH, borderTop: "1px dashed #3b82f6" }} /> NIFTY 500 Buy & Hold</span>
                )}
              </>
            )}
          </div>

          {/* SECTION 12: BENCHMARKING COMPARISON */}
          {benchmarkStats ? (
            <div className="bt-bench-summary">
              <span className="bt-bench-summary__item">
                Strategy: <strong>{fmtPct(benchmarkStats.stratReturn)}</strong>
              </span>
              <span className="bt-bench-summary__divider">vs</span>
              <span className="bt-bench-summary__item">
                NIFTY 500: <strong>{fmtPct(benchmarkStats.benchmarkReturn)}</strong>
              </span>
              <span className={`bt-bench-summary__alpha ${pnlClass(benchmarkStats.alpha)}`}>
                Alpha: {fmtPct(benchmarkStats.alpha)}
              </span>
            </div>
          ) : (
            <span className="muted-copy" style={{ fontSize: "0.78rem" }}>Benchmark unavailable</span>
          )}
        </div>

        {/* SECTION 11: SIGNAL VISUALIZATION TRACK */}
        {hasSignals && (
          <div className="bt-signal-track">
            <div className="bt-signal-track__label">Signal Execution Track</div>
            <div className="bt-legend" style={{ marginBottom: 4 }}>
              <span><i style={{ background: UP }} /> Long Entry</span>
              <span><i style={{ background: DOWN }} /> Exit</span>
            </div>
            <ResponsiveContainer width="100%" height={44}>
              <ComposedChart data={chartRows} margin={{ top: 4, right: 12, left: 12, bottom: 0 }}>
                <XAxis dataKey="label" hide />
                <YAxis hide domain={[0, 1]} />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="transparent"
                  isAnimationActive={false}
                  dot={(props: any) => {
                    const { cx, cy, payload } = props;
                    if (payload.entryTrade) {
                      return <path key={`entry-${payload.label}`} d={`M${cx},${12} l-4,8 l8,0 Z`} fill={UP} />;
                    }
                    if (payload.exitTrade) {
                      return <path key={`exit-${payload.label}`} d={`M${cx},${28} l-4,-8 l8,0 Z`} fill={DOWN} />;
                    }
                    return <g key={`none-${payload.label}`} />;
                  }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {/* SECTION 5: MONTHLY RETURNS HEATMAP */}
      <section className="bt-chart-panel">
        <div className="bt-chart-panel__header-row">
          <div>
            <h3 className="bt-panel-title">Monthly Returns (%)</h3>
            <p className="bt-panel-desc">Matrix of calendar month returns and full year performance</p>
          </div>
        </div>
        {heatmap.length ? (
          <div className="bt-heat-wrap">
            <table className="bt-heat">
              <thead>
                <tr>
                  <th>Year</th>
                  {MONTHS.map((m) => (
                    <th key={m}>{m}</th>
                  ))}
                  <th>Year</th>
                </tr>
              </thead>
              <tbody>
                {heatmap.map(({ yr, months }) => {
                  let prod = 1;
                  let any = false;
                  return (
                    <tr key={yr}>
                      <td className="bt-heat__year-cell">{yr}</td>
                      {MONTHS.map((m) => {
                        const r = months[m];
                        if (r !== undefined) {
                          prod *= 1 + r;
                          any = true;
                        }
                        const isMissing = r === undefined;
                        const sign = r != null && r > 0 ? "+" : "";
                        return (
                          <td
                            key={m}
                            style={{
                              background: heatColor(r),
                              color: isMissing ? "var(--text-muted)" : "#fff",
                            }}
                          >
                            {isMissing ? "--" : `${sign}${(r * 100).toFixed(1)}%`}
                          </td>
                        );
                      })}
                      <td
                        className="bt-heat__total-cell"
                        style={{
                          background: any ? heatColor(prod - 1) : "var(--bg-card)",
                          color: any ? "#fff" : "var(--text-muted)",
                        }}
                      >
                        {any ? `${prod - 1 > 0 ? "+" : ""}${((prod - 1) * 100).toFixed(1)}%` : "--"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted-copy">Monthly returns not available for this period.</p>
        )}
      </section>

      {/* SECTION 6 & 7: BACKTEST SUMMARY & TRADE ANALYSIS */}
      <div className="bt-split-grid">
        {/* SECTION 6: BACKTEST SUMMARY */}
        <section className="bt-chart-panel">
          <div className="bt-chart-panel__header-row">
            <div>
              <h3 className="bt-panel-title">Backtest Summary</h3>
              <p className="bt-panel-desc">Core parameters and portfolio milestones</p>
            </div>
          </div>
          <dl className="bt-summary-list">
            <div className="bt-summary-list__row">
              <dt>Backtest Period</dt>
              <dd>{currentPeriodText}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Initial Capital</dt>
              <dd>{fmtMoney(model.initial_capital)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Ending Capital</dt>
              <dd>{fmtMoney(model.ending_capital)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Total Return</dt>
              <dd className={pnlClass(model.total_return)}>{fmtPct(model.total_return)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Best Trade</dt>
              <dd className="bt-pos">{fmtPct(model.best_trade?.pnl_percent)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Worst Trade</dt>
              <dd className="bt-neg">{fmtPct(model.worst_trade?.pnl_percent)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average Trade Return</dt>
              <dd className={pnlClass(model.avg_trade_return)}>{fmtPct(model.avg_trade_return)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Max Consecutive Losses</dt>
              <dd>{model.max_consecutive_losses == null ? "--" : String(model.max_consecutive_losses)}</dd>
            </div>
          </dl>
        </section>

        {/* SECTION 7: TRADE ANALYSIS */}
        <section className="bt-chart-panel">
          <div className="bt-chart-panel__header-row">
            <div>
              <h3 className="bt-panel-title">Trade Analysis</h3>
              <p className="bt-panel-desc">Win/loss mechanics and expectancy statistics</p>
            </div>
          </div>

          {/* Winner/Loser Visual Ratio Bar */}
          <div className="bt-trade-ratio-wrap">
            <div className="bt-trade-ratio-bar">
              <div
                className="bt-trade-ratio-bar__segment bt-trade-ratio-bar__segment--win"
                style={{ width: `${tradeStats.winRatio}%` }}
                title={`Winners: ${tradeStats.winCount} (${tradeStats.winRatio.toFixed(1)}%)`}
              />
              <div
                className="bt-trade-ratio-bar__segment bt-trade-ratio-bar__segment--be"
                style={{ width: `${tradeStats.breakEvenRatio}%` }}
                title={`Break-even: ${tradeStats.breakEvenCount}`}
              />
              <div
                className="bt-trade-ratio-bar__segment bt-trade-ratio-bar__segment--loss"
                style={{ width: `${tradeStats.lossRatio}%` }}
                title={`Losers: ${tradeStats.lossCount} (${tradeStats.lossRatio.toFixed(1)}%)`}
              />
            </div>
            <div className="bt-trade-ratio-labels">
              <span className="bt-pos">Winners <strong>{tradeStats.winCount}</strong></span>
              <span className="muted-copy">Break-even <strong>{tradeStats.breakEvenCount}</strong></span>
              <span className="bt-neg">Losers <strong>{tradeStats.lossCount}</strong></span>
            </div>
          </div>

          <dl className="bt-summary-list" data-testid="strategy-tester-report">
            <div className="bt-summary-list__row">
              <dt>Total P&L</dt>
              <dd className={pnlClass(tradeStats.netPnl)}>{fmtPnl(tradeStats.netPnl)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Max Drawdown</dt>
              <dd className="bt-neg">
                {tradeStats.maxDrawdownInr != null ? fmtPnl(tradeStats.maxDrawdownInr) : "--"}
                {model.max_drawdown != null
                  ? ` (${model.max_drawdown <= 0 ? fmtPct(model.max_drawdown) : `-${Number(model.max_drawdown).toFixed(2)}%`})`
                  : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Total Trades</dt>
              <dd>{tradeStats.total}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Profitable trades</dt>
              <dd className="bt-pos">{fmtShare(tradeStats.winCount, tradeStats.total)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Losing trades</dt>
              <dd className="bt-neg">{fmtShare(tradeStats.lossCount, tradeStats.total)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Breakeven</dt>
              <dd>{fmtShare(tradeStats.breakEvenCount, tradeStats.total)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Win Rate</dt>
              <dd>{tradeStats.winRate != null ? `${tradeStats.winRate.toFixed(2)}%` : "--"}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Profit Factor</dt>
              <dd>{pf}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Gross Profit</dt>
              <dd className="bt-pos">{fmtPnl(tradeStats.grossProfit)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Gross Loss</dt>
              <dd className="bt-neg">{fmtPnl(tradeStats.grossLoss)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Commission</dt>
              <dd>{fmtPnl(tradeStats.commission)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Expected Payoff</dt>
              <dd className={pnlClass(tradeStats.expectedPayoffInr ?? tradeStats.expectedPayoff)}>
                {tradeStats.expectedPayoffInr != null ? fmtPnl(tradeStats.expectedPayoffInr) : "--"}
                {tradeStats.expectedPayoff != null ? ` (${fmtPct(tradeStats.expectedPayoff)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Largest Profit</dt>
              <dd className="bt-pos">
                {tradeStats.largestProfitInr != null ? fmtPnl(tradeStats.largestProfitInr) : "--"}
                {tradeStats.largestProfit != null ? ` (${fmtPct(tradeStats.largestProfit)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Largest Loss</dt>
              <dd className="bt-neg">
                {tradeStats.largestLossInr != null ? fmtPnl(tradeStats.largestLossInr) : "--"}
                {tradeStats.largestLoss != null ? ` (${fmtPct(tradeStats.largestLoss)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average winning trade</dt>
              <dd className="bt-pos">{fmtPct(tradeStats.avgWin)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average losing trade</dt>
              <dd className="bt-neg">{fmtPct(tradeStats.avgLoss)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Outlier P&L</dt>
              <dd className={pnlClass(tradeStats.outlierPnl)}>
                {fmtPnl(tradeStats.outlierPnl)}
                {tradeStats.outlierTrades ? ` (${tradeStats.outlierTrades} trades)` : ""}
              </dd>
            </div>
          </dl>
        </section>
      </div>

      {/* Trades Distribution — same closed-trade ledger as the Detailed Trade Log */}
      <section className="bt-chart-panel" data-testid="trades-distribution">
        <div className="bt-chart-panel__header-row">
          <div>
            <h3 className="bt-panel-title">Trades Distribution</h3>
            <p className="bt-panel-desc">
              Closed-trade outcomes from the canonical ledger ({tradeStats.total} trades). Open marks are excluded.
            </p>
          </div>
        </div>
        <div className="bt-trade-dist-grid">
          <div className="bt-trade-dist-card">
            <span className="bt-metric-card__label">Total trades</span>
            <strong className="bt-metric-card__value">{tradeStats.total}</strong>
          </div>
          <div className="bt-trade-dist-card bt-trade-dist-card--win">
            <span className="bt-metric-card__label">Winners</span>
            <strong className="bt-metric-card__value bt-pos">{tradeStats.winCount} trades</strong>
            <span className="bt-metric-card__sub">{fmtShare(tradeStats.winCount, tradeStats.total)}</span>
          </div>
          <div className="bt-trade-dist-card bt-trade-dist-card--loss">
            <span className="bt-metric-card__label">Losers</span>
            <strong className="bt-metric-card__value bt-neg">{tradeStats.lossCount} trades</strong>
            <span className="bt-metric-card__sub">{fmtShare(tradeStats.lossCount, tradeStats.total)}</span>
          </div>
          <div className="bt-trade-dist-card">
            <span className="bt-metric-card__label">Breakevens</span>
            <strong className="bt-metric-card__value">{tradeStats.breakEvenCount} trades</strong>
            <span className="bt-metric-card__sub">{fmtShare(tradeStats.breakEvenCount, tradeStats.total)}</span>
          </div>
        </div>
      </section>

      {/* SECTION 8: RETURNS DISTRIBUTION HISTOGRAM */}
      <section className="bt-chart-panel">
        <div className="bt-chart-panel__header-row">
          <div>
            <h3 className="bt-panel-title">Returns Distribution</h3>
            <p className="bt-panel-desc">Frequency distribution of trade returns across performance buckets</p>
          </div>
          <div className="bt-dist-averages">
            <span className="bt-dist-avg-tag bt-dist-avg-tag--pos">
              Avg Winner: <strong>{fmtPct(tradeStats.avgWin)}</strong>
            </span>
            <span className="bt-dist-avg-tag bt-dist-avg-tag--neg">
              Avg Loser: <strong>{fmtPct(tradeStats.avgLoss)}</strong>
            </span>
          </div>
        </div>

        {returnDistribution.length ? (
          <div className="bt-chart-container">
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={returnDistribution} margin={{ top: 12, right: 12, left: -16, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="range" tickLine={false} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} stroke="var(--text-muted, #94a3b8)" />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} stroke="var(--text-muted, #94a3b8)" />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const item = payload[0]?.payload;
                    return (
                      <div className="bt-chart-tooltip">
                        <div>Bucket: <strong>{item.range}</strong></div>
                        <div>Trades: <strong>{item.count}</strong></div>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                  {returnDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.isPositive ? UP : DOWN} />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="muted-copy">No completed trades to compute returns distribution.</p>
        )}
      </section>

      {/* SECTION 10: BEST AND WORST TRADES INTERACTIVE CARDS */}
      <div className="bt-trade-cards-grid">
        <div
          className="bt-trade-highlight-card bt-trade-highlight-card--pos"
          onClick={() => handleTradeCardClick(model.best_trade)}
          role="button"
          tabIndex={0}
          title="Click to locate best trade in trade log"
        >
          <div className="bt-trade-highlight-card__header">
            <span className="bt-trade-highlight-card__badge bt-pos">Best Trade</span>
            <span className="bt-trade-highlight-card__hint">Click to inspect ↗</span>
          </div>
          {model.best_trade && model.best_trade.pnl_percent != null ? (
            <>
              <div className="bt-trade-highlight-card__dates">
                {fmtDate(model.best_trade.entry_date)} → {fmtDate(model.best_trade.exit_date)}
              </div>
              <strong className="bt-trade-highlight-card__pnl bt-pos">
                {fmtPct(model.best_trade.pnl_percent)}
              </strong>
              <div className="bt-trade-highlight-card__meta">
                <span>Entry: {fmtPrice(model.best_trade.entry_price)}</span>
                <span>Exit: {fmtPrice(model.best_trade.exit_price)}</span>
                {model.best_trade.holding_days != null && <span>{model.best_trade.holding_days}d</span>}
              </div>
            </>
          ) : (
            <p className="muted-copy">No winning trade recorded.</p>
          )}
        </div>

        <div
          className="bt-trade-highlight-card bt-trade-highlight-card--neg"
          onClick={() => handleTradeCardClick(model.worst_trade)}
          role="button"
          tabIndex={0}
          title="Click to locate worst trade in trade log"
        >
          <div className="bt-trade-highlight-card__header">
            <span className="bt-trade-highlight-card__badge bt-neg">Worst Trade</span>
            <span className="bt-trade-highlight-card__hint">Click to inspect ↗</span>
          </div>
          {model.worst_trade && model.worst_trade.pnl_percent != null ? (
            <>
              <div className="bt-trade-highlight-card__dates">
                {fmtDate(model.worst_trade.entry_date)} → {fmtDate(model.worst_trade.exit_date)}
              </div>
              <strong className="bt-trade-highlight-card__pnl bt-neg">
                {fmtPct(model.worst_trade.pnl_percent)}
              </strong>
              <div className="bt-trade-highlight-card__meta">
                <span>Entry: {fmtPrice(model.worst_trade.entry_price)}</span>
                <span>Exit: {fmtPrice(model.worst_trade.exit_price)}</span>
                {model.worst_trade.holding_days != null && <span>{model.worst_trade.holding_days}d</span>}
              </div>
            </>
          ) : (
            <p className="muted-copy">No losing trade recorded.</p>
          )}
        </div>
      </div>

      {/* SECTION 9: PROFESSIONAL TRADE LOG TABLE */}
      <section className="bt-chart-panel" id="bt-trade-log-section">
        <div className="bt-chart-panel__header-row">
          <div>
            <h3 className="bt-panel-title">Detailed Trade Log</h3>
            <p className="bt-panel-desc">
              Canonical closed-trade ledger: {tradeStats.total} closed
              {allTrades.length !== tradeStats.total ? ` (${allTrades.length} rows including open marks)` : ""}
              {sortedTrades.length > pageSize ? ` · page ${currentPage} of ${totalPages}` : ""}
            </p>
          </div>
          <button
            type="button"
            className="bt-export-btn"
            onClick={handleExportCSV}
            disabled={!allTrades.length}
            title="Download complete trade log as CSV"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Export CSV
          </button>
        </div>

        {/* Filters Toolbar */}
        <div className="bt-table-toolbar">
          <div className="bt-table-toolbar__filters">
            <div className="bt-filter-pill-group" role="group" aria-label="Result filter">
              <button
                type="button"
                className={`bt-filter-pill ${tradeFilter === "ALL" ? "is-active" : ""}`}
                onClick={() => { setTradeFilter("ALL"); setCurrentPage(1); }}
              >
                All ({allTrades.length})
              </button>
              <button
                type="button"
                className={`bt-filter-pill ${tradeFilter === "WINNERS" ? "is-active" : ""}`}
                onClick={() => { setTradeFilter("WINNERS"); setCurrentPage(1); }}
              >
                Winners ({tradeStats.winCount})
              </button>
              <button
                type="button"
                className={`bt-filter-pill ${tradeFilter === "LOSERS" ? "is-active" : ""}`}
                onClick={() => { setTradeFilter("LOSERS"); setCurrentPage(1); }}
              >
                Losers ({tradeStats.lossCount})
              </button>
              {allTrades.some((t) => t.open) && (
                <button
                  type="button"
                  className={`bt-filter-pill ${tradeFilter === "OPEN" ? "is-active" : ""}`}
                  onClick={() => { setTradeFilter("OPEN"); setCurrentPage(1); }}
                >
                  Open ({allTrades.filter((t) => t.open).length})
                </button>
              )}
            </div>

            <div className="bt-filter-pill-group" role="group" aria-label="Type filter">
              <button
                type="button"
                className={`bt-filter-pill ${tradeTypeFilter === "ALL" ? "is-active" : ""}`}
                onClick={() => { setTradeTypeFilter("ALL"); setCurrentPage(1); }}
              >
                All Types
              </button>
              <button
                type="button"
                className={`bt-filter-pill ${tradeTypeFilter === "LONG" ? "is-active" : ""}`}
                onClick={() => { setTradeTypeFilter("LONG"); setCurrentPage(1); }}
              >
                Long
              </button>
              <button
                type="button"
                className={`bt-filter-pill ${tradeTypeFilter === "SHORT" ? "is-active" : ""}`}
                onClick={() => { setTradeTypeFilter("SHORT"); setCurrentPage(1); }}
              >
                Short
              </button>
            </div>
          </div>

          <div className="bt-table-toolbar__search">
            <input
              type="text"
              placeholder="Search date, type, reason..."
              value={tradeSearch}
              onChange={(e) => {
                setTradeSearch(e.target.value);
                setCurrentPage(1);
              }}
              className="bt-search-input"
              aria-label="Search trade log"
            />
          </div>
        </div>

        {/* Trade Log Table */}
        {sortedTrades.length ? (
          <>
            <div className="bt-table-wrap">
              <table className="data-table bt-pro-table">
                <thead>
                  <tr>
                    <th onClick={() => handleSort("index")} className="bt-sortable-th">
                      # {sortCol === "index" && (sortDir === "asc" ? "▲" : "▼")}
                    </th>
                    <th onClick={() => handleSort("entry_date")} className="bt-sortable-th">
                      Entry Date {sortCol === "entry_date" && (sortDir === "asc" ? "▲" : "▼")}
                    </th>
                    <th onClick={() => handleSort("exit_date")} className="bt-sortable-th">
                      Exit Date {sortCol === "exit_date" && (sortDir === "asc" ? "▲" : "▼")}
                    </th>
                    <th>Type</th>
                    <th onClick={() => handleSort("entry_price")} className="bt-sortable-th bt-num-col">
                      Entry Price {sortCol === "entry_price" && (sortDir === "asc" ? "▲" : "▼")}
                    </th>
                    <th onClick={() => handleSort("exit_price")} className="bt-sortable-th bt-num-col">
                      Exit Price {sortCol === "exit_price" && (sortDir === "asc" ? "▲" : "▼")}
                    </th>
                    <th onClick={() => handleSort("pnl_percent")} className="bt-sortable-th bt-num-col">
                      Return % {sortCol === "pnl_percent" && (sortDir === "asc" ? "▲" : "▼")}
                    </th>
                    <th onClick={() => handleSort("holding_days")} className="bt-sortable-th bt-num-col">
                      Holding Days {sortCol === "holding_days" && (sortDir === "asc" ? "▲" : "▼")}
                    </th>
                    <th>Exit Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedTrades.map((t) => {
                    const isSelected = selectedTradeIndex === t.originalIndex;
                    return (
                      <tr
                        key={`${t.entry_date}-${t.originalIndex}`}
                        className={isSelected ? "bt-row-selected" : ""}
                        onClick={() => setSelectedTradeIndex(t.originalIndex)}
                      >
                        <td className="bt-index-col">{t.originalIndex}</td>
                        <td>{fmtDate(t.entry_date)}</td>
                        <td>
                          {t.open ? (
                            <span className="bt-open-badge">OPEN</span>
                          ) : (
                            fmtDate(t.exit_date)
                          )}
                        </td>
                        <td>
                          <span className={`bt-type-badge bt-type-badge--${(t.type || "LONG").toLowerCase()}`}>
                            {t.type || "LONG"}
                          </span>
                        </td>
                        <td className="bt-num-col">{fmtPrice(t.entry_price)}</td>
                        <td className="bt-num-col">{t.open ? "--" : fmtPrice(t.exit_price)}</td>
                        <td className={`bt-num-col ${pnlClass(t.pnl_percent)}`}>
                          {t.pnl_percent != null ? fmtPct(t.pnl_percent) : "--"}
                        </td>
                        <td className="bt-num-col">{t.holding_days != null ? `${t.holding_days}d` : "--"}</td>
                        <td className="bt-reason-col">{t.reason || "--"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="bt-pagination">
                <div className="bt-pagination__info">
                  Showing {(currentPage - 1) * pageSize + 1}–
                  {Math.min(currentPage * pageSize, sortedTrades.length)} of {sortedTrades.length} trades
                </div>
                <div className="bt-pagination__buttons">
                  <button
                    type="button"
                    className="bt-pagination__btn"
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                  >
                    Previous
                  </button>
                  <span className="bt-pagination__page-num">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    type="button"
                    className="bt-pagination__btn"
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="muted-copy" style={{ padding: "20px 0" }}>No trades match the selected criteria.</p>
        )}
      </section>

      {/* CONFIGURATION DETAILS MODAL */}
      {showConfigModal && (
        <div className="bt-modal-backdrop" onClick={() => setShowConfigModal(false)}>
          <div className="bt-modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="bt-modal-panel__header">
              <h3>Backtest Configuration</h3>
              <button
                type="button"
                className="bt-modal-close"
                onClick={() => setShowConfigModal(false)}
                aria-label="Close configuration modal"
              >
                ✕
              </button>
            </div>
            <div className="bt-modal-panel__body">
              <dl className="bt-summary-list">
                <div className="bt-summary-list__row">
                  <dt>Target Stock</dt>
                  <dd>{currentSymbol}</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Strategy</dt>
                  <dd>{currentStrategy}</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Timeframe</dt>
                  <dd>{timeframe}</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Backtest Window</dt>
                  <dd>{range} ({currentPeriodText})</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Initial Capital</dt>
                  <dd>{currentInitialCapital}</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Replay Mode</dt>
                  <dd>{model.replay_kind || "symbol_window"}</dd>
                </div>
                {model.data_hash && (
                  <div className="bt-summary-list__row">
                    <dt>Dataset Hash</dt>
                    <dd style={{ fontSize: "0.75rem", fontFamily: "monospace" }}>{model.data_hash.slice(0, 16)}...</dd>
                  </div>
                )}
                {model.coverage && (
                  <>
                    <div className="bt-summary-list__row">
                      <dt>Candle Sessions</dt>
                      <dd>{model.coverage.candle_count ?? "--"} bars</dd>
                    </div>
                    <div className="bt-summary-list__row">
                      <dt>Coverage Ratio</dt>
                      <dd>{model.coverage.coverage_ratio != null ? `${(model.coverage.coverage_ratio * 100).toFixed(1)}%` : "--"}</dd>
                    </div>
                  </>
                )}
              </dl>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
