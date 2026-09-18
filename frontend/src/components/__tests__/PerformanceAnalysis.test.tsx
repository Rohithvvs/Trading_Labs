import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PerformanceAnalysis } from "../PerformanceAnalysis";

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

describe("PerformanceAnalysis Component", () => {
  const sampleModel = {
    trades: [
      { entry_date: "2024-01-01", exit_date: "2024-01-10", type: "LONG", pnl_percent: 5.0, net_pnl: 500, reason: "Breakout", open: false },
      { entry_date: "2024-01-15", exit_date: "2024-01-20", type: "SHORT", pnl_percent: -2.0, net_pnl: -200, reason: "Pullback", open: false },
      { entry_date: "2024-02-01", exit_date: "2024-02-10", type: "LONG", pnl_percent: 3.0, net_pnl: 300, reason: "Breakout", open: false },
    ],
    equity_curve: [
      { date: "2024-01-01", label: "2024-01-01", equity: 100000 },
      { date: "2024-01-10", label: "2024-01-10", equity: 100500 },
      { date: "2024-01-20", label: "2024-01-20", equity: 100300 },
      { date: "2024-02-10", label: "2024-02-10", equity: 100600 },
    ],
    benchmark_curve: [
      { date: "2024-01-01", close: 20000, equity: 100000 },
      { date: "2024-01-10", close: 20200, equity: 101000 },
      { date: "2024-01-20", close: 20100, equity: 100500 },
      { date: "2024-02-10", close: 20400, equity: 102000 },
    ],
    total_return: 0.6,
    cagr: 3.5,
    sharpe_ratio: 1.2,
    initial_capital: 100000,
  };

  it("renders Performance analysis header with all 5 pill tabs", () => {
    render(<PerformanceAnalysis model={sampleModel} />);

    expect(screen.getByText("Performance analysis")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Breakdown" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Periodical" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Benchmarking" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Margin usage" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Growth and decline" })).toBeTruthy();
  });

  it("renders Breakdown tab metrics and supports By signals vs By side", () => {
    render(<PerformanceAnalysis model={sampleModel} />);

    expect(screen.getByTestId("performance-breakdown-tab")).toBeTruthy();
    expect(screen.getByText("Gross profit")).toBeTruthy();
    expect(screen.getByText("Gross loss")).toBeTruthy();
    expect(screen.getByText("Profit factor")).toBeTruthy();
    expect(screen.getByText("Commission load")).toBeTruthy();

    expect(screen.getByText("800.00")).toBeTruthy();
    expect(screen.getByText("200.00")).toBeTruthy();
    expect(screen.getByText("4.000")).toBeTruthy();

    // Toggle to By side
    const bySideBtn = screen.getByRole("button", { name: "By side" });
    fireEvent.click(bySideBtn);
    expect(screen.getByText("Long")).toBeTruthy();
    expect(screen.getByText("Short")).toBeTruthy();

    // Toggle back to By signals
    const bySignalsBtn = screen.getByRole("button", { name: "By signals" });
    fireEvent.click(bySignalsBtn);
    expect(screen.getByText("All signals")).toBeTruthy();
  });

  it("switches to Periodical tab and supports period selector", () => {
    render(<PerformanceAnalysis model={sampleModel} />);

    const periodicalTab = screen.getByRole("tab", { name: "Periodical" });
    fireEvent.click(periodicalTab);

    expect(screen.getByTestId("performance-periodical-tab")).toBeTruthy();
    expect(screen.getByText("Annualized return (CAGR)")).toBeTruthy();
    expect(screen.getByText("Total return")).toBeTruthy();
    expect(screen.getByText("Sharpe ratio")).toBeTruthy();
    expect(screen.getByText("Sortino ratio")).toBeTruthy();

    expect(screen.getByRole("heading", { level: 4, name: "Weekly PnL" })).toBeTruthy();

    // Switch to Quarterly
    const quarterlyBtn = screen.getByRole("button", { name: "Quarterly" });
    fireEvent.click(quarterlyBtn);
    expect(screen.getByRole("heading", { level: 4, name: "Quarterly PnL" })).toBeTruthy();

    // Switch to Yearly
    const yearlyBtn = screen.getByRole("button", { name: "Yearly" });
    fireEvent.click(yearlyBtn);
    expect(screen.getByRole("heading", { level: 4, name: "Yearly PnL" })).toBeTruthy();
  });

  it("switches to Benchmarking tab and displays comparison metrics", () => {
    render(<PerformanceAnalysis model={sampleModel} />);

    const benchTab = screen.getByRole("tab", { name: "Benchmarking" });
    fireEvent.click(benchTab);

    expect(screen.getByTestId("performance-benchmarking-tab")).toBeTruthy();
    expect(screen.getByText("Strategy return")).toBeTruthy();
    expect(screen.getByText("Buy and hold return")).toBeTruthy();
    expect(screen.getByText("Strategy outperformance")).toBeTruthy();
    expect(screen.getByText("Correlation")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 4, name: "Strategy vs benchmark" })).toBeTruthy();
  });

  it("switches to Margin usage tab and displays utilization metrics", () => {
    render(<PerformanceAnalysis model={sampleModel} />);

    const marginTab = screen.getByRole("tab", { name: "Margin usage" });
    fireEvent.click(marginTab);

    expect(screen.getByTestId("performance-margin-tab")).toBeTruthy();
    expect(screen.getByText("Margin efficiency")).toBeTruthy();
    expect(screen.getByText("Average margin used")).toBeTruthy();
    expect(screen.getByText("Margin calls")).toBeTruthy();
    expect(screen.getByText("Total liquidated volume")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 4, name: "Margin utilization" })).toBeTruthy();
  });

  it("switches to Growth and decline tab and displays alternating and comparison charts", () => {
    render(<PerformanceAnalysis model={sampleModel} />);

    const growthTab = screen.getByRole("tab", { name: "Growth and decline" });
    fireEvent.click(growthTab);

    expect(screen.getByTestId("performance-growth-tab")).toBeTruthy();
    expect(screen.getByText("Average run-up duration")).toBeTruthy();
    expect(screen.getByText("Average drawdown duration")).toBeTruthy();
    expect(screen.getByText("Max drawdown")).toBeTruthy();
    expect(screen.getByText("Max drawdown as % of initial capital")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 4, name: "Alternating growth and decline" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 4, name: "Comparison of growth and decline periods" })).toBeTruthy();
  });

  it("renders clean empty state when no data is available", () => {
    render(<PerformanceAnalysis model={{ trades: [], equity_curve: [] }} />);

    expect(screen.getByTestId("performance-analysis-empty-state")).toBeTruthy();
    expect(screen.getByText("No performance analysis available")).toBeTruthy();
  });

  it("renders loading state when loading is true", () => {
    render(<PerformanceAnalysis model={null} loading={true} />);

    expect(screen.getByTestId("performance-analysis-loading")).toBeTruthy();
    expect(screen.getByText(/Computing performance breakdown/)).toBeTruthy();
  });
});
