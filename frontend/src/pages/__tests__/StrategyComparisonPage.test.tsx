import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StrategyComparisonPage } from "../StrategyComparisonPage";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(globalThis, "ResizeObserver", { writable: true, value: ResizeObserverStub });

const catalog = {
  strategies: [
    {
      id: "strat-a",
      name: "Alpha Momentum",
      description: "Trend follow",
      completed_run_count: 1,
      completed_lean_count: 0,
      has_pine: false,
      latest_run: {
        run_id: "STR-A1",
        source: "strategy_tester",
        status: "completed",
        strategy_name: "Alpha Momentum",
        start_date: "2024-01-02",
        end_date: "2024-06-28",
        universe: "ALL_755",
        timeframe: "1D",
        completed_at: "2024-06-28T10:00:00Z",
        label: "Scan · 2024-01-02 → 2024-06-28 · ALL_755",
      },
    },
    {
      id: "strat-b",
      name: "Beta Breakout",
      description: "Breakout",
      completed_run_count: 1,
      completed_lean_count: 0,
      has_pine: true,
      latest_run: {
        run_id: "STR-B1",
        source: "strategy_tester",
        status: "completed",
        strategy_name: "Beta Breakout",
        start_date: "2024-01-02",
        end_date: "2024-06-28",
        universe: "NIFTY500",
        timeframe: "1D",
        completed_at: "2024-06-28T10:00:00Z",
        label: "Scan · 2024-01-02 → 2024-06-28 · NIFTY500",
      },
    },
  ],
  suggestions: [
    {
      title: "Alpha Momentum vs Beta Breakout",
      subtitle: "Completed Strategy Tester / LEAN runs",
      strategy_ids: ["strat-a", "strat-b"],
      names: ["Alpha Momentum", "Beta Breakout"],
    },
  ],
  min_slots: 2,
  max_slots: 4,
  strategy_count: 2,
};

const runsA = {
  strategy_id: "strat-a",
  strategy_name: "Alpha Momentum",
  runs: [
    {
      run_id: "STR-A1",
      source: "strategy_tester",
      status: "completed",
      strategy_name: "Alpha Momentum",
      start_date: "2024-01-02",
      end_date: "2024-06-28",
      universe: "ALL_755",
      timeframe: "1D",
      completed_at: "2024-06-28T10:00:00Z",
      label: "Scan · 2024-01-02 → 2024-06-28 · ALL_755",
    },
  ],
};

const runsB = {
  strategy_id: "strat-b",
  strategy_name: "Beta Breakout",
  runs: [
    {
      run_id: "STR-B1",
      source: "strategy_tester",
      status: "completed",
      strategy_name: "Beta Breakout",
      start_date: "2024-01-02",
      end_date: "2024-06-28",
      universe: "NIFTY500",
      timeframe: "1D",
      completed_at: "2024-06-28T10:00:00Z",
      label: "Scan · 2024-01-02 → 2024-06-28 · NIFTY500",
    },
  ],
};

function slotPayload(id: string, name: string, runId: string, universe: string, pine: string | null) {
  return {
    slot_id: id,
    strategy_id: id,
    strategy_name: name,
    run_id: runId,
    source: "strategy_tester",
    status: "completed",
    logic: {
      source_type: pine ? "pine" : "builder",
      pine_code: pine,
      entry_conditions: ["Close > SMA 50"],
      exit_conditions: ["Window End"],
      indicators: ["SMA 50"],
      filters: ["Close > SMA 50"],
      stop_loss: "5%",
      take_profit: "10%",
      trailing_stop: null,
      position_type: "LONG",
      time_exit_bars: null,
    },
    metrics: {
      net_profit: null,
      total_return_pct: 1.5,
      cagr: null,
      win_rate: 50,
      total_trades: 2,
      profit_factor: null,
      average_trade: 1.5,
      average_trade_unit: "pct",
      max_drawdown: null,
      max_drawdown_pct: null,
      sharpe_ratio: null,
      sortino_ratio: null,
      long_trades: 2,
      short_trades: 0,
      best_trade: { symbol: "RELIANCE", return_pct: 12 },
      worst_trade: { symbol: "TCS", return_pct: -6 },
      final_equity: null,
      initial_capital: 100000,
      metrics_source: "strategy_tester",
      metrics_note: "Strategy Tester scan metrics.",
    },
    config: {
      start_date: "2024-01-02",
      end_date: "2024-06-28",
      universe,
      universe_size: 3,
      timeframe: "1D",
      initial_capital: 100000,
      commission: null,
      slippage: null,
      position_type: "LONG",
      source: "strategy_tester",
    },
    signals: [
      { symbol: "RELIANCE", signal: "BUY", return_pct: 12 },
      { symbol: "TCS", signal: "BUY", return_pct: -6 },
    ],
    trades: [
      {
        symbol: "RELIANCE",
        entry_price: 100,
        exit_price: 112,
        net_pnl: null,
        return_pct: 12,
        holding_period: null,
        holding_window: "2024-01-02 → 2024-06-28",
        exit_reason: "WINDOW_END",
      },
    ],
    equity_curve: [],
    drawdown_curve: [],
    monthly_returns: [],
    yearly_returns: [],
    trade_distribution: [
      { bucket: "gt_10", label: "> 10%", count: 1 },
      { bucket: "pos5_10", label: "5% to 10%", count: 0 },
      { bucket: "pos0_5", label: "0% to 5%", count: 0 },
      { bucket: "eq_0", label: "0%", count: 0 },
      { bucket: "neg5_0", label: "-5% to 0%", count: 0 },
      { bucket: "neg10_neg5", label: "-10% to -5%", count: 1 },
      { bucket: "lt_neg10", label: "< -10%", count: 0 },
    ],
    scan_summary: { buy: 2, watch: 0, reject: 0, universe_size: 3 },
  };
}

function leanSlotPayload() {
  const slot = slotPayload("s1", "Beta Breakout", "STR-B1", "NIFTY500", "//@version=6\nstrategy('beta')\n");
  return {
    ...slot,
    source: "lean",
    metrics: {
      ...slot.metrics,
      net_profit: 12400,
      total_return_pct: 12.4,
      cagr: 8.1,
      win_rate: 55.25,
      total_trades: 18,
      profit_factor: 1.4,
      average_trade: 0.82,
      max_drawdown: 10500,
      max_drawdown_pct: 10.5,
      sharpe_ratio: 0.9,
      sortino_ratio: 1.1,
      calmar_ratio: 0.7714,
      avg_cash: 80000,
      avg_exposure_pct: 22.5,
      long_trades: 18,
      metrics_source: "lean",
      metrics_note: "LEAN backtest summary.",
      best_trade: { symbol: "INFY", return_pct: 18.2 },
      worst_trade: { symbol: "HDFCBANK", return_pct: -9.1 },
    },
    config: { ...slot.config, source: "lean" },
  };
}

const comparison = {
  slot_count: 2,
  aligned_config: false,
  config_warnings: [{ field: "universe", label: "Universe", message: "Universe differs across selected runs.", values: ["ALL_755", "NIFTY500"] }],
  slots: [
    slotPayload("s0", "Alpha Momentum", "STR-A1", "ALL_755", null),
    leanSlotPayload(),
  ],
  radar: {
    axes: [
      { key: "win_rate", label: "Win Rate", higher_is_better: true },
      { key: "total_return_pct", label: "Return %", higher_is_better: true },
      { key: "total_trades", label: "Trades", higher_is_better: true },
      { key: "buy_count", label: "BUY signals", higher_is_better: true },
      { key: "watch_count", label: "WATCH", higher_is_better: true },
      { key: "average_trade", label: "Avg Return", higher_is_better: true },
    ],
    series: [
      {
        slot_id: "s0",
        name: "Alpha Momentum",
        values: { win_rate: 50, total_return_pct: 30, total_trades: 100, buy_count: 80, watch_count: 40, average_trade: 30 },
        raw: { win_rate: 50, total_return_pct: 1.5, total_trades: 2, buy_count: 2, watch_count: 0, average_trade: 1.5 },
      },
      {
        slot_id: "s1",
        name: "Beta Breakout",
        values: { win_rate: 50, total_return_pct: 30, total_trades: 50, buy_count: 40, watch_count: 100, average_trade: 30 },
        raw: { win_rate: 50, total_return_pct: 1.5, total_trades: 1, buy_count: 1, watch_count: 1, average_trade: 1.5 },
      },
    ],
    note: "Radar axes are a display scale of the same raw metrics. They are not a ranking.",
  },
  signals: {
    available: true,
    unavailable_reason: null,
    pairwise: [
      {
        left_slot_id: "s0",
        right_slot_id: "s1",
        shared_buy: ["RELIANCE"],
        left_only_buy: ["TCS"],
        right_only_buy: [],
        shared_count: 1,
        overlap_pct: 50,
      },
    ],
    overlap_pct: 50,
    symbols: [
      { symbol: "RELIANCE", signals: { s0: "BUY", s1: "BUY" } },
      { symbol: "TCS", signals: { s0: "BUY", s1: null } },
    ],
    symbol_count: 2,
  },
  trades: {
    symbols: [
      {
        symbol: "RELIANCE",
        by_slot: {
          s0: { symbol: "RELIANCE", entry_price: 100, exit_price: 112, return_pct: 12, net_pnl: null, exit_reason: "WINDOW_END" },
          s1: { symbol: "RELIANCE", entry_price: 100, exit_price: 108, return_pct: 8, net_pnl: null, exit_reason: "WINDOW_END" },
        },
      },
    ],
    symbol_count: 1,
  },
  has_equity: false,
  has_pine: true,
};

vi.mock("../../api_strategy_comparison", () => ({
  fetchComparisonCatalog: vi.fn(async () => catalog),
  fetchComparisonRuns: vi.fn(async (id: string) => (id === "strat-a" ? runsA : runsB)),
  compareStrategies: vi.fn(async () => comparison),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <StrategyComparisonPage />
    </MemoryRouter>,
  );
}

describe("StrategyComparisonPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows empty state until two strategies and runs are selected", async () => {
    renderPage();
    expect(await screen.findByTestId("strategy-comparison-page")).toBeTruthy();
    expect(screen.getByTestId("sc-empty-state")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Strategy Comparison" })).toBeTruthy();
    expect(screen.queryByText(/best strategy/i)).toBeNull();
  });

  it("adds and removes a strategy slot", async () => {
    renderPage();
    await screen.findByTestId("sc-slots");
    fireEvent.click(screen.getByTestId("sc-add-strategy"));
    expect(screen.getByTestId("sc-slot-2")).toBeTruthy();
    fireEvent.click(screen.getByTestId("sc-remove-2"));
    expect(screen.queryByTestId("sc-slot-2")).toBeNull();
  });

  it("compares selected strategies with real API payload and warns on config mismatch", async () => {
    renderPage();
    await screen.findByTestId("sc-select-cta-0");
    fireEvent.click(screen.getByTestId("sc-select-cta-0"));
    fireEvent.click(await screen.findByText("Alpha Momentum"));
    await waitFor(() => expect(screen.getByTestId("sc-run-select-0")).toBeTruthy());
    fireEvent.change(screen.getByTestId("sc-run-select-0"), { target: { value: "STR-A1" } });

    fireEvent.click(screen.getByTestId("sc-select-cta-1"));
    fireEvent.click(await screen.findByText("Beta Breakout"));
    await waitFor(() => expect(screen.getByTestId("sc-run-select-1")).toBeTruthy());
    fireEvent.change(screen.getByTestId("sc-run-select-1"), { target: { value: "STR-B1" } });

    expect(await screen.findByTestId("sc-config-warning")).toBeTruthy();
    expect(screen.getByTestId("sc-radar")).toBeTruthy();
    expect(screen.getByTestId("sc-radar-chart")).toBeTruthy();
    expect(screen.getByTestId("sc-leaderboard")).toBeTruthy();
    const leaderboard = screen.getByTestId("sc-leaderboard");
    const radar = screen.getByTestId("sc-radar");
    const metrics = screen.getByTestId("sc-metrics");
    expect(leaderboard.compareDocumentPosition(radar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(leaderboard.compareDocumentPosition(metrics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    (
      [
        ["rank", "Rank"],
        ["strategy", "Strategy"],
        ["score", "Score"],
        ["grade", "Grade"],
        ["trades", "Trades"],
        ["winRate", "Win Rate"],
        ["pf", "PF"],
        ["avgTrade", "Avg Trade"],
        ["cagr", "CAGR"],
        ["totalReturn", "Total Return"],
        ["maxDd", "Max DD"],
        ["calmar", "Calmar"],
        ["avgCash", "Avg Cash"],
        ["avgExposure", "Avg Exposure"],
        ["bestTrade", "Best Trade"],
        ["worstTrade", "Worst Trade"],
      ] as const
    ).forEach(([key, label]) => {
      expect(screen.getByTestId(`sc-lb-col-${key}`).textContent).toBe(label);
    });
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("₹80,000");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("8.10%");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("1.40");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("22.5%");
    expect(screen.getByTestId("sc-lb-row-s0").textContent).toMatch(/—/);
    expect(screen.getByTestId("sc-metrics")).toBeTruthy();
    expect(screen.getByTestId("sc-logic")).toBeTruthy();
    expect(screen.getByTestId("sc-signals")).toBeTruthy();
    expect(screen.getByTestId("sc-trades")).toBeTruthy();
    expect(screen.getByTestId("sc-pine")).toBeTruthy();
    expect(screen.getAllByText("Win Rate").length).toBeGreaterThan(0);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByTestId("sc-summary")).toBeTruthy();
    expect(screen.getByTestId("sc-charts")).toBeTruthy();
    expect(screen.getByTestId("sc-config")).toBeTruthy();
    expect(screen.queryByText(/best strategy/i)).toBeNull();
  });

  it("shows related comparison cards from saved strategies", async () => {
    renderPage();
    expect(await screen.findByTestId("sc-related")).toBeTruthy();
    expect(screen.getByText("Alpha Momentum vs Beta Breakout")).toBeTruthy();
  });

  it("loads scan results after picking a related pair", async () => {
    renderPage();
    fireEvent.click(await screen.findByText("Alpha Momentum vs Beta Breakout"));
    expect(await screen.findByTestId("sc-metrics")).toBeTruthy();
    expect(await screen.findByTestId("sc-leaderboard")).toBeTruthy();
    expect(await screen.findByTestId("sc-radar")).toBeTruthy();
    expect(screen.getAllByText("BUY signals").length).toBeGreaterThan(0);
    expect(screen.getByTestId("sc-signals")).toBeTruthy();
    expect(screen.getByTestId("sc-charts")).toBeTruthy();
  });

  it("highlights differences without declaring a winner", async () => {
    renderPage();
    await screen.findByTestId("sc-select-cta-0");
    fireEvent.click(screen.getByTestId("sc-select-cta-0"));
    fireEvent.click(await screen.findByText("Alpha Momentum"));
    await waitFor(() => expect(screen.getByTestId("sc-run-select-0")).toBeTruthy());
    fireEvent.change(screen.getByTestId("sc-run-select-0"), { target: { value: "STR-A1" } });
    fireEvent.click(screen.getByTestId("sc-select-cta-1"));
    fireEvent.click(await screen.findByText("Beta Breakout"));
    await waitFor(() => expect(screen.getByTestId("sc-run-select-1")).toBeTruthy());
    fireEvent.change(screen.getByTestId("sc-run-select-1"), { target: { value: "STR-B1" } });
    await screen.findByTestId("sc-metrics");
    fireEvent.click(screen.getByTestId("sc-highlight-toggle"));
    expect(screen.queryByText(/best strategy/i)).toBeNull();
    expect(screen.getByTestId("sc-leaderboard-note").textContent).toMatch(/radar display-scale/i);
    expect(screen.getByTestId("sc-leaderboard").querySelectorAll(".sc-cell--hi").length).toBeGreaterThan(0);
  });
});
