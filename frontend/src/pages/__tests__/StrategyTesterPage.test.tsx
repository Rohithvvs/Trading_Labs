import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

vi.mock("../../api_strategy_tester", () => ({
  fetchStrategyCatalog: vi.fn(async () => ({
    universe_count: 755,
    universe_label: "All Stocks (755)",
    universe_symbols: [
      { symbol: "360ONE", company: "360 One Wam Limited" },
      { symbol: "RELIANCE", company: "Reliance Industries Ltd." },
    ],
    operators: [{ code: ">", label: ">" }],
    fields: [{ code: "CLOSE", label: "Close", group: "price" }],
    presets: [
      {
        preset_id: "momentum",
        name: "Momentum Strategy",
        description: "Momentum based strategy using trend, momentum and volume filters.",
        filters: [
          { id: "close_sma50", field: "close", operator: ">", value: { indicator: "SMA", period: 50 } },
          { id: "sma50_sma200", field: "SMA_50", operator: ">", value: { indicator: "SMA", period: 200 } },
          { id: "rsi_55", field: "RSI", operator: ">", value: 55 },
          { id: "vol_avg", field: "volume", operator: ">", value: { indicator: "AVG_VOLUME", period: 20 } },
        ],
      },
    ],
    sides: ["LONG", "SHORT"],
  })),
  fetchStrategyHistory: vi.fn(async () => ({
    runs: [
      {
        id: "run-1",
        run_id: "STR-20260826-001",
        strategy: "Momentum Strategy",
        strategy_name: "Momentum Strategy",
        run_date: "2026-08-26T05:00:00Z",
        started_at: "2026-08-26T05:00:00Z",
        completed_at: "2026-08-26T05:04:12Z",
        duration_seconds: 252,
        status: "completed",
        stocks: 755,
        universe_size: 755,
        evaluated: 755,
        buy: 42,
        watch: 183,
        reject: 530,
        top_return: 35.1,
        worst_return: -30.06,
        positive_returns: 318,
        negative_returns: 437,
        average_return: -1.42,
      },
    ],
  })),
  fetchSavedStrategies: vi.fn(async () => ({ strategies: [] })),
  saveStrategyDefinition: vi.fn(async () => ({ id: "s1", name: "saved", version: 1 })),
  updateStrategyDefinition: vi.fn(async (id: string) => ({ id, name: "saved", version: 2 })),
  startStrategyTest: vi.fn(async () => ({ run_id: "STR-20260826-002", status: "queued" })),
  fetchStrategyRun: vi.fn(async (runId: string) => ({
    run_id: runId || "STR-20260826-001",
    status: "completed",
    stage: "done",
    strategy_name: "Momentum Strategy",
    started_at: "2026-08-26T05:00:00Z",
    completed_at: "2026-08-26T05:04:12Z",
    duration_seconds: 252,
    progress: { processed_stocks: 755, total_stocks: 755, percent: 100 },
    summary: {
      stocks_scanned: 755,
      evaluated: 755,
      buy: 42,
      watch: 183,
      reject: 530,
      positive_returns: 318,
      negative_returns: 437,
      average_return: -1.42,
      top_positive: [
        { rank: 1, symbol: "KALYANKJIL", entry_price: 78.20, exit_price: 105.65, return_pct: 35.10, signal: "BUY", key_filters: ["SMA50", "RSI", "Vol"] },
      ],
      top_negative: [
        { rank: 1, symbol: "IDEA", entry_price: 15.80, exit_price: 11.05, return_pct: -30.06, signal: "REJECT", key_filters: ["RSI", "SMA50", "Vol"] },
      ],
    },
  })),
  fetchStrategyResults: vi.fn(async () => ({
    total: 755,
    page: 1,
    page_size: 25,
    results: [
      {
        rank: 1,
        symbol: "RELIANCE",
        company: "Reliance Industries Ltd.",
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
        pass_count: 4,
        fail_count: 0,
        primary_failure: "None",
      },
    ],
  })),
  fetchStrategyResultDetail: vi.fn(async () => ({
    rank: 1,
    symbol: "RELIANCE",
    company: "Reliance Industries Ltd.",
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
    pass_count: 4,
    fail_count: 0,
    primary_failure: "None",
    filter_results: [
      { name: "Close > SMA 50", passed: true },
      { name: "SMA 50 > SMA 200", passed: true },
      { name: "RSI > 55", passed: true },
      { name: "Volume > Avg Volume", passed: true },
    ],
  })),
  fetchFilterAnalytics: vi.fn(async () => ({
    independent: [
      { filter_id: "1", label: "Close > SMA 50", passed: 420, failed: 335, pass_pct: 55.6, fail_pct: 44.4 },
      { filter_id: "2", label: "SMA 50 > SMA 200", passed: 310, failed: 445, pass_pct: 41.1, fail_pct: 58.9 },
      { filter_id: "3", label: "RSI > 55", passed: 280, failed: 475, pass_pct: 37.1, fail_pct: 62.9 },
      { filter_id: "4", label: "Volume > Avg Volume", passed: 195, failed: 560, pass_pct: 25.8, fail_pct: 74.2 },
    ],
    funnel: [
      { step: 0, label: "Start Universe", remaining: 755, drop: 0, retention_pct: 100 },
      { step: 1, label: "Close > SMA 50", remaining: 620, drop: 135, retention_pct: 82.1 },
      { step: 2, label: "SMA 50 > SMA 200", remaining: 410, drop: 210, retention_pct: 54.3 },
      { step: 3, label: "RSI > 55", remaining: 285, drop: 125, retention_pct: 37.7 },
      { step: 4, label: "Volume > Avg Volume", remaining: 195, drop: 90, retention_pct: 25.8 },
      { step: 5, label: "Final BUY Signals", remaining: 42, drop: 153, retention_pct: 5.6 },
    ],
  })),
  fetchStrategyResultCandles: vi.fn(async () => ({
    symbol: "RELIANCE",
    start_date: "2024-01-01",
    end_date: "2026-08-26",
    candles: [
      { date: "2026-08-25", open: 1410, high: 1430, low: 1405, close: 1420, volume: 8200000, sma_20: 1395, sma_50: 1350, sma_200: 1240, rsi: 64.2 },
      { date: "2026-08-26", open: 1420, high: 1635, low: 1415, close: 1630, volume: 9200000, sma_20: 1410, sma_50: 1360, sma_200: 1245, rsi: 72.5 },
    ],
  })),
  fetchStrategyResultHistory: vi.fn(async () => ({
    symbol: "RELIANCE",
    history: [
      { run_id: "STR-20260826-001", strategy_name: "Momentum Strategy", date: "2026-08-26T05:00:00Z", signal: "BUY", entry_price: 1420, exit_price: 1630, return_pct: 14.82, status: "completed" },
    ],
  })),
  cancelStrategyRun: vi.fn(),
  exportStrategyRun: vi.fn(),
}));

vi.mock("../../api_indicator_scanner", () => ({
  fetchIndicators: vi.fn(async () => []),
  fetchIndicatorTemplates: vi.fn(async () => []),
  validateIndicatorSource: vi.fn(),
  createIndicator: vi.fn(),
  updateIndicator: vi.fn(),
  duplicateIndicator: vi.fn(),
  archiveIndicator: vi.fn(),
  startIndicatorScan: vi.fn(),
  fetchIndicatorScan: vi.fn(),
  fetchIndicatorScanResults: vi.fn(),
  fetchIndicatorScanResult: vi.fn(),
  fetchIndicatorScanDiagnostics: vi.fn(),
  fetchLatestIndicatorScan: vi.fn(async () => null),
  exportIndicatorScanCsv: vi.fn(),
  cancelIndicatorScan: vi.fn(),
}));

vi.mock("../../design-system", async () => {
  const actual = await vi.importActual<typeof import("../../design-system")>("../../design-system");
  return {
    ...actual,
    useToast: () => ({
      pushToast: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      toast: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
      loading: vi.fn(),
      dismiss: vi.fn(),
      dismissAll: vi.fn(),
      toasts: [],
    }),
  };
});

import {
  fetchSavedStrategies,
  saveStrategyDefinition,
  updateStrategyDefinition,
} from "../../api_strategy_tester";
import { StrategyTesterPage } from "../StrategyTesterPage";

describe("StrategyTesterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    vi.mocked(fetchSavedStrategies).mockResolvedValue({ strategies: [] } as never);
    vi.mocked(saveStrategyDefinition).mockResolvedValue({ id: "s1", name: "saved", version: 1 });
    vi.mocked(updateStrategyDefinition).mockImplementation(async (id: string) => ({
      id,
      name: "saved",
      version: 2,
    }));
  });

  it("renders Strategy Tester header, top action buttons, and config panel", async () => {
    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("strategy-tester-page")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Strategy Tester" })).toBeTruthy();
    expect(
      screen.getByText(/Test trading strategies across the complete stock universe/i),
    ).toBeTruthy();

    // Top buttons
    expect(screen.getByTestId("btn-import-strategy")).toBeTruthy();
    expect(screen.getByTestId("btn-save-strategy")).toBeTruthy();
    expect(screen.getByTestId("btn-new-strategy")).toBeTruthy();

    // Configuration controls
    expect(screen.getByTestId("select-strategy-preset")).toBeTruthy();
    expect(screen.getAllByText("All Stocks (755)").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("1 Day").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId("input-start-date")).toBeTruthy();
    expect(screen.getByTestId("input-end-date")).toBeTruthy();
    expect(screen.getByTestId("input-initial-capital")).toBeTruthy();
    expect(screen.getByTestId("btn-run-strategy")).toBeTruthy();
    expect(screen.getByTestId("btn-reset-strategy")).toBeTruthy();
    expect(screen.getByText(/Momentum based strategy using trend, momentum and volume filters/i)).toBeTruthy();
  });

  it("renders 3 run status and summary cards", async () => {
    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("card-run-info")).toBeTruthy();
    expect(screen.getByTestId("card-scan-progress")).toBeTruthy();
    expect(screen.getByTestId("card-run-summary")).toBeTruthy();

    expect(screen.getByText("Scan Progress")).toBeTruthy();
    expect(screen.getByText("Run Summary")).toBeTruthy();
    expect(screen.getByText(/Stocks Scanned:/i)).toBeTruthy();
    expect(screen.getByText(/BUY Signals:/i)).toBeTruthy();
    expect(screen.getByText(/WATCH Signals:/i)).toBeTruthy();
    expect(screen.getByText(/REJECT Signals:/i)).toBeTruthy();
    expect(screen.getByText(/Positive Returns:/i)).toBeTruthy();
    expect(screen.getByText(/Negative Returns:/i)).toBeTruthy();
  });

  it("renders upper analytics grid with Strategy Builder on left and stacked Top 5 returns on right", async () => {
    const { container } = render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("card-strategy-builder")).toBeTruthy();
    expect(screen.getByTestId("card-top-positive")).toBeTruthy();
    expect(screen.getByTestId("card-top-negative")).toBeTruthy();

    const upperGrid = container.querySelector(".st-upper-analytics-grid");
    expect(upperGrid).toBeTruthy();
    const builderCol = container.querySelector(".st-builder-col");
    const topReturnsCol = container.querySelector(".st-top-returns-col");
    expect(builderCol).toBeTruthy();
    expect(topReturnsCol).toBeTruthy();

    // Verify Strategy Builder is inside builderCol
    expect(builderCol?.querySelector("[data-testid='card-strategy-builder']")).toBeTruthy();
    // Verify Top 5 Positive and Negative are inside topReturnsCol (vertically stacked)
    expect(topReturnsCol?.querySelector("[data-testid='card-top-positive']")).toBeTruthy();
    expect(topReturnsCol?.querySelector("[data-testid='card-top-negative']")).toBeTruthy();

    // Strategy Builder contents
    expect(screen.getAllByText("Close > SMA 50").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("SMA 50 > SMA 200").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("RSI > 55").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Volume > Avg Volume").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("LONG ONLY")).toBeTruthy();
  });

  it("renders lower analytics grid with 3 columns: Filter Analytics, Filter Funnel, Signal Distribution", async () => {
    const { container } = render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("card-filter-analytics")).toBeTruthy();
    expect(screen.getByTestId("card-filter-funnel")).toBeTruthy();
    expect(screen.getByTestId("card-signal-distribution")).toBeTruthy();

    const lowerGrid = container.querySelector(".st-lower-analytics-grid");
    expect(lowerGrid).toBeTruthy();

    // Verify Filter Funnel has sequential stages
    expect(screen.getByText("Start Universe")).toBeTruthy();
    expect(screen.getByText("Final BUY Signals")).toBeTruthy();

    // Verify Signal Distribution legend follows BUY -> WATCH -> REJECT order
    const signalDistCard = screen.getByTestId("card-signal-distribution");
    expect(signalDistCard).toBeTruthy();
    const legendItems = signalDistCard.querySelectorAll(".st-donut-legend-item");
    expect(legendItems.length).toBeGreaterThanOrEqual(3);
    expect(legendItems[0].textContent).toContain("BUY");
    expect(legendItems[1].textContent).toContain("WATCH");
    expect(legendItems[2].textContent).toContain("REJECT");
  });

  it("renders All Stock Results with Quick Access Signal pills and Left-aligned toolbar", async () => {
    const { container } = render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("table-strategy-results")).toBeTruthy();

    // Quick Access Signal Selector pills
    expect(screen.getByTestId("pill-filter-buy")).toBeTruthy();
    expect(screen.getByTestId("pill-filter-watch")).toBeTruthy();
    expect(screen.getByTestId("pill-filter-reject")).toBeTruthy();
    expect(screen.getByTestId("pill-filter-failed")).toBeTruthy();

    expect(screen.getByTestId("pill-filter-buy").textContent).toContain("BUY");
    expect(screen.getByTestId("pill-filter-buy").textContent).toContain("42");
    expect(screen.getByTestId("pill-filter-watch").textContent).toContain("WATCH");
    expect(screen.getByTestId("pill-filter-watch").textContent).toContain("183");
    expect(screen.getByTestId("pill-filter-reject").textContent).toContain("REJECT");
    expect(screen.getByTestId("pill-filter-reject").textContent).toContain("530");

    // Left-aligned toolbar container
    const toolbar = container.querySelector(".st-results-toolbar");
    expect(toolbar).toBeTruthy();

    // Left toolbar controls
    expect(screen.getByTestId("input-search-stocks")).toBeTruthy();
    expect(screen.getByTestId("select-signal-filter")).toBeTruthy();
    expect(screen.getByTestId("select-return-filter")).toBeTruthy();
    expect(screen.getByTestId("btn-columns-modal")).toBeTruthy();
    expect(screen.getByTestId("btn-export-csv")).toBeTruthy();

    // Select options strict ordering: All Signals -> BUY -> WATCH -> REJECT -> FAILED
    const signalSelect = screen.getByTestId("select-signal-filter") as HTMLSelectElement;
    const options = Array.from(signalSelect.options).map((o) => o.value);
    expect(options).toEqual(["ALL", "BUY", "WATCH", "REJECT", "FAILED"]);

    // Clicking BUY quick pill toggles signal filter
    fireEvent.click(screen.getByTestId("pill-filter-buy"));
    expect(signalSelect.value).toBe("BUY");
  });

  it("navigates to dedicated /stock/:symbol page and does not render side drawer", async () => {
    mockNavigate.mockClear();
    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    // Ensure the old docked right-side stock detail drawer is NOT rendered on Strategy Tester
    expect(screen.queryByTestId("tab-detail-overview")).toBeNull();
    expect(screen.queryByTestId("tab-detail-chart")).toBeNull();
    expect(screen.queryByTestId("tab-detail-history")).toBeNull();

    // Click stock in All Stock Results table -> navigates to /stock/RELIANCE
    const relianceRow = await screen.findByTestId("row-stock-RELIANCE");
    fireEvent.click(relianceRow);
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.stringMatching(/\/stock\/RELIANCE/),
      expect.objectContaining({
        state: expect.objectContaining({
          symbol: "RELIANCE",
          returnTo: "/strategy-tester",
        }),
      }),
    );

    // Click stock in Top 5 Positive Returns -> navigates to /stock/KALYANKJIL
    const kalyanRow = await screen.findByTestId("row-top-positive-KALYANKJIL");
    fireEvent.click(kalyanRow);
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.stringMatching(/\/stock\/KALYANKJIL/),
      expect.anything(),
    );

    // Click stock in Top 5 Negative Returns -> navigates to /stock/IDEA
    const ideaRow = await screen.findByTestId("row-top-negative-IDEA");
    fireEvent.click(ideaRow);
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.stringMatching(/\/stock\/IDEA/),
      expect.anything(),
    );
  });

  it("opens and closes Import, Save, Builder and Columns modals", async () => {
    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    // Import modal
    fireEvent.click(await screen.findByTestId("btn-import-strategy"));
    expect(screen.getByTestId("modal-import-strategy")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Cancel" })[0]);

    // Save modal
    fireEvent.click(screen.getByTestId("btn-save-strategy"));
    expect(screen.getByTestId("modal-save-strategy")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Cancel" })[0]);

    // New Strategy / Builder modal
    fireEvent.click(screen.getByTestId("btn-new-strategy"));
    expect(screen.getByTestId("modal-strategy-builder")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Cancel" })[0]);

    // Columns modal
    fireEvent.click(screen.getByTestId("btn-columns-modal"));
    expect(screen.getByTestId("modal-columns-config")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
  });

  it("Pine Script workflow: Observe Filters does NOT scan, Save & Apply automatically triggers scanner", async () => {
    const { startStrategyTest } = await import("../../api_strategy_tester");
    vi.mocked(startStrategyTest).mockClear();

    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    // 1. Open New Strategy
    fireEvent.click(await screen.findByTestId("btn-new-strategy"));
    expect(screen.getByTestId("modal-strategy-builder")).toBeTruthy();

    // 2. Switch to Pine Script tab
    fireEvent.click(screen.getByTestId("tab-pine-script"));
    expect(screen.getByTestId("pine-code-editor")).toBeTruthy();

    // 3. Paste Pine Script
    const pineCode = `//@version=6
strategy("52W Breakout", overlay=true)

sma50 = ta.sma(close, 50)
sma200 = ta.sma(close, 200)
rsi14 = ta.rsi(close, 14)
avgVol20 = ta.sma(volume, 20)
high52 = ta.highest(high, 252)

breakout = high > high52[1]

longCondition =
    breakout and
    close > sma50 and
    sma50 > sma200 and
    rsi14 > 55 and
    volume > avgVol20

if longCondition
    strategy.entry("Long", strategy.long)
`;
    const textarea = screen.getByTestId("pine-textarea");
    fireEvent.change(textarea, { target: { value: pineCode } });

    // 4. Click Observe Filters
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    // CRITICAL: Observe Filters must NOT trigger scanner execution!
    expect(startStrategyTest).not.toHaveBeenCalled();

    // Strategy Builder tab is automatically shown with detected filters
    expect(screen.getByTestId("tab-strategy-builder").className).toContain("is-active");
    expect(screen.getByTestId("pine-import-summary")).toBeTruthy();
    expect((screen.getByTestId("input-strategy-name") as HTMLInputElement).value).toBe("52W Breakout");

    // 5. User reviews/modifies and manually clicks Save & Apply
    fireEvent.click(screen.getByTestId("btn-apply-strategy-builder"));

    // Modal closes
    expect(screen.queryByTestId("modal-strategy-builder")).toBeNull();

    // Scanner automatically starts with the new strategy configuration without requiring a second click
    await waitFor(() => expect(startStrategyTest).toHaveBeenCalledTimes(1));
    const [payload] = vi.mocked(startStrategyTest).mock.calls[0];
    expect(payload.name).toBe("52W Breakout");
    expect(payload.side).toBe("LONG");
    expect(payload.filters?.length).toBe(5);
  });

  it("Canonical 52-Week Breakout Pine Script workflow: separates risk/ranking and executes scanner on Save & Apply", async () => {
    const { startStrategyTest } = await import("../../api_strategy_tester");
    vi.mocked(startStrategyTest).mockClear();

    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    // 1. Open New Strategy -> Pine Script Tab
    fireEvent.click(await screen.findByTestId("btn-new-strategy"));
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    // 2. Load template (which is Canonical 52-Week High Breakout)
    const templateBtn = screen.getByRole("button", { name: "Template" });
    fireEvent.click(templateBtn);

    // 3. Click Observe Filters
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    // Observe Filters does NOT trigger scanner
    expect(startStrategyTest).not.toHaveBeenCalled();

    // Summary banner shows 3 entry filters and details
    expect(screen.getByTestId("pine-import-summary")).toBeTruthy();
    expect(screen.getByTestId("pine-import-summary").textContent).toContain("3 entry filters detected");
    expect(screen.getByTestId("pine-import-summary").textContent).toContain("NIFTY 500");
    expect(screen.getByTestId("pine-import-summary").textContent).toContain("Trailing Stop");

    // 4. Click Save & Apply -> Automatically starts scanner with exactly 3 entry filters
    fireEvent.click(screen.getByTestId("btn-apply-strategy-builder"));

    await waitFor(() => expect(startStrategyTest).toHaveBeenCalledTimes(1));
    const [payload] = vi.mocked(startStrategyTest).mock.calls[0];
    expect(payload.name).toBe("52-Week High Breakout");
    expect(payload.side).toBe("LONG");
    expect(payload.filters?.length).toBe(3);
    expect(payload.source?.type).toBe("pine");
  });

  it("deduplicates repeated strategies in the Strategy Tester dropdown like Indicator Scanner", async () => {
    const { fetchSavedStrategies } = await import("../../api_strategy_tester");
    vi.mocked(fetchSavedStrategies).mockResolvedValue([
      { id: "s-old", name: "Momentum Strategy", updated_at: "2026-01-01T00:00:00Z" },
      { id: "s-new", name: "Momentum Strategy", updated_at: "2026-08-01T00:00:00Z" },
      { id: "s-custom", name: "My Custom", updated_at: "2026-08-02T00:00:00Z" },
      { id: "s-custom-2", name: "My Custom", updated_at: "2026-07-01T00:00:00Z" },
    ] as never);

    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    const select = (await screen.findByTestId("select-strategy-preset")) as HTMLSelectElement;
    await waitFor(() => {
      const labels = [...select.options].map((opt) => opt.text);
      expect(labels).toEqual(["Momentum Strategy", "My Custom"]);
    });
    expect(select.options).toHaveLength(2);
    expect([...select.options].map((opt) => opt.value).sort()).toEqual(["s-custom", "s-new"]);
  });

  it("updates an existing same-name strategy instead of creating a duplicate", async () => {
    const { fetchSavedStrategies, saveStrategyDefinition, updateStrategyDefinition } = await import(
      "../../api_strategy_tester"
    );
    vi.mocked(fetchSavedStrategies).mockResolvedValue([
      { id: "s-existing", name: "Momentum Strategy", updated_at: "2026-08-01T00:00:00Z" },
    ] as never);
    vi.mocked(updateStrategyDefinition).mockResolvedValue({
      id: "s-existing",
      name: "Momentum Strategy",
      version: 2,
    });

    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      const select = screen.getByTestId("select-strategy-preset") as HTMLSelectElement;
      expect([...select.options].map((opt) => opt.value)).toContain("s-existing");
    });
    fireEvent.click(screen.getByTestId("btn-save-strategy"));
    fireEvent.click(screen.getByTestId("btn-confirm-save"));

    await waitFor(() => expect(updateStrategyDefinition).toHaveBeenCalled());
    expect(saveStrategyDefinition).not.toHaveBeenCalled();
    expect(vi.mocked(updateStrategyDefinition).mock.calls[0][0]).toBe("s-existing");
  });

  it("opens the Indicator Scanner workspace and Add Indicator tab", async () => {
    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByTestId("workspace-indicator"));
    expect(screen.getByTestId("indicator-screener")).toBeTruthy();
    expect(screen.getByTestId("select-indicator-universe").textContent).toContain("755 Stocks");
    expect(screen.queryByTestId("btn-import-strategy")).toBeNull();
    expect(screen.queryByTestId("btn-save-strategy")).toBeNull();
    expect(screen.getByTestId("btn-new-strategy").textContent).toMatch(/New Indicator/);
    await waitFor(() => {
      const headerActions = screen.getByTestId("btn-new-strategy").closest(".st-header-actions");
      expect(headerActions?.querySelector('[data-testid="btn-scan-indicator"]')).toBeTruthy();
    });
    expect(screen.getByTestId("indicator-empty-library")).toBeTruthy();
    fireEvent.click(screen.getByTestId("btn-add-indicator"));
    expect(screen.getByTestId("tab-indicator").className).toContain("is-active");
    expect(screen.getByTestId("indicator-editor-panel")).toBeTruthy();
    expect(screen.getByTestId("indicator-results-table")).toBeTruthy();
    expect(screen.getByTestId("indicator-row-360ONE")).toBeTruthy();
  });

  it("restores Indicator Scanner workspace from saved page state", async () => {
    sessionStorage.setItem(
      "strategy_tester_state_v1",
      JSON.stringify({
        workspace: "indicator",
        appliedIndicator: {
          id: "ind-1",
          name: "52-Week High Breakout [SCAN]",
          description: "",
          source_code: "indicator()",
          script_version: 6,
          language_mode: "pine_subset_v1",
          timeframe: "1D",
          validation_status: "valid",
          required_bars: 253,
        },
      }),
    );
    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("indicator-screener")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Indicator Scanner" })).toBeTruthy();
  });

  it("opens the Indicator tab from New Strategy while in Indicator Scanner", async () => {
    render(
      <MemoryRouter>
        <StrategyTesterPage />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByTestId("workspace-indicator"));
    fireEvent.click(screen.getByTestId("btn-new-strategy"));
    expect(screen.getByTestId("tab-indicator").className).toContain("is-active");
    expect(screen.getByTestId("indicator-editor-panel")).toBeTruthy();
  });
});
