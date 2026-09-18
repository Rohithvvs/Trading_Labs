import { expect, test, type Page } from "@playwright/test";

const user = {
  id: "e2e-compare-user",
  email: "compare@example.com",
  full_name: "Compare User",
  role: "trader",
};

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
      completed_lean_count: 1,
      has_pine: true,
      latest_run: {
        run_id: "LEAN-B1",
        source: "lean",
        status: "completed",
        strategy_name: "Beta Breakout",
        start_date: "2024-01-02",
        end_date: "2024-06-28",
        universe: "NIFTY500",
        timeframe: "1D",
        completed_at: "2024-06-28T10:00:00Z",
        label: "LEAN · 2024-01-02 → 2024-06-28 · NIFTY500",
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

function scanSlot() {
  return {
    slot_id: "s0",
    strategy_id: "strat-a",
    strategy_name: "Alpha Momentum",
    run_id: "STR-A1",
    source: "strategy_tester",
    status: "completed",
    logic: {
      source_type: "builder",
      pine_code: null,
      entry_conditions: ["Close > SMA 50"],
      exit_conditions: ["Window End"],
      indicators: ["SMA 50"],
      filters: [],
      stop_loss: null,
      take_profit: null,
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
      calmar_ratio: null,
      avg_cash: null,
      avg_exposure_pct: null,
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
      universe: "ALL_755",
      universe_size: 3,
      timeframe: "1D",
      initial_capital: 100000,
      commission: null,
      slippage: null,
      position_type: "LONG",
      source: "strategy_tester",
    },
    signals: [{ symbol: "RELIANCE", signal: "BUY", return_pct: 12 }],
    trades: [{ symbol: "RELIANCE", return_pct: 12, exit_reason: "WINDOW_END" }],
    equity_curve: [],
    drawdown_curve: [],
    monthly_returns: [],
    yearly_returns: [],
    trade_distribution: [],
    scan_summary: { buy: 2, watch: 0, reject: 0, universe_size: 3 },
  };
}

function leanSlot() {
  return {
    slot_id: "s1",
    strategy_id: "strat-b",
    strategy_name: "Beta Breakout",
    run_id: "LEAN-B1",
    source: "lean",
    status: "completed",
    logic: {
      source_type: "pine",
      pine_code: "//@version=6\nstrategy('beta')\n",
      entry_conditions: ["Breakout"],
      exit_conditions: ["Stop"],
      indicators: ["High"],
      filters: [],
      stop_loss: "5%",
      take_profit: "10%",
      trailing_stop: null,
      position_type: "LONG",
      time_exit_bars: null,
    },
    metrics: {
      net_profit: 12400,
      total_return_pct: 12.4,
      cagr: 8.1,
      win_rate: 55.25,
      total_trades: 18,
      profit_factor: 1.4,
      average_trade: 0.82,
      average_trade_unit: "pct",
      max_drawdown: 10500,
      max_drawdown_pct: 10.5,
      sharpe_ratio: 0.9,
      sortino_ratio: 1.1,
      calmar_ratio: 0.7714,
      avg_cash: 80000,
      avg_exposure_pct: 22.5,
      long_trades: 18,
      short_trades: 0,
      best_trade: { symbol: "INFY", return_pct: 18.2 },
      worst_trade: { symbol: "HDFCBANK", return_pct: -9.1 },
      final_equity: 112400,
      initial_capital: 100000,
      metrics_source: "lean",
      metrics_note: "LEAN backtest summary.",
    },
    config: {
      start_date: "2024-01-02",
      end_date: "2024-06-28",
      universe: "NIFTY500",
      universe_size: 3,
      timeframe: "1D",
      initial_capital: 100000,
      commission: 0.03,
      slippage: 0.05,
      position_type: "LONG",
      source: "lean",
    },
    signals: [],
    trades: [{ symbol: "INFY", return_pct: 18.2, net_pnl: 1800 }],
    equity_curve: [
      { date: "2024-01-02", equity: 100000, cash: 90000, invested: 10000 },
      { date: "2024-06-28", equity: 112400, cash: 70000, invested: 42400 },
    ],
    drawdown_curve: [{ date: "2024-03-01", drawdown: -5000, drawdown_pct: -5 }],
    monthly_returns: [],
    yearly_returns: [],
    trade_distribution: [],
    scan_summary: null,
  };
}

const comparison = {
  slot_count: 2,
  aligned_config: false,
  config_warnings: [{ field: "universe", label: "Universe", message: "Universe differs across selected runs.", values: ["ALL_755", "NIFTY500"] }],
  slots: [scanSlot(), leanSlot()],
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
        values: { win_rate: 50, total_return_pct: 30, total_trades: 40, buy_count: 80, watch_count: 20, average_trade: 30 },
        raw: { win_rate: 50, total_return_pct: 1.5, total_trades: 2, buy_count: 2, watch_count: 0, average_trade: 1.5 },
      },
      {
        slot_id: "s1",
        name: "Beta Breakout",
        values: { win_rate: 70, total_return_pct: 90, total_trades: 100, buy_count: 40, watch_count: 10, average_trade: 50 },
        raw: { win_rate: 55.25, total_return_pct: 12.4, total_trades: 18, buy_count: 1, watch_count: 0, average_trade: 0.82 },
      },
    ],
    note: "Radar axes are a display scale of the same raw metrics.",
  },
  signals: {
    available: true,
    unavailable_reason: null,
    pairwise: [
      {
        left_slot_id: "s0",
        right_slot_id: "s1",
        shared_buy: ["RELIANCE"],
        left_only_buy: [],
        right_only_buy: [],
        shared_count: 1,
        overlap_pct: 50,
      },
    ],
    overlap_pct: 50,
    symbols: [{ symbol: "RELIANCE", signals: { s0: "BUY", s1: null } }],
    symbol_count: 1,
  },
  trades: { symbols: [], symbol_count: 0 },
  has_equity: true,
  has_pine: true,
};

async function mockSessionAndComparison(page: Page) {
  await page.addInitScript((profile) => {
    sessionStorage.setItem("auth_user_profile", JSON.stringify(profile));
    sessionStorage.setItem("auth_user_role", profile.role);
  }, user);

  await page.route("**/auth/me", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) }),
  );
  await page.route("**/features", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "advanced_scanner",
            feature_key: "advanced_scanner",
            description: "Advanced scanner",
            allowed_roles: ["trader", "admin"],
            is_active: true,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ],
      }),
    }),
  );
  await page.route("**/strategy-comparison/catalog", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalog) }),
  );
  await page.route("**/strategy-comparison/strategies/strat-a/runs", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ strategy_id: "strat-a", strategy_name: "Alpha Momentum", runs: [catalog.strategies[0].latest_run] }),
    }),
  );
  await page.route("**/strategy-comparison/strategies/strat-b/runs", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ strategy_id: "strat-b", strategy_name: "Beta Breakout", runs: [catalog.strategies[1].latest_run] }),
    }),
  );
  await page.route("**/strategy-comparison", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(comparison) });
      return;
    }
    await route.fallback();
  });
}

test("strategy comparison shows the top summary table above other sections", async ({ page }) => {
  await mockSessionAndComparison(page);
  await page.goto("/strategy-comparison");
  await expect(page.getByTestId("strategy-comparison-page")).toBeVisible();
  await page.getByText("Alpha Momentum vs Beta Breakout").click();
  await expect(page.getByTestId("sc-leaderboard")).toBeVisible();

  for (const label of [
    "Rank",
    "Strategy",
    "Score",
    "Grade",
    "Trades",
    "Win Rate",
    "PF",
    "Avg Trade",
    "CAGR",
    "Total Return",
    "Max DD",
    "Calmar",
    "Avg Cash",
    "Avg Exposure",
    "Best Trade",
    "Worst Trade",
  ]) {
    await expect(page.getByTestId("sc-leaderboard").getByText(label, { exact: true })).toBeVisible();
  }

  const leaderboardBox = await page.getByTestId("sc-leaderboard").boundingBox();
  const radarBox = await page.getByTestId("sc-radar-chart").boundingBox();
  const metricsBox = await page.getByTestId("sc-metrics").boundingBox();
  expect(leaderboardBox).toBeTruthy();
  expect(radarBox).toBeTruthy();
  expect(metricsBox).toBeTruthy();
  expect(leaderboardBox!.y).toBeLessThan(radarBox!.y);
  expect(leaderboardBox!.y).toBeLessThan(metricsBox!.y);

  await expect(page.getByTestId("sc-lb-row-s1")).toContainText("Beta Breakout");
  await expect(page.getByTestId("sc-lb-row-s1").locator(".sc-lb-rank")).toHaveText("1");
  await expect(page.getByTestId("sc-lb-row-s1")).toContainText("₹80,000");
  await expect(page.getByTestId("sc-lb-row-s1")).toContainText("8.10%");
  await expect(page.getByTestId("sc-lb-row-s1")).toContainText("1.40");
  await expect(page.getByTestId("sc-lb-row-s1")).toContainText("INFY +18.20%");
  await expect(page.getByTestId("sc-lb-row-s0")).toContainText("—");

  await page.getByTestId("sc-slots").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../tests/artifacts/playwright/strategy-comparison-leaderboard.png", fullPage: false });

  await page.getByTestId("sc-highlight-toggle").check();
  await expect(page.locator("[data-testid=sc-leaderboard] .sc-cell--hi").first()).toBeVisible();
  await expect(page.getByText(/best strategy/i)).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  const scroll = page.locator(".sc-leaderboard-scroll");
  await expect(scroll).toBeVisible();
  const overflow = await scroll.evaluate((el) => (el as HTMLElement).scrollWidth > (el as HTMLElement).clientWidth);
  expect(overflow).toBe(true);
});
