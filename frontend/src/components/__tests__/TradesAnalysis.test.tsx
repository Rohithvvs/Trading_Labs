import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TradesAnalysis } from "../TradesAnalysis";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  ComposedChart: ({ children }: any) => <div>{children}</div>,
  PieChart: ({ children }: any) => <div>{children}</div>,
  Pie: () => <div />,
  ReferenceLine: () => <div />,
  Line: () => <div />,
  Area: () => <div />,
  Bar: () => <div />,
  Cell: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
}));

describe("TradesAnalysis Component", () => {
  const sampleModel = {
    trades: [
      { entry_date: "2024-01-01", exit_date: "2024-01-05", pnl_percent: 5.0, net_pnl: 500, holding_days: 4, open: false },
      { entry_date: "2024-01-06", exit_date: "2024-01-10", pnl_percent: -2.0, net_pnl: -200, holding_days: 4, open: false },
      { entry_date: "2024-01-11", exit_date: "2024-01-15", pnl_percent: 0.0, net_pnl: 0, holding_days: 4, open: false },
      { entry_date: "2024-01-16", exit_date: "2024-01-20", pnl_percent: 3.0, net_pnl: 300, holding_days: 4, open: false },
    ],
    ledger: {
      total_trades: 4,
      winning_trades: 2,
      losing_trades: 1,
      breakeven_trades: 1,
      win_rate: 50.0,
      expected_payoff: 1.5,
      expected_payoff_inr: 150.0,
      largest_profit: 5.0,
      largest_profit_inr: 500.0,
      largest_loss: -2.0,
      largest_loss_inr: -200.0,
      average_profit: 4.0,
      average_loss: -2.0,
      outlier_pnl: 0,
      outlier_trades: 0,
      gross_profit: 800,
      gross_loss: -200,
      net_pnl: 600,
    },
    initial_capital: 100000,
  };

  it("renders Trades analysis header with Distribution, Streaks, and Details tabs", () => {
    render(<TradesAnalysis model={sampleModel} />);

    expect(screen.getByText("Trades analysis")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Distribution" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Streaks" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Trades analysis details" })).toBeTruthy();
  });

  it("renders Distribution tab metrics and charts by default", () => {
    render(<TradesAnalysis model={sampleModel} />);

    // Top metrics
    expect(screen.getByText("Expected payoff")).toBeTruthy();
    expect(screen.getByText("Outliers PnL")).toBeTruthy();
    expect(screen.getByText("Largest profit")).toBeTruthy();
    expect(screen.getByText("Largest loss")).toBeTruthy();

    // Values
    expect(screen.getByText("150.00")).toBeTruthy();
    expect(screen.getByText("500.00")).toBeTruthy();
    expect(screen.getByText("200.00")).toBeTruthy();

    // Chart titles
    expect(screen.getByText("Returns distribution")).toBeTruthy();
    expect(screen.getByText("Trades distribution")).toBeTruthy();

    // Donut counts
    expect(screen.getByText("4")).toBeTruthy(); // Total trades
    expect(screen.getByText("2 trades")).toBeTruthy(); // Winners
    expect(screen.getAllByText("1 trades").length).toBe(2); // Losers and Breakevens
    expect(screen.getByText("50.00%")).toBeTruthy(); // Winners pct
    expect(screen.getAllByText("25.00%").length).toBe(2); // Losers and Breakevens pct
  });

  it("switches to Streaks tab when clicked", () => {
    render(<TradesAnalysis model={sampleModel} />);

    const streaksTab = screen.getByRole("tab", { name: "Streaks" });
    fireEvent.click(streaksTab);

    expect(screen.getByTestId("streaks-tab-content")).toBeTruthy();
    expect(screen.getByText("Winning Streak Analysis")).toBeTruthy();
    expect(screen.getByText("Losing Streak Analysis")).toBeTruthy();
    expect(screen.getByText("Streak Stability & Sequence")).toBeTruthy();
    expect(screen.getByText("Max winning streak")).toBeTruthy();
    expect(screen.getByText("Max losing streak")).toBeTruthy();
  });

  it("switches to Trades analysis details tab when clicked", () => {
    render(<TradesAnalysis model={sampleModel} />);

    const detailsTab = screen.getByRole("tab", { name: "Trades analysis details" });
    fireEvent.click(detailsTab);

    expect(screen.getByTestId("trades-analysis-details-tab-content")).toBeTruthy();
    expect(screen.getByText("Trade Overview & Distribution")).toBeTruthy();
    expect(screen.getByText("Financial Performance & Payoff")).toBeTruthy();
    expect(screen.getByText("Trade Averages & Extremes")).toBeTruthy();
    expect(screen.getByText("Holding Duration (Days)")).toBeTruthy();
    expect(screen.getByText("Profit factor")).toBeTruthy();
  });

  it("renders clean empty state when no trades are available", () => {
    render(<TradesAnalysis model={{ trades: [], trade_count: 0 }} />);

    expect(screen.getByTestId("trades-analysis-empty-state")).toBeTruthy();
    expect(screen.getByText("No trade analysis available")).toBeTruthy();
    expect(
      screen.getByText("Run a backtest with completed trades to view trade statistics."),
    ).toBeTruthy();
  });

  it("renders loading state when loading is true", () => {
    render(<TradesAnalysis model={null} loading={true} />);

    expect(screen.getByTestId("trades-analysis-loading")).toBeTruthy();
    expect(screen.getByText(/Computing trades distribution/)).toBeTruthy();
  });

  it("updates dynamically when backtest model changes", () => {
    const { rerender } = render(<TradesAnalysis model={sampleModel} />);

    expect(screen.getByText("150.00")).toBeTruthy();

    const newModel = {
      trades: [
        { entry_date: "2025-01-01", exit_date: "2025-01-10", pnl_percent: 12.0, net_pnl: 1200, open: false },
      ],
      ledger: {
        total_trades: 1,
        winning_trades: 1,
        losing_trades: 0,
        breakeven_trades: 0,
        win_rate: 100.0,
        expected_payoff_inr: 1200.0,
        expected_payoff: 12.0,
        largest_profit_inr: 1200.0,
        largest_profit: 12.0,
      },
      initial_capital: 100000,
    };

    rerender(<TradesAnalysis model={newModel} />);

    expect(screen.getAllByText("1200.00").length).toBeGreaterThan(0);
    expect(screen.getByText("100.00%")).toBeTruthy();
  });
});
