import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StockDetailsPage } from "../StockDetailsPage";

// Mock ResizeObserver for Recharts
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockCupidDetail = {
  rank: 1,
  symbol: "CUPID",
  company: "Cupid Ltd.",
  status: "completed",
  signal: "WATCH",
  entry_price: 11.68,
  exit_price: 281.76,
  return_pct: 2312.33,
  rsi: 64.2,
  sma_20: 1395.2,
  sma_50: 1350.4,
  sma_200: 1240.15,
  volume: 8200000,
  avg_volume: 5100000,
  indicators: {
    ema_20: 1380.0,
    ema_50: 1340.0,
    macd: 12.4,
    macd_signal: 10.1,
    atr_14: 15.2,
  },
  filters_passed: 2,
  filters_failed: 2,
  filter_results: [
    { name: "Close > SMA 50", passed: true },
    { name: "SMA 50 > SMA 200", passed: true },
    { name: "RSI 14 > SMA 20", passed: false },
    { name: "Volume > Average Volume 20", passed: false },
  ],
};

const mockGvtdDetail = {
  rank: 1,
  symbol: "GVTD",
  company: "GE Vernova T&D India Ltd.",
  status: "completed",
  signal: "BUY",
  entry_price: 528.5,
  exit_price: 4185.0,
  return_pct: 691.86,
  rsi: 45.5,
  sma_20: 4282.48,
  sma_50: 4479.7,
  sma_200: 3937.52,
  volume: 868900,
  avg_volume: 761500,
  indicators: {
    ema_20: 4310.2,
    ema_50: 4390.5,
    macd: 25.6,
    macd_signal: 22.1,
    atr_14: 124.5,
  },
  filters_passed: 3,
  filters_failed: 0,
  filter_results: [
    { name: "NIFTY 500 Close > NIFTY 500 SMA 50", passed: true },
    { name: "Close >= Prior 252-Session High", passed: true },
    { name: "Volume > Average Volume 20", passed: true },
  ],
};

const mockCandles = [
  {
    date: "2026-08-20",
    open: 11.0,
    high: 12.5,
    low: 10.8,
    close: 11.68,
    volume: 5000000,
    sma_20: 11.2,
    sma_50: 10.5,
    sma_200: 9.8,
    rsi: 64.2,
  },
  {
    date: "2026-08-26",
    open: 270.0,
    high: 285.0,
    low: 268.0,
    close: 281.76,
    volume: 8200000,
    sma_20: 250.0,
    sma_50: 220.0,
    sma_200: 180.0,
    rsi: 72.5,
  },
];

const mockHistory = [
  {
    run_id: "STR-20260826-001",
    strategy_name: "52-Week High Breakout",
    date: "2026-08-26T05:00:00Z",
    signal: "WATCH",
    entry_price: 11.68,
    exit_price: 281.76,
    return_pct: 2312.33,
    status: "completed",
  },
];

vi.mock("../../api_strategy_tester", () => ({
  fetchStrategyHistory: vi.fn(async () => ({
    runs: [{ run_id: "STR-20260826-001", strategy_name: "52-Week High Breakout" }],
  })),
  fetchStrategyRun: vi.fn(async (runId: string) => ({
    id: runId,
    run_id: runId,
    strategy_name: "52-Week High Breakout",
    start_date: "2024-01-01",
    end_date: "2026-08-26",
    initial_capital: 1000000,
    timeframe: "1 Day",
    universe: "NIFTY 500",
    universe_size: 755,
    status: "completed",
    progress_pct: 100,
    processed_count: 755,
    total_count: 755,
    buy: 42,
    watch: 183,
    reject: 530,
    strategy_snapshot: {
      position_rules: {
        side: "LONG",
        exit_rule: "Close < Trailing Stop",
        return_method: "Close < Trailing Stop",
      },
    },
  })),
  fetchStrategyResultDetail: vi.fn(async (runId: string, symbol: string) => {
    if (symbol.toUpperCase() === "CUPID") return mockCupidDetail;
    if (symbol.toUpperCase() === "GVTD" || symbol.toUpperCase() === "GVT&D") return mockGvtdDetail;
    if (symbol.toUpperCase() === "RELIANCE") {
      return {
        rank: 2,
        symbol: "RELIANCE",
        company: "Reliance Industries Ltd.",
        status: "completed",
        signal: "BUY",
        entry_price: 1420.0,
        exit_price: 1630.0,
        return_pct: 14.82,
        rsi: 64.2,
        sma_20: 1395.2,
        sma_50: 1350.4,
        sma_200: 1240.15,
        volume: 8200000,
        avg_volume: 5100000,
        filters_passed: 4,
        filters_failed: 0,
        filter_results: [
          { name: "Close > SMA 50", passed: true },
          { name: "SMA 50 > SMA 200", passed: true },
          { name: "RSI > 55", passed: true },
          { name: "Volume > Avg Volume", passed: true },
        ],
      };
    }
    if (symbol.toUpperCase() === "UNKNOWN_STOCK") {
      const err = new Error("Symbol not in this run");
      (err as any).status = 404;
      throw err;
    }
    if (symbol.toUpperCase() === "NETWORK_ERROR") {
      throw new Error("Connection failed");
    }
    return {
      rank: 99,
      symbol,
      company: `${symbol} Ltd.`,
      status: "completed",
      signal: "WATCH",
      entry_price: 100.0,
      exit_price: 110.0,
      return_pct: 10.0,
    };
  }),
  fetchStrategyResultCandles: vi.fn(async () => ({
    symbol: "CUPID",
    candles: mockCandles,
  })),
  fetchStrategyResultHistory: vi.fn(async () => ({
    symbol: "CUPID",
    history: mockHistory,
  })),
}));

vi.mock("../../api", () => ({
  fetchSymbolDetail: vi.fn(async (symbol: string) => {
    if (symbol.toUpperCase() === "GVTD" || symbol.toUpperCase() === "GVT&D") {
      return {
        symbol: "GVTD",
        company_name: "GE Vernova T&D India Ltd.",
        sector: "Capital Goods",
        industry: "Heavy Electrical Equipment",
        market_cap: 35000000000,
        company_description: "GE Vernova T&D India is a leading player in power transmission.",
        year52_high: 4500.0,
        year52_low: 520.0,
        technical_extras: {
          atr: 124.5,
          bollinger_status: "Upper Band Touch",
          bollinger_position: "upper",
        },
        backtest_extras: {
          max_drawdown: 18.5,
          profit_factor: 3.42,
        },
        news_articles: [
          {
            title: "GE Vernova T&D bags major power transmission contract",
            description: "GE Vernova T&D India has received orders worth INR 500 Cr.",
            source: "Economic Times",
            published_at: "2026-08-25T10:00:00Z",
            url: "https://example.com/news/1",
          },
        ],
        news_sentiment_label: "positive",
        news_sentiment_score: 0.85,
        news_summary: "Strong order book growth driving bullish sentiment.",
      };
    }
    return {
      symbol: symbol.toUpperCase(),
      company_name: `${symbol} Ltd.`,
      sector: "Healthcare",
      industry: "Personal Care",
      market_cap: 10000000000,
      company_description: "Leading manufacturer of personal care products.",
      year52_high: 300.0,
      year52_low: 10.0,
      technical_extras: {
        atr: 15.2,
      },
      news_articles: [],
    };
  }),
  fetchW52SymbolDetail: vi.fn(async () => null),
  fetchLtmSymbolDetail: vi.fn(async () => null),
}));

describe("StockDetailsPage", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it("renders dedicated Stock Details page with header, metrics, and Overview tab content for CUPID", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/CUPID"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    // Header & identity
    const symbolEl = await screen.findByTestId("stock-details-symbol");
    expect(symbolEl.textContent).toBe("CUPID");
    expect(screen.getByTestId("stock-details-company").textContent).toBe("Cupid Ltd.");

    // Back to Strategy Tester button
    expect(screen.getByTestId("btn-back-to-strategy-tester").textContent).toContain("Back to Strategy Tester");

    // Metrics banner
    expect(screen.getByTestId("stock-detail-signal").textContent).toBe("WATCH");
    expect(screen.getByTestId("stock-detail-return").textContent).toBe("+2312.33%");
    expect(screen.getByTestId("stock-detail-entry-price").textContent).toBe("₹11.68");
    expect(screen.getByTestId("stock-detail-exit-price").textContent).toBe("₹281.76");

    // Exact 6 tabs in exact order
    expect(screen.getByTestId("tab-detail-overview").textContent).toBe("Overview");
    expect(screen.getByTestId("tab-detail-chart").textContent).toBe("Chart");
    expect(screen.getByTestId("tab-detail-history").textContent).toBe("History");
    expect(screen.getByTestId("tab-detail-news").textContent).toBe("News");
    expect(screen.getByTestId("tab-detail-backtest").textContent).toBe("Backtest");
    expect(screen.getByTestId("tab-detail-research").textContent).toBe("Research");
    expect(screen.queryByTestId("tab-detail-technicals")).toBeNull();
    expect(screen.queryByTestId("tab-detail-trade-plan")).toBeNull();

    // Trade Plan embedded in Overview
    expect(screen.getByTestId("card-detail-tradeplan")).toBeTruthy();
    expect(screen.getByTestId("card-detail-tradeplan-overview")).toBeTruthy();
    expect(screen.getByTestId("card-detail-tradeplan-risk")).toBeTruthy();
    expect(screen.getByTestId("card-detail-tradeplan-conditions")).toBeTruthy();
    expect(screen.getByTestId("card-detail-tradeplan-exit")).toBeTruthy();
    expect(screen.getByTestId("tradeplan-signal").textContent).toBe("WATCH");
    expect(screen.getByText("STR-20260826-001")).toBeTruthy();
    expect(screen.getByText("Close > SMA 50")).toBeTruthy();
    expect(screen.getByText("SMA 50 > SMA 200")).toBeTruthy();
    expect(screen.getByText("RSI 14 > SMA 20")).toBeTruthy();
    expect(screen.getByText("Volume > Average Volume 20")).toBeTruthy();
    expect(screen.getAllByText("✓ Passed").length).toBe(2);
    expect(screen.getAllByText("✕ Failed").length).toBe(2);
    expect(screen.getByText("((Exit - Entry) / Entry) × 100")).toBeTruthy();

    // Technicals embedded in Overview
    expect(screen.getByTestId("card-detail-technicals")).toBeTruthy();
    expect(screen.getByTestId("card-detail-technicals-key")).toBeTruthy();
    expect(screen.getByTestId("card-detail-technicals-ma")).toBeTruthy();
    expect(screen.getByTestId("card-detail-technicals-momentum")).toBeTruthy();
    expect(screen.getByTestId("card-detail-technicals-volume")).toBeTruthy();
    expect(screen.getByText("EMA 20")).toBeTruthy();
    expect(screen.getByText("EMA 50")).toBeTruthy();
    expect(screen.getByText("SMA 20")).toBeTruthy();
    expect(screen.getByText("SMA 50")).toBeTruthy();
    expect(screen.getByText("SMA 200")).toBeTruthy();
    expect(screen.getByText("RSI (14)")).toBeTruthy();
    expect(screen.getByText("MACD")).toBeTruthy();
    expect(screen.getByText("MACD Signal")).toBeTruthy();
    expect(screen.getByText("ATR")).toBeTruthy();
  });

  it("switches to Chart tab and renders chart view", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/CUPID"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const symbolEl = await screen.findByTestId("stock-details-symbol");
    expect(symbolEl.textContent).toBe("CUPID");

    // Switch to Chart tab
    fireEvent.click(screen.getByTestId("tab-detail-chart"));
    expect(await screen.findByTestId("card-detail-chart")).toBeTruthy();
    expect(screen.getByText("Price & Indicator Chart")).toBeTruthy();
    expect(screen.getByText("SMA 20")).toBeTruthy();
    expect(screen.getByText("SMA 50")).toBeTruthy();
    expect(screen.getByText("SMA 200")).toBeTruthy();
  });

  it("switches to History tab and renders past runs table", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/CUPID"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const symbolEl = await screen.findByTestId("stock-details-symbol");
    expect(symbolEl.textContent).toBe("CUPID");

    // Switch to History tab
    fireEvent.click(screen.getByTestId("tab-detail-history"));
    expect(await screen.findByTestId("card-detail-history")).toBeTruthy();
    expect(screen.getByText("Test Run History")).toBeTruthy();
    expect(await screen.findByTestId("table-stock-history")).toBeTruthy();
  });

  it("displays technical indicators in Overview tab", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/CUPID"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("stock-details-symbol");

    expect(await screen.findByTestId("card-detail-technicals")).toBeTruthy();
    expect(screen.getByTestId("card-detail-technicals-key")).toBeTruthy();
    expect(screen.getByTestId("card-detail-technicals-ma")).toBeTruthy();
    expect(screen.getByTestId("card-detail-technicals-momentum")).toBeTruthy();
    expect(screen.getByTestId("card-detail-technicals-volume")).toBeTruthy();

    // Check specific technical indicator labels
    expect(screen.getAllByText("EMA 20").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("EMA 50").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("MACD").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("MACD Signal").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ATR").length).toBeGreaterThanOrEqual(1);
  });

  it("displays trading plan in Overview tab for selected stock", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/GVTD"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("stock-details-symbol");

    expect(await screen.findByTestId("card-detail-tradeplan")).toBeTruthy();
    expect(screen.getByTestId("card-detail-tradeplan-overview")).toBeTruthy();
    expect(screen.getByTestId("card-detail-tradeplan-risk")).toBeTruthy();
    expect(screen.getByTestId("card-detail-tradeplan-conditions")).toBeTruthy();
    expect(screen.getByTestId("card-detail-tradeplan-exit")).toBeTruthy();

    expect(screen.getByTestId("tradeplan-signal").textContent).toBe("BUY");
    expect(screen.getAllByText("LONG").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("52-Week High Breakout").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Close < Trailing Stop").length).toBeGreaterThanOrEqual(1);
  });

  it("normalizes legacy tab=technicals or tab=tradeplan URL parameters to overview tab", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/GVTD?tab=technicals"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("stock-details-symbol");
    expect(screen.getByTestId("tab-detail-overview").classList.contains("is-active")).toBe(true);
    expect(await screen.findByTestId("card-detail-technicals")).toBeTruthy();
    expect(await screen.findByTestId("card-detail-tradeplan")).toBeTruthy();
  });

  it("switches to News tab and renders articles or empty state", async () => {
    // For GVTD with articles
    render(
      <MemoryRouter initialEntries={["/stock/GVTD"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("stock-details-symbol");
    fireEvent.click(screen.getByTestId("tab-detail-news"));
    expect(await screen.findByTestId("card-detail-news")).toBeTruthy();
    expect(await screen.findByText(/GE Vernova T&D bags major power transmission contract/)).toBeTruthy();
    expect(screen.getByText("Economic Times")).toBeTruthy();
  });

  it("renders empty state in News tab when stock has no articles", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/CUPID?tab=news"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("stock-details-symbol");
    expect(await screen.findByTestId("news-empty-state")).toBeTruthy();
    expect(screen.getByText("No recent news available for this stock.")).toBeTruthy();
  });

  it("switches to Backtest tab and displays stock-scoped backtest metrics", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/GVTD"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("stock-details-symbol");
    fireEvent.click(screen.getByTestId("tab-detail-backtest"));

    expect(await screen.findByTestId("card-detail-backtest")).toBeTruthy();
    expect(screen.getByTestId("card-detail-backtest-summary")).toBeTruthy();
    expect(screen.getByTestId("backtest-total-return").textContent).toBe("+691.86%");
    expect(screen.getByTestId("backtest-total-pnl")).toBeTruthy();
    expect(screen.getByTestId("backtest-total-trades")).toBeTruthy();
    expect(screen.getByTestId("backtest-win-rate")).toBeTruthy();
    expect(screen.getByTestId("backtest-max-drawdown")).toBeTruthy();
    expect(screen.getByTestId("table-backtest-trades")).toBeTruthy();
  });

  it("switches to Research tab and displays consolidated research for selected stock", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/GVTD"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("stock-details-symbol");
    fireEvent.click(screen.getByTestId("tab-detail-research"));

    expect(await screen.findByTestId("card-detail-research")).toBeTruthy();
    expect(screen.getByTestId("card-detail-research-company")).toBeTruthy();
    expect(screen.getByTestId("card-detail-research-market")).toBeTruthy();
    expect(screen.getByTestId("card-detail-research-technical")).toBeTruthy();
    expect(screen.getByTestId("card-detail-research-strategy")).toBeTruthy();
    expect(screen.getByTestId("card-detail-research-performance")).toBeTruthy();

    expect(screen.getByText("Capital Goods")).toBeTruthy();
    expect(screen.getByText("Heavy Electrical Equipment")).toBeTruthy();
  });

  it("handles back button click returning to Strategy Tester", async () => {
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: "/stock/CUPID",
            state: { returnTo: "/strategy-tester" },
          },
        ]}
      >
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const symbolEl = await screen.findByTestId("stock-details-symbol");
    expect(symbolEl.textContent).toBe("CUPID");
    fireEvent.click(screen.getByTestId("btn-back-to-strategy-tester"));
    expect(mockNavigate).toHaveBeenCalledWith("/strategy-tester");
  });

  it("displays 'Stock not found' when symbol does not exist", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/UNKNOWN_STOCK"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("stock-details-not-found")).toBeTruthy();
    expect(screen.getByText("Stock not found")).toBeTruthy();
    expect(screen.getByText(/UNKNOWN_STOCK/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Return to Strategy Tester" }));
    expect(mockNavigate).toHaveBeenCalled();
  });

  it("displays error state with retry button on network failure", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/NETWORK_ERROR"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("stock-details-error")).toBeTruthy();
    expect(screen.getByText("Unable to load stock details")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("correctly canonicalizes lowercase symbol /stock/cupid to CUPID", async () => {
    render(
      <MemoryRouter initialEntries={["/stock/cupid"]}>
        <Routes>
          <Route path="/stock/:symbol" element={<StockDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const symbolEl = await screen.findByTestId("stock-details-symbol");
    expect(symbolEl.textContent).toBe("CUPID");
  });
});
