import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import type { StrategyResultRow } from "../../../api_strategy_tester";
import { AllStockResultsTable } from "../AllStockResultsTable";
import { FilterFunnelCard } from "../FilterFunnelCard";
import { SignalDistributionCard } from "../SignalDistributionCard";
import { TopReturnsCard } from "../TopReturnsCard";

// Mock ResizeObserver for Recharts
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

describe("AllStockResultsTable - Layout and Signal Priority", () => {
  const mockResults: StrategyResultRow[] = [
    {
      rank: 3,
      symbol: "REJECT1",
      company: "Reject Corp",
      status: "ok",
      signal: "REJECT",
      entry_price: 100,
      exit_price: 90,
      return_pct: -10,
      filters_passed: 1,
      filters_failed: 3,
      passed_filters: ["F1"],
      failed_filters: ["F2", "F3", "F4"],
    },
    {
      rank: 1,
      symbol: "BUY1",
      company: "Buy Corp 1",
      status: "ok",
      signal: "BUY",
      entry_price: 100,
      exit_price: 130,
      return_pct: 30,
      filters_passed: 4,
      filters_failed: 0,
      passed_filters: ["F1", "F2", "F3", "F4"],
      failed_filters: [],
    },
    {
      rank: 2,
      symbol: "WATCH1",
      company: "Watch Corp",
      status: "ok",
      signal: "WATCH",
      entry_price: 100,
      exit_price: 110,
      return_pct: 10,
      filters_passed: 3,
      filters_failed: 1,
      passed_filters: ["F1", "F2", "F3"],
      failed_filters: ["F4"],
    },
    {
      rank: 4,
      symbol: "BUY2",
      company: "Buy Corp 2",
      status: "ok",
      signal: "BUY",
      entry_price: 50,
      exit_price: 60,
      return_pct: 20,
      filters_passed: 4,
      filters_failed: 0,
      passed_filters: ["F1", "F2", "F3", "F4"],
      failed_filters: [],
    },
    {
      rank: 5,
      symbol: "FAIL1",
      company: "Fail Corp",
      status: "error",
      signal: "FAILED",
      entry_price: 50,
      exit_price: 45,
      return_pct: -10,
      filters_passed: 0,
      filters_failed: 4,
      passed_filters: [],
      failed_filters: ["F1", "F2", "F3", "F4"],
    },
  ];

  it("orders rows by signal priority: BUY -> WATCH -> REJECT -> FAILED when All Signals is active", () => {
    const handleStockSelect = vi.fn();
    render(
      <AllStockResultsTable
        results={mockResults}
        totalResults={5}
        selectedSymbol={null}
        searchQuery=""
        signalFilter="ALL"
        returnFilter="ALL"
        sortColumn="return_pct"
        sortDirection="desc"
        currentPage={1}
        pageSize={25}
        buyCount={2}
        watchCount={1}
        rejectCount={1}
        failedCount={1}
        onSearchChange={vi.fn()}
        onSignalFilterChange={vi.fn()}
        onReturnFilterChange={vi.fn()}
        onSortChange={vi.fn()}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
        onStockSelect={handleStockSelect}
        onColumnsClick={vi.fn()}
        onExportClick={vi.fn()}
      />
    );

    const rows = screen.getAllByTestId(/^row-stock-/);
    expect(rows.length).toBe(5);

    // BUY1 (30%) and BUY2 (20%) should be first
    expect(rows[0].getAttribute("data-testid")).toBe("row-stock-BUY1");
    expect(rows[1].getAttribute("data-testid")).toBe("row-stock-BUY2");
    // WATCH1 (10%) should be next
    expect(rows[2].getAttribute("data-testid")).toBe("row-stock-WATCH1");
    // REJECT1 (-10%) should be next
    expect(rows[3].getAttribute("data-testid")).toBe("row-stock-REJECT1");
    // FAIL1 should be last
    expect(rows[4].getAttribute("data-testid")).toBe("row-stock-FAIL1");
  });

  it("has quick access signal selector pills with dynamic counts and active states", () => {
    const onSignalFilterChange = vi.fn();
    const onPageChange = vi.fn();

    const { rerender } = render(
      <AllStockResultsTable
        results={mockResults}
        totalResults={755}
        selectedSymbol={null}
        searchQuery=""
        signalFilter="ALL"
        returnFilter="ALL"
        sortColumn="return_pct"
        sortDirection="desc"
        currentPage={1}
        pageSize={25}
        buyCount={42}
        watchCount={183}
        rejectCount={530}
        failedCount={0}
        onSearchChange={vi.fn()}
        onSignalFilterChange={onSignalFilterChange}
        onReturnFilterChange={vi.fn()}
        onSortChange={vi.fn()}
        onPageChange={onPageChange}
        onPageSizeChange={vi.fn()}
        onStockSelect={vi.fn()}
        onColumnsClick={vi.fn()}
        onExportClick={vi.fn()}
      />
    );

    const buyPill = screen.getByTestId("pill-filter-buy");
    const watchPill = screen.getByTestId("pill-filter-watch");
    const rejectPill = screen.getByTestId("pill-filter-reject");
    const failedPill = screen.getByTestId("pill-filter-failed");

    expect(buyPill.textContent).toContain("BUY42");
    expect(watchPill.textContent).toContain("WATCH183");
    expect(rejectPill.textContent).toContain("REJECT530");
    expect(failedPill.textContent).toContain("FAILED0");

    expect(buyPill.className).not.toContain("is-active");

    fireEvent.click(buyPill);
    expect(onSignalFilterChange).toHaveBeenCalledWith("BUY");
    expect(onPageChange).toHaveBeenCalledWith(1);

    // Re-render with signalFilter="BUY"
    rerender(
      <AllStockResultsTable
        results={mockResults}
        totalResults={42}
        selectedSymbol={null}
        searchQuery=""
        signalFilter="BUY"
        returnFilter="ALL"
        sortColumn="return_pct"
        sortDirection="desc"
        currentPage={1}
        pageSize={25}
        buyCount={42}
        watchCount={183}
        rejectCount={530}
        failedCount={0}
        onSearchChange={vi.fn()}
        onSignalFilterChange={onSignalFilterChange}
        onReturnFilterChange={vi.fn()}
        onSortChange={vi.fn()}
        onPageChange={onPageChange}
        onPageSizeChange={vi.fn()}
        onStockSelect={vi.fn()}
        onColumnsClick={vi.fn()}
        onExportClick={vi.fn()}
      />
    );

    expect(screen.getByTestId("pill-filter-buy").className).toContain("is-active");
  });

  it("has Left-aligned toolbar with Search, dropdowns in correct order, Columns, and Export CSV", () => {
    const onColumnsClick = vi.fn();
    const onExportClick = vi.fn();
    const onSearchChange = vi.fn();

    const { container } = render(
      <AllStockResultsTable
        results={mockResults}
        totalResults={755}
        selectedSymbol={null}
        searchQuery=""
        signalFilter="ALL"
        returnFilter="ALL"
        sortColumn="return_pct"
        sortDirection="desc"
        currentPage={1}
        pageSize={25}
        onSearchChange={onSearchChange}
        onSignalFilterChange={vi.fn()}
        onReturnFilterChange={vi.fn()}
        onSortChange={vi.fn()}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
        onStockSelect={vi.fn()}
        onColumnsClick={onColumnsClick}
        onExportClick={onExportClick}
      />
    );

    const toolbar = container.querySelector(".st-results-toolbar");
    expect(toolbar).toBeTruthy();

    const searchInput = screen.getByTestId("input-search-stocks");
    expect(searchInput).toBeTruthy();
    expect(searchInput.getAttribute("placeholder")).toBe("Search by symbol or company");

    fireEvent.change(searchInput, { target: { value: "TCS" } });
    expect(onSearchChange).toHaveBeenCalledWith("TCS");

    // All Signals dropdown strict order
    const signalSelect = screen.getByTestId("select-signal-filter") as HTMLSelectElement;
    const signalOptions = Array.from(signalSelect.options).map((o) => o.text);
    expect(signalOptions).toEqual(["All Signals ▼", "BUY", "WATCH", "REJECT", "FAILED"]);

    // All Returns dropdown options
    const returnSelect = screen.getByTestId("select-return-filter") as HTMLSelectElement;
    const returnOptions = Array.from(returnSelect.options).map((o) => o.text);
    expect(returnOptions).toEqual(["All Returns ▼", "Positive Returns", "Negative Returns", "Flat Returns"]);

    // Columns & Export CSV buttons
    fireEvent.click(screen.getByTestId("btn-columns-modal"));
    expect(onColumnsClick).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("btn-export-csv"));
    expect(onExportClick).toHaveBeenCalledTimes(1);
  });
});

describe("FilterFunnelCard - Sequential Trapezoid Funnel", () => {
  it("renders stages from Start Universe down to Final BUY Signals", () => {
    const onStepClick = vi.fn();
    const mockSteps = [
      { step: 0, filter_id: null, label: "Start Universe", remaining: 755 },
      { step: 1, filter_id: "f1", label: "Close > SMA 50", remaining: 620 },
      { step: 2, filter_id: "f2", label: "SMA 50 > SMA 200", remaining: 410 },
      { step: 3, filter_id: "f3", label: "RSI > 55", remaining: 285 },
      { step: 4, filter_id: "f4", label: "Volume > Avg Volume", remaining: 195 },
      { step: 5, filter_id: "final", label: "Final BUY Signals", remaining: 42 },
    ];

    const { container } = render(
      <FilterFunnelCard
        steps={mockSteps}
        totalUniverse={755}
        onStepClick={onStepClick}
      />
    );

    expect(screen.getByText("Filter Funnel (Sequential)")).toBeTruthy();
    expect(screen.getByText("Start Universe")).toBeTruthy();
    expect(screen.getByText("Close > SMA 50")).toBeTruthy();
    expect(screen.getByText("SMA 50 > SMA 200")).toBeTruthy();
    expect(screen.getByText("RSI > 55")).toBeTruthy();
    expect(screen.getByText("Volume > Avg Volume")).toBeTruthy();
    expect(screen.getByText("Final BUY Signals")).toBeTruthy();

    // Stage counts inside trapezoid bars
    const funnelNumbers = container.querySelectorAll(".st-funnel-number");
    expect(funnelNumbers.length).toBe(6);
    expect(funnelNumbers[0].textContent).toBe("755");
    expect(funnelNumbers[1].textContent).toBe("620");
    expect(funnelNumbers[2].textContent).toBe("410");
    expect(funnelNumbers[3].textContent).toBe("285");
    expect(funnelNumbers[4].textContent).toBe("195");
    expect(funnelNumbers[5].textContent).toBe("42");

    // Clicking stage fires onStepClick
    const rows = container.querySelectorAll(".st-funnel-row");
    fireEvent.click(rows[5]);
    expect(onStepClick).toHaveBeenCalledWith(mockSteps[5]);
  });
});

describe("SignalDistributionCard - Donut Chart & Legend Order", () => {
  it("strictly displays legend in BUY -> WATCH -> REJECT -> FAILED order", () => {
    const onSignalClick = vi.fn();
    render(
      <SignalDistributionCard
        buyCount={42}
        watchCount={183}
        rejectCount={530}
        failedCount={5}
        totalUniverse={760}
        onSignalClick={onSignalClick}
      />
    );

    expect(screen.getByText("Signal Distribution")).toBeTruthy();
    expect(screen.getByText("760")).toBeTruthy();
    expect(screen.getByText("Total Stocks")).toBeTruthy();

    const buyItem = screen.getByTitle("Filter by BUY");
    const watchItem = screen.getByTitle("Filter by WATCH");
    const rejectItem = screen.getByTitle("Filter by REJECT");
    const failedItem = screen.getByTitle("Filter by FAILED");

    expect(buyItem.textContent).toContain("BUY: 42");
    expect(watchItem.textContent).toContain("WATCH: 183");
    expect(rejectItem.textContent).toContain("REJECT: 530");
    expect(failedItem.textContent).toContain("FAILED: 5");

    fireEvent.click(buyItem);
    expect(onSignalClick).toHaveBeenCalledWith("BUY");
  });
});

describe("TopReturnsCard - Top 5 Positive and Negative", () => {
  it("sorts Top 5 Positive highest to lowest return and triggers stock selection", () => {
    const onStockClick = vi.fn();
    const onViewAllClick = vi.fn();

    const items = [
      { rank: 1, symbol: "A", entry_price: 10, exit_price: 15, return_pct: 50, signal: "BUY", key_filters: ["F1"] },
      { rank: 2, symbol: "B", entry_price: 10, exit_price: 20, return_pct: 100, signal: "BUY", key_filters: ["F1"] },
      { rank: 3, symbol: "C", entry_price: 10, exit_price: 12, return_pct: 20, signal: "BUY", key_filters: ["F1"] },
    ];

    render(
      <TopReturnsCard
        type="positive"
        items={items}
        totalCount={3}
        onStockClick={onStockClick}
        onViewAllClick={onViewAllClick}
      />
    );

    expect(screen.getByText("Top 5 Positive Returns")).toBeTruthy();
    const rows = screen.getAllByRole("row");
    // header is row 0, row 1 should be B (+100%), row 2 should be A (+50%), row 3 should be C (+20%)
    expect(rows[1].textContent).toContain("B");
    expect(rows[1].textContent).toContain("+100.00%");
    expect(rows[2].textContent).toContain("A");
    expect(rows[2].textContent).toContain("+50.00%");
    expect(rows[3].textContent).toContain("C");
    expect(rows[3].textContent).toContain("+20.00%");

    fireEvent.click(rows[1]);
    expect(onStockClick).toHaveBeenCalledWith("B");

    fireEvent.click(screen.getByTestId("link-view-all-positive"));
    expect(onViewAllClick).toHaveBeenCalledTimes(1);
  });

  it("sorts Top 5 Negative lowest to highest return (most negative first)", () => {
    const items = [
      { rank: 1, symbol: "X", entry_price: 10, exit_price: 8, return_pct: -20, signal: "REJECT", key_filters: ["F1"] },
      { rank: 2, symbol: "Y", entry_price: 10, exit_price: 5, return_pct: -50, signal: "REJECT", key_filters: ["F1"] },
      { rank: 3, symbol: "Z", entry_price: 10, exit_price: 9, return_pct: -10, signal: "WATCH", key_filters: ["F1"] },
    ];

    render(
      <TopReturnsCard
        type="negative"
        items={items}
        totalCount={3}
        onStockClick={vi.fn()}
        onViewAllClick={vi.fn()}
      />
    );

    expect(screen.getByText("Top 5 Negative Returns")).toBeTruthy();
    const rows = screen.getAllByRole("row");
    // row 1 should be Y (-50%), row 2 should be X (-20%), row 3 should be Z (-10%)
    expect(rows[1].textContent).toContain("Y");
    expect(rows[1].textContent).toContain("-50.00%");
    expect(rows[2].textContent).toContain("X");
    expect(rows[2].textContent).toContain("-20.00%");
    expect(rows[3].textContent).toContain("Z");
    expect(rows[3].textContent).toContain("-10.00%");
  });
});
