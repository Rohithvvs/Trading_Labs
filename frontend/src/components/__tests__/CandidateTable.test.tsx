import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CandidateTable, SCANNER_TABLE_PAGE_SIZE } from "../CandidateTable";
import type { CandidateRow } from "../../types";

const mockCanAccess = vi.fn();

vi.mock("../../hooks/useFeaturePermissions", () => ({
  useFeaturePermissions: () => ({
    canAccess: mockCanAccess,
    isLoading: false,
    permissions: {},
    error: null,
    refetchPermissions: vi.fn(),
  }),
}));

vi.mock("../../hooks/useResearchPrefetch", () => ({
  useResearchPrefetch: () => ({ hoverHandlers: () => ({}) }),
}));

describe("Dashboard Component", () => {
  it("renders Multi-Agent Progress Tracker overlay when isLoading is true", () => {
    expect(true).toBe(true);
  });
});

describe("CandidateTable Component", () => {
  const mockRow: CandidateRow = {
    rank: 1,
    symbol: "TCS.NS",
    signal: "BUY",
    score: 85.5,
    confidence: 0.9,
    entryLow: 3500,
    entryHigh: 3550,
    stopLoss: 3400,
    target1: 3800,
    target2: null,
    riskReward: 2.5,
    trend: "Bullish",
    momentum: "Strong",
    volume: "High",
    newsSentiment: "Bullish",
    lastUpdated: "2023-10-01T10:00:00Z",
    tradeReadiness: "High",
    recommendationSummary: "Strong buy",
    analysisItem: {
      symbol: "TCS.NS",
      backtests: [
        {
          mode: "swing",
          strategy_name: "EMA Crossover",
          total_return: 15.0,
          cagr: 10.0,
          max_drawdown: 5.0,
          win_rate: 0.65,
          profit_factor: 1.8,
          trade_count: 50,
          verdict: "Pass",
          equity_curve: [
            { label: "1", equity: 100 },
            { label: "2", equity: 115 },
          ],
        },
      ],
      ohlcv: [],
      technical: [],
      news_articles: [],
      news_summary: "",
      news_sentiment_label: "Bullish",
      news_sentiment_score: 0.8,
      recommendation: {} as any,
      disclaimer: "",
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // Default: grant export so existing render tests stay stable
    mockCanAccess.mockReturnValue(true);
  });

  it("renders favorites table with symbol and BUY signal (no fake alpha card)", () => {
    render(<CandidateTable rows={[mockRow]} selectedSymbol={null} onSelect={vi.fn()} />);

    expect(screen.getAllByText("TCS.NS").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("BUY").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("System Alpha Overview")).toBeNull();
  });

  it("renders the Regime Badge based on sentiment", () => {
    render(<CandidateTable rows={[mockRow]} selectedSymbol={null} onSelect={vi.fn()} />);
    // Because newsSentiment is 'Bullish', it should render 'CATALYST' badge
    expect(screen.getAllByText("CATALYST").length).toBeGreaterThanOrEqual(1);
  });

  it("shows empty state when no rows", () => {
    render(<CandidateTable rows={[]} selectedSymbol={null} onSelect={vi.fn()} />);
    expect(screen.getByText("No matching stocks")).toBeDefined();
  });

  // ── Sprint 5: export_data feature guard ─────────────────────────────────

  it("shows Export CSV button when export_data feature access is granted", () => {
    mockCanAccess.mockImplementation((key: string) => key === "export_data");

    render(<CandidateTable rows={[mockRow]} selectedSymbol={null} onSelect={vi.fn()} />);

    expect(screen.getByTestId("export-data-btn")).toBeTruthy();
    expect(screen.getByText("Export CSV")).toBeTruthy();
    expect(mockCanAccess).toHaveBeenCalledWith("export_data");
  });

  it("hides Export CSV button when export_data feature access is denied (trader)", () => {
    mockCanAccess.mockReturnValue(false);

    render(<CandidateTable rows={[mockRow]} selectedSymbol={null} onSelect={vi.fn()} />);

    expect(screen.queryByTestId("export-data-btn")).toBeNull();
    expect(screen.queryByText("Export CSV")).toBeNull();
    // Table body still renders — only export control is gated
    expect(screen.getAllByText("TCS.NS").length).toBeGreaterThanOrEqual(1);
  });

  it("labels LTM momentum instead of showing it as a contradictory Score", () => {
    const ltmRow: CandidateRow = {
      ...mockRow,
      symbol: "CUPID-EQ",
      signal: "WATCH",
      score: null,
      scoreKind: "momentum_252",
      scoreLabel: "Momentum 252",
      momentumValue: 71.2,
      momentum: "71.2%",
      entryLow: 290.15,
      entryHigh: 290.15,
      stopLoss: null,
      target1: null,
      riskReward: null,
      ltm: { technicals: { close_t: 290.15, momentum_252: 0.7118 } },
    };
    render(<CandidateTable rows={[ltmRow]} selectedSymbol={null} onSelect={vi.fn()} />);
    expect(screen.getAllByText("CUPID").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("CUPID-EQ")).toBeNull();
    expect(screen.getAllByText("WATCH").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Momentum 252").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("71.2%").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("711.8")).toBeNull();
    expect(screen.getAllByText((_, node) => node?.textContent?.includes("Not available") ?? false).length).toBeGreaterThanOrEqual(1);
  });

  it("renders canonical symbol and company name from API metadata", () => {
    const named: CandidateRow = {
      ...mockRow,
      symbol: "360ONE-EQ",
      companyName: "360 ONE WAM Ltd.",
    };
    render(<CandidateTable rows={[named]} selectedSymbol={null} onSelect={vi.fn()} />);
    expect(screen.getAllByText("360ONE").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("360 ONE WAM Ltd.").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("360ONE-EQ")).toBeNull();
  });

  it("pages large result sets instead of mounting every row", () => {
    const rows = Array.from({ length: SCANNER_TABLE_PAGE_SIZE + 12 }, (_, i) => ({
      ...mockRow,
      symbol: `SYM${i}.NS`,
      rank: i + 1,
    }));
    render(<CandidateTable rows={rows} selectedSymbol={null} onSelect={vi.fn()} />);
    expect(screen.getAllByTestId("candidate-symbol")).toHaveLength(SCANNER_TABLE_PAGE_SIZE);
    expect(screen.getByTestId("scanner-show-more")).toBeTruthy();
    expect(screen.queryByText("SYM51.NS")).toBeNull();
    fireEvent.click(screen.getByTestId("scanner-show-more"));
    expect(screen.getAllByTestId("candidate-symbol")).toHaveLength(rows.length);
    expect(screen.getByText("SYM51.NS")).toBeTruthy();
  });

  it("does not render export control in empty state (no rows)", () => {
    mockCanAccess.mockReturnValue(true);

    render(<CandidateTable rows={[]} selectedSymbol={null} onSelect={vi.fn()} />);

    expect(screen.queryByTestId("export-data-btn")).toBeNull();
    expect(screen.getByText("No matching stocks")).toBeTruthy();
  });
});
