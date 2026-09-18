import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StrategyBuilderModal } from "../StrategyBuilderModal";
import { DEFAULT_PINE_TEMPLATE } from "../../../utils/pineParser";

describe("StrategyBuilderModal", () => {
  const defaultProps = {
    isOpen: true,
    initialName: "Momentum Strategy",
    initialDescription: "Default momentum strategy",
    initialFilters: [
      { id: "1", field: "CLOSE", operator: ">", rightKind: "indicator" as const, literal: "", indicator: "SMA", indicatorPeriod: "50", low: "", high: "" },
      { id: "2", field: "SMA", period: "50", operator: ">", rightKind: "indicator" as const, literal: "", indicator: "SMA", indicatorPeriod: "200", low: "", high: "" },
    ],
    initialLogic: "ALL" as const,
    initialSide: "LONG" as const,
    onClose: vi.fn(),
    onApply: vi.fn(),
  };

  it("renders with Strategy Builder tab by default", () => {
    render(<StrategyBuilderModal {...defaultProps} />);

    expect(screen.getByTestId("modal-strategy-builder")).toBeTruthy();
    expect(screen.getByTestId("tab-strategy-builder").className).toContain("is-active");
    expect(screen.getByTestId("tab-indicator")).toBeTruthy();
    expect(screen.getByTestId("input-strategy-name")).toBeTruthy();
    expect((screen.getByTestId("input-strategy-name") as HTMLInputElement).value).toBe("Momentum Strategy");
    expect(screen.getByTestId("btn-apply-strategy-builder")).toBeTruthy();
    expect(screen.getByTestId("btn-apply-strategy-builder").textContent).toBe("Save & Apply");
  });

  it("switches to Indicator tab and shows the create indicator editor", () => {
    render(<StrategyBuilderModal {...defaultProps} />);
    fireEvent.click(screen.getByTestId("tab-indicator"));
    expect(screen.getByTestId("tab-indicator").className).toContain("is-active");
    expect(screen.getByTestId("indicator-editor-panel")).toBeTruthy();
    expect(screen.getByText("Create Indicator")).toBeTruthy();
    expect(screen.queryByTestId("btn-apply-strategy-builder")).toBeNull();
  });

  it("switches to Pine Script tab and shows code editor and Observe Filters button", () => {
    render(<StrategyBuilderModal {...defaultProps} />);

    // Click Pine Script tab
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    expect(screen.getByTestId("tab-pine-script").className).toContain("is-active");
    expect(screen.getByTestId("pine-code-editor")).toBeTruthy();
    expect(screen.getByTestId("pine-version-badge").textContent).toContain("Pine Script version detected: v6");
    expect(screen.getByTestId("btn-observe-pine-filters")).toBeTruthy();
    expect(screen.getByTestId("btn-observe-pine-filters").textContent).toBe("Observe Filters");
  });

  it("detects Pine Script versions (v6, v5, unsupported v3)", () => {
    render(<StrategyBuilderModal {...defaultProps} />);
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    const textarea = screen.getByTestId("pine-textarea");

    // Version 5
    fireEvent.change(textarea, { target: { value: `//@version=5\nstrategy("V5 Test")` } });
    expect(screen.getByTestId("pine-version-badge").textContent).toContain("v5");

    // Unsupported Version 3
    fireEvent.change(textarea, { target: { value: `//@version=3\nstrategy("V3 Test")` } });
    expect(screen.getByTestId("pine-version-badge").textContent).toContain("Unsupported Pine Script version (v3)");
  });

  it("shows error when clicking Observe Filters with empty code", () => {
    const onApply = vi.fn();
    render(<StrategyBuilderModal {...defaultProps} onApply={onApply} />);
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    const textarea = screen.getByTestId("pine-textarea");
    fireEvent.change(textarea, { target: { value: "   " } });

    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    expect(screen.getByTestId("pine-error-banner")).toBeTruthy();
    expect(screen.getByTestId("pine-error-banner").textContent).toContain("Please enter Pine Script code first");
    expect(onApply).not.toHaveBeenCalled();
  });

  it("shows error on syntax failure and does NOT apply or save", () => {
    const onApply = vi.fn();
    render(<StrategyBuilderModal {...defaultProps} onApply={onApply} />);
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    const textarea = screen.getByTestId("pine-textarea");
    fireEvent.change(textarea, { target: { value: "//@version=6\nstrategy(\"Broken\"\nlongCondition =" } });

    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    expect(screen.getByTestId("pine-error-banner")).toBeTruthy();
    expect(screen.getByTestId("pine-error-banner").textContent).toContain("Unable to analyze Pine Script");
    expect(onApply).not.toHaveBeenCalled();
  });

  it("Test Case 1: parses Momentum Strategy, populates Builder, switches tab, and does NOT auto-save", () => {
    const onApply = vi.fn();
    render(<StrategyBuilderModal {...defaultProps} onApply={onApply} />);
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    const pineCode = `//@version=6
strategy("Momentum Strategy", overlay=true)

sma50 = ta.sma(close, 50)
sma200 = ta.sma(close, 200)
rsi = ta.rsi(close, 14)
avgVolume = ta.sma(volume, 20)

longCondition = close > sma50 and sma50 > sma200 and rsi > 55 and volume > avgVolume

if longCondition
    strategy.entry("Long", strategy.long)
`;

    const textarea = screen.getByTestId("pine-textarea");
    fireEvent.change(textarea, { target: { value: pineCode } });

    // Click Observe Filters
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    // Critical: Observe Filters must NOT call onApply (no auto-save or auto-scan)
    expect(onApply).not.toHaveBeenCalled();

    // Must automatically switch to Strategy Builder tab
    expect(screen.getByTestId("tab-strategy-builder").className).toContain("is-active");

    // Summary banner must be visible
    expect(screen.getByTestId("pine-import-summary")).toBeTruthy();
    expect(screen.getByTestId("pine-import-summary").textContent).toContain("Pine Script analyzed successfully");
    expect(screen.getByTestId("pine-import-summary").textContent).toContain("4 entry filters detected");

    // Strategy Name populated
    expect((screen.getByTestId("input-strategy-name") as HTMLInputElement).value).toBe("Momentum Strategy");

    // Position Side populated
    expect((screen.getByTestId("select-position-side") as HTMLSelectElement).value).toBe("LONG");

    // 4 filter rows rendered
    expect(screen.getByTestId("filter-row-0")).toBeTruthy();
    expect(screen.getByTestId("filter-row-1")).toBeTruthy();
    expect(screen.getByTestId("filter-row-2")).toBeTruthy();
    expect(screen.getByTestId("filter-row-3")).toBeTruthy();
  });

  it("Test Case 2: parses 52W Breakout with offset [1]", () => {
    render(<StrategyBuilderModal {...defaultProps} />);
    fireEvent.click(screen.getByTestId("tab-pine-script"));

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
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    expect(screen.getByTestId("tab-strategy-builder").className).toContain("is-active");
    expect((screen.getByTestId("input-strategy-name") as HTMLInputElement).value).toBe("52W Breakout");
    expect(screen.getByTestId("pine-import-summary").textContent).toContain("5 entry filters detected");
  });

  it("Test Case 3: parses OR Logic into ANY execution logic", () => {
    render(<StrategyBuilderModal {...defaultProps} />);
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    const pineCode = `//@version=6
strategy("OR Test")

longCondition =
    close > ta.sma(close, 50) or
    ta.rsi(close, 14) > 70

if longCondition
    strategy.entry("Long", strategy.long)
`;

    const textarea = screen.getByTestId("pine-textarea");
    fireEvent.change(textarea, { target: { value: pineCode } });
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    expect(screen.getByTestId("tab-strategy-builder").className).toContain("is-active");
    expect(screen.getByTestId("btn-logic-any").className).toContain("st-btn-primary");
  });

  it("Test Case 6: allows manual editing after Observe Filters and submits with Save & Apply", () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    render(<StrategyBuilderModal {...defaultProps} onApply={onApply} onClose={onClose} />);

    fireEvent.click(screen.getByTestId("tab-pine-script"));

    const pineCode = `//@version=6
strategy("Momentum Strategy", overlay=true)

sma50 = ta.sma(close, 50)
sma200 = ta.sma(close, 200)
rsi = ta.rsi(close, 14)
avgVolume = ta.sma(volume, 20)

longCondition = close > sma50 and sma50 > sma200 and rsi > 55 and volume > avgVolume

if longCondition
    strategy.entry("Long", strategy.long)
`;

    const textarea = screen.getByTestId("pine-textarea");
    fireEvent.change(textarea, { target: { value: pineCode } });
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    // User edits RSI threshold from 55 to 60
    const rsiLiteralInput = screen.getByTestId("filter-literal-2");
    fireEvent.change(rsiLiteralInput, { target: { value: "60" } });

    // User edits strategy name
    const nameInput = screen.getByTestId("input-strategy-name");
    fireEvent.change(nameInput, { target: { value: "Momentum Strategy Modified" } });

    // User clicks Save & Apply
    fireEvent.click(screen.getByTestId("btn-apply-strategy-builder"));

    expect(onApply).toHaveBeenCalledTimes(1);
    const [name, , filters, logic, side, source, passedPineCode] = onApply.mock.calls[0];
    expect(name).toBe("Momentum Strategy Modified");
    expect(logic).toBe("ALL");
    expect(side).toBe("LONG");
    expect(source).toBe("pine");
    expect(passedPineCode).toBe(pineCode);
    expect(filters[2].literal).toBe("60");
    expect(onClose).toHaveBeenCalled();
  });

  it("Test Case 7: Canonical 52-Week High Breakout Strategy shows market gate, risk management, exit, and ranking", () => {
    render(<StrategyBuilderModal {...defaultProps} />);
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    const textarea = screen.getByTestId("pine-textarea");
    fireEvent.change(textarea, { target: { value: DEFAULT_PINE_TEMPLATE } });
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    expect(screen.getByTestId("tab-strategy-builder").className).toContain("is-active");
    expect((screen.getByTestId("input-strategy-name") as HTMLInputElement).value).toBe("52-Week High Breakout");

    const summary = screen.getByTestId("pine-import-summary");
    expect(summary.textContent).toContain("3 entry filters detected");
    expect(summary.textContent).toContain("Market Gate");
    expect(summary.textContent).toContain("NIFTY 500");
    expect(summary.textContent).toContain("Risk Management");
    expect(summary.textContent).toContain("Trailing Stop");
    expect(summary.textContent).toContain("Ranking: Momentum 60 descending");

    // Exactly 3 entry filters in UI
    expect(screen.getByTestId("filter-row-0")).toBeTruthy();
    expect(screen.getByTestId("filter-row-1")).toBeTruthy();
    expect(screen.getByTestId("filter-row-2")).toBeTruthy();
    expect(screen.queryByTestId("filter-row-3")).toBeNull();
  });

  it("Test Case 8: Accidental data loss protection prompts confirmation before replacing modified filters", () => {
    render(<StrategyBuilderModal {...defaultProps} />);

    // User modifies builder filters first
    const nameInput = screen.getByTestId("input-strategy-name");
    fireEvent.change(nameInput, { target: { value: "My Custom Modified Strategy" } });
    const addFilterBtn = screen.getByTestId("btn-add-filter-rule");
    fireEvent.click(addFilterBtn);

    // User switches to Pine Script tab
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    const textarea = screen.getByTestId("pine-textarea");
    fireEvent.change(textarea, { target: { value: DEFAULT_PINE_TEMPLATE } });

    // Click Observe Filters -> should trigger confirmation dialog
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));

    expect(screen.getByTestId("pine-confirm-replace")).toBeTruthy();
    expect(screen.getByTestId("pine-confirm-replace").textContent).toContain("Replace Existing Filters?");

    // Click Cancel -> dialog closes, tab stays on Pine
    fireEvent.click(screen.getByTestId("btn-cancel-replace-filters"));
    expect(screen.queryByTestId("pine-confirm-replace")).toBeNull();

    // Click Observe Filters again and confirm replace
    fireEvent.click(screen.getByTestId("btn-observe-pine-filters"));
    expect(screen.getByTestId("pine-confirm-replace")).toBeTruthy();
    fireEvent.click(screen.getByTestId("btn-confirm-replace-filters"));

    // Now switches to builder tab with replaced filters
    expect(screen.getByTestId("tab-strategy-builder").className).toContain("is-active");
    expect((screen.getByTestId("input-strategy-name") as HTMLInputElement).value).toBe("52-Week High Breakout");
  });

  it("Test Case 9: Debug trace button toggles AST semantic role table", () => {
    render(<StrategyBuilderModal {...defaultProps} />);
    fireEvent.click(screen.getByTestId("tab-pine-script"));

    expect(screen.queryByTestId("pine-debug-trace")).toBeNull();

    // Click Debug Trace button
    fireEvent.click(screen.getByTestId("btn-toggle-pine-debug"));
    expect(screen.getByTestId("pine-debug-trace")).toBeTruthy();
    expect(screen.getByTestId("pine-debug-trace").textContent).toContain("ENTRY_FILTER");
    expect(screen.getByTestId("pine-debug-trace").textContent).toContain("RISK_MANAGEMENT");

    // Click again to hide
    fireEvent.click(screen.getByTestId("btn-toggle-pine-debug"));
    expect(screen.queryByTestId("pine-debug-trace")).toBeNull();
  });
});
