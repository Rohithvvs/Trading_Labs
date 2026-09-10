import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IndicatorEditorPanel } from "../IndicatorEditorPanel";
import { DEFAULT_INDICATOR_TEMPLATE } from "../../../utils/indicatorTemplate";

const validateIndicatorSource = vi.fn();
const createIndicator = vi.fn();
const fetchIndicators = vi.fn(async () => []);
const updateIndicator = vi.fn();

vi.mock("../../../api_indicator_scanner", () => ({
  validateIndicatorSource: (...args: unknown[]) => validateIndicatorSource(...args),
  createIndicator: (...args: unknown[]) => createIndicator(...args),
  fetchIndicators: (...args: unknown[]) => fetchIndicators(...args),
  updateIndicator: (...args: unknown[]) => updateIndicator(...args),
}));

describe("IndicatorEditorPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchIndicators.mockResolvedValue([]);
  });

  it("renders create indicator copy, template, and keeps Save & Apply clickable", () => {
    render(<IndicatorEditorPanel onCancel={vi.fn()} onSaved={vi.fn()} onSavedAndApply={vi.fn()} />);
    expect(screen.getByText("Create Indicator")).toBeTruthy();
    expect(screen.queryByText("Edit Indicator")).toBeNull();
    expect(screen.getByText(/Paste indicator Pine code, click Observe/i)).toBeTruthy();
    expect(screen.getByText(/TradingLabs supports a secure Pine Script v6-compatible subset/i)).toBeTruthy();
    expect((screen.getByTestId("input-indicator-name") as HTMLInputElement).value).toBe("52-Week High Breakout [SCAN]");
    expect((screen.getByTestId("pine-textarea") as HTMLTextAreaElement).value).toContain("indicator(\"52-Week High Breakout [SCAN]\"");
    expect((screen.getByTestId("btn-save-apply-indicator") as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId("btn-save-indicator") as HTMLButtonElement).disabled).toBe(false);
    expect(DEFAULT_INDICATOR_TEMPLATE).toContain("plot(scanSignal ? 1 : 0, \"52W Breakout Signal\")");
  });

  it("validates successfully and enables save", async () => {
    validateIndicatorSource.mockResolvedValue({
      ok: true,
      status: "valid",
      errors: [],
      warnings: [{ line: 1, column: 1, message: "Input 'ATR Multiplier' is defined but is not used by this indicator." }],
      inputs: [
        { name: "breakoutLength", title: "Breakout Lookback", kind: "int", default: 252 },
        { name: "atrMultiplier", title: "ATR Multiplier", kind: "float", default: 3.0 },
      ],
      outputs: [
        { name: "52W Breakout Signal", kind: "plot" },
        { name: "Close", kind: "plot" },
        { name: "52W Breakout", kind: "plotshape" },
        { name: "52W Breakout Scan", kind: "alertcondition" },
      ],
      parsed_definition: {
        outputs: [
          { name: "52W Breakout Signal", kind: "plot" },
          { name: "Close", kind: "plot" },
        ],
        entry_conditions: [
          { name: "NIFTY 500 Close > NIFTY 500 SMA 50" },
          { name: "Close >= Prior 252 High" },
          { name: "Volume > Average Volume 20" },
        ],
      },
      required_bars: 253,
      required_symbols: ["NSE:CNX500"],
    });
    render(<IndicatorEditorPanel onCancel={vi.fn()} onSaved={vi.fn()} onSavedAndApply={vi.fn()} />);
    fireEvent.click(screen.getByTestId("btn-validate-indicator"));
    await waitFor(() => expect(screen.getByTestId("indicator-validation-panel").textContent).toContain("Valid"));
    expect(screen.getByTestId("btn-validate-indicator").textContent).toContain("Observe");
    const panel = screen.getByTestId("indicator-observe-summary").textContent || "";
    expect(panel).toContain("Absorbed from Pine");
    expect(panel).toContain("ATR Multiplier");
    expect(panel).toContain("52W Breakout Signal");
    expect(screen.getByTestId("indicator-absorbed-filters").textContent).toContain("NIFTY 500 Close > NIFTY 500 SMA 50");
    expect(screen.getByTestId("indicator-absorbed-filters").textContent).toContain("Close >= Prior 252 High");
    expect(screen.getByTestId("indicator-absorbed-filters").textContent).toContain("Volume > Average Volume 20");
    expect(screen.getByTestId("indicator-absorbed-filters").textContent).not.toContain("52W Breakout Signal = 1");
    expect((screen.getByTestId("btn-save-apply-indicator") as HTMLButtonElement).disabled).toBe(false);
  });

  it("offers to insert a Signal = 1 plot when the first plot is a price", async () => {
    validateIndicatorSource.mockResolvedValue({
      ok: true,
      status: "valid",
      errors: [],
      warnings: [
        {
          line: 6,
          column: 1,
          code: "MISSING_SCREENER_SIGNAL_PLOT",
          message:
            "TradingView Pine Screener filters numeric plot() columns. This script's first plot is 'EMA 20' (not a 0/1 signal), so setting that column to 1 matches nothing.",
        },
      ],
      inputs: [],
      outputs: [
        { name: "EMA 20", kind: "plot" },
        { name: "Momentum Signal", kind: "plotshape" },
      ],
      parsed_definition: {
        outputs: [
          { name: "EMA 20", kind: "plot" },
          { name: "Momentum Signal", kind: "plotshape" },
        ],
        entry_conditions: [{ name: "Close > EMA 20" }, { name: "RSI 14 crosses above 50" }],
      },
      required_bars: 20,
      required_symbols: [],
    });
    const pulse = `//@version=6
indicator("Momentum Pulse Finder", overlay=true)
ema20 = ta.ema(close, 20)
rsiValue = ta.rsi(close, 14)
buySignal = close > ema20 and ta.crossover(rsiValue, 50)
plot(ema20, title="EMA 20")
plotshape(buySignal, title="Momentum Signal")
`;
    render(
      <IndicatorEditorPanel
        initial={{
          id: "ind-pulse",
          name: "Momentum Pulse Finder",
          description: "",
          source_code: pulse,
          script_version: 6,
          language_mode: "pine_subset_v1",
          timeframe: "1D",
          validation_status: "valid",
          required_bars: 20,
        }}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onSavedAndApply={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("btn-validate-indicator"));
    await waitFor(() => expect(screen.getByTestId("btn-insert-screener-signal-plot")).toBeTruthy());
    fireEvent.click(screen.getByTestId("btn-insert-screener-signal-plot"));
    expect((screen.getByTestId("pine-textarea") as HTMLTextAreaElement).value).toContain(
      'plot(buySignal ? 1 : 0, "Signal")',
    );
  });

  it("shows line-specific errors for unsupported Pine", async () => {
    validateIndicatorSource.mockResolvedValue({
      ok: false,
      status: "invalid",
      errors: [{ line: 2, column: 1, message: "This is an indicator scanner. Use indicator() instead of strategy()." }],
      warnings: [],
      inputs: [],
      outputs: [],
      required_bars: 0,
      required_symbols: [],
    });
    render(<IndicatorEditorPanel onCancel={vi.fn()} onSaved={vi.fn()} onSavedAndApply={vi.fn()} />);
    fireEvent.click(screen.getByTestId("btn-save-apply-indicator"));
    await waitFor(() => expect(screen.getByText(/Line 2/)).toBeTruthy());
    expect(createIndicator).not.toHaveBeenCalled();
    expect(screen.getByTestId("indicator-editor-panel")).toBeTruthy();
  });

  it("shows Edit Indicator copy when an existing indicator is passed", () => {
    render(
      <IndicatorEditorPanel
        initial={{
          id: "ind-1",
          name: "52-Week High Breakout [SCAN]",
          description: "",
          source_code: DEFAULT_INDICATOR_TEMPLATE,
          script_version: 6,
          language_mode: "pine_subset_v1",
          timeframe: "1D",
          validation_status: "valid",
          required_bars: 253,
        }}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onSavedAndApply={vi.fn()}
      />,
    );
    expect(screen.getByText("Edit Indicator")).toBeTruthy();
  });

  it("save and apply persists the indicator", async () => {
    validateIndicatorSource.mockResolvedValue({
      ok: true,
      status: "valid",
      errors: [],
      warnings: [],
      inputs: [],
      outputs: [{ name: "52W Breakout Signal", kind: "plot" }],
      required_bars: 253,
      required_symbols: ["NSE:CNX500"],
    });
    createIndicator.mockResolvedValue({
      id: "ind-1",
      name: "52-Week High Breakout [SCAN]",
      description: "",
      source_code: DEFAULT_INDICATOR_TEMPLATE,
      script_version: 6,
      language_mode: "pine_subset_v1",
      timeframe: "1D",
      validation_status: "valid",
      required_bars: 253,
    });
    const onSavedAndApply = vi.fn();
    render(<IndicatorEditorPanel onCancel={vi.fn()} onSaved={vi.fn()} onSavedAndApply={onSavedAndApply} />);
    fireEvent.click(screen.getByTestId("btn-save-apply-indicator"));
    await waitFor(() => expect(onSavedAndApply).toHaveBeenCalled());
    expect(validateIndicatorSource).toHaveBeenCalled();
    expect(createIndicator).toHaveBeenCalled();
    expect(updateIndicator).not.toHaveBeenCalled();
  });

  it("updates an existing same-name indicator instead of creating a duplicate", async () => {
    validateIndicatorSource.mockResolvedValue({
      ok: true,
      status: "valid",
      errors: [],
      warnings: [],
      inputs: [],
      outputs: [{ name: "52W Breakout Signal", kind: "plot" }],
      required_bars: 253,
      required_symbols: ["NSE:CNX500"],
    });
    fetchIndicators.mockResolvedValue([
      {
        id: "ind-existing",
        name: "52-Week High Breakout [SCAN]",
        description: "",
        source_code: DEFAULT_INDICATOR_TEMPLATE,
        script_version: 6,
        language_mode: "pine_subset_v1",
        timeframe: "1D",
        validation_status: "valid",
        required_bars: 253,
      },
    ]);
    updateIndicator.mockResolvedValue({
      id: "ind-existing",
      name: "52-Week High Breakout [SCAN]",
      description: "",
      source_code: DEFAULT_INDICATOR_TEMPLATE,
      script_version: 6,
      language_mode: "pine_subset_v1",
      timeframe: "1D",
      validation_status: "valid",
      required_bars: 253,
    });
    const onSavedAndApply = vi.fn();
    render(<IndicatorEditorPanel onCancel={vi.fn()} onSaved={vi.fn()} onSavedAndApply={onSavedAndApply} />);
    fireEvent.click(screen.getByTestId("btn-save-apply-indicator"));
    await waitFor(() => expect(onSavedAndApply).toHaveBeenCalled());
    expect(updateIndicator).toHaveBeenCalledWith(
      "ind-existing",
      expect.objectContaining({ name: "52-Week High Breakout [SCAN]" }),
    );
    expect(createIndicator).not.toHaveBeenCalled();
  });
});
