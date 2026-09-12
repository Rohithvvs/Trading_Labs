import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IndicatorScreenerPanel } from "../IndicatorScreenerPanel";
import { saveIndicatorScannerState } from "../../../utils/indicatorScannerState";

const fetchIndicators = vi.fn();
const startIndicatorScan = vi.fn();
const fetchIndicatorScan = vi.fn();
const fetchIndicatorScanResults = vi.fn();
const duplicateIndicator = vi.fn();
const archiveIndicator = vi.fn();
const cancelIndicatorScan = vi.fn();
const exportIndicatorScanCsv = vi.fn();
const fetchIndicatorScanDiagnostics = vi.fn();

vi.mock("../../../api_strategy_tester", () => ({
  fetchStrategyCatalog: vi.fn(async () => ({
    universe_count: 755,
    universe_label: "755 Stocks",
    universe_symbols: [
      { symbol: "360ONE", company: "360 One Wam Limited" },
      { symbol: "3MINDIA", company: "3M India Limited" },
    ],
  })),
}));

vi.mock("../../../api_indicator_scanner", () => ({
  fetchIndicators: (...args: unknown[]) => fetchIndicators(...args),
  startIndicatorScan: (...args: unknown[]) => startIndicatorScan(...args),
  fetchIndicatorScan: (...args: unknown[]) => fetchIndicatorScan(...args),
  fetchIndicatorScanResults: (...args: unknown[]) => fetchIndicatorScanResults(...args),
  duplicateIndicator: (...args: unknown[]) => duplicateIndicator(...args),
  archiveIndicator: (...args: unknown[]) => archiveIndicator(...args),
  cancelIndicatorScan: (...args: unknown[]) => cancelIndicatorScan(...args),
  exportIndicatorScanCsv: (...args: unknown[]) => exportIndicatorScanCsv(...args),
  fetchIndicatorScanDiagnostics: (...args: unknown[]) => fetchIndicatorScanDiagnostics(...args),
}));

const applied = {
  id: "ind-1",
  name: "52-Week High Breakout [SCAN]",
  description: "Daily 52-week high breakout",
  source_code: "indicator()",
  script_version: 6,
  language_mode: "pine_subset_v1",
  timeframe: "1D",
  parsed_definition: {
    outputs: [
      { name: "52W Breakout Signal" },
      { name: "Close" },
      { name: "Prior 252 High" },
    ],
  },
  validation_status: "valid",
  required_bars: 253,
};

function renderPanel(overrides: Partial<React.ComponentProps<typeof IndicatorScreenerPanel>> = {}) {
  const notify = vi.fn();
  const onAddIndicator = vi.fn();
  const onEditIndicator = vi.fn();
  const navigate = vi.fn();
  const result = render(
    <IndicatorScreenerPanel
      universeCount={755}
      appliedIndicator={applied}
      navigate={navigate}
      onAddIndicator={onAddIndicator}
      onEditIndicator={onEditIndicator}
      notify={notify}
      {...overrides}
    />,
  );
  return { ...result, notify, onAddIndicator, onEditIndicator, navigate };
}

describe("IndicatorScreenerPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    fetchIndicators.mockResolvedValue([applied]);
    startIndicatorScan.mockResolvedValue({
      id: "run-1",
      scan_id: "IND-20260829-001",
      status: "queued",
      universe_size: 755,
      total_count: 755,
      processed_count: 0,
      progress_pct: 0,
      matched_count: 0,
      indicator_name: applied.name,
      universe: "nse-755",
      timeframe: "1D",
      started_at: "2026-08-28T18:23:00.000Z",
    });
    fetchIndicatorScan.mockResolvedValue({
      id: "run-1",
      scan_id: "IND-20260829-001",
      status: "completed",
      stage: "completed",
      universe_size: 755,
      total_count: 755,
      processed_count: 755,
      progress_pct: 100,
      matched_count: 1,
      as_of: "2026-08-28",
      success_count: 755,
      failed_count: 0,
      skipped_count: 0,
      indicator_name: applied.name,
      universe: "nse-755",
      timeframe: "1D",
      started_at: "2026-08-28T18:23:00.000Z",
      completed_at: "2026-08-28T18:24:02.000Z",
      elapsed_seconds: 62,
    });
    fetchIndicatorScanDiagnostics.mockResolvedValue({
      total_symbols: 755,
      successful: 753,
      failed: 0,
      skipped: 2,
      as_of: "2026-08-28",
    });
    fetchIndicatorScanResults.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 50,
      outputs: ["52W Breakout Signal", "Close", "Prior 252 High"],
      results: [
        {
          symbol: "RELIANCE",
          display_name: "Reliance Industries",
          status: "ok",
          matched: true,
          as_of: "2026-08-28",
          outputs: { "52W Breakout Signal": 1, Close: 1400, "Prior 252 High": 1390 },
          ohlcv: { volume: 8000000 },
        },
      ],
    });
  });

  it("shows an empty library prompt when no indicator is applied", async () => {
    fetchIndicators.mockResolvedValue([]);
    renderPanel({ appliedIndicator: null });
    expect(await screen.findByTestId("indicator-empty-library")).toBeTruthy();
    expect(await screen.findByTestId("btn-scan-indicator")).toBeTruthy();
    expect(await screen.findByTestId("indicator-row-360ONE")).toBeTruthy();
    expect(screen.getByTestId("btn-add-indicator").textContent).toMatch(/Add indicator/i);
  });

  it("selects the applied indicator and its output columns after save and apply", async () => {
    renderPanel();
    await waitFor(() => expect((screen.getByTestId("select-saved-indicator") as HTMLSelectElement).value).toBe("ind-1"));
    expect(screen.getByTestId("indicator-absorbed-columns").textContent).toContain("52W Breakout Signal");
    expect(screen.getByTestId("indicator-absorbed-columns").textContent).toContain("Prior 252 High");
    expect((screen.getByLabelText("Filter output") as HTMLSelectElement).value).toBe("52W Breakout Signal");
  });

  it("passes the selected indicator to Edit", async () => {
    const { onEditIndicator } = renderPanel();
    fireEvent.click(await screen.findByTestId("btn-edit-indicator"));
    expect(onEditIndicator).toHaveBeenCalledWith(expect.objectContaining({ id: "ind-1" }));
  });

  it("scans with the applied indicator and renders matching rows", async () => {
    renderPanel();
    fireEvent.click(await screen.findByTestId("btn-scan-indicator"));
    await waitFor(() => expect(startIndicatorScan).toHaveBeenCalled());
    expect(startIndicatorScan.mock.calls[0][0]).toBe("ind-1");
    expect(startIndicatorScan.mock.calls[0][1].filters).toEqual([
      { field: "52W Breakout Signal", operator: "=", value: 1 },
    ]);
    expect(startIndicatorScan.mock.calls[0][1].scan_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(screen.getByTestId("input-indicator-scan-date")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("indicator-results-table").textContent).toContain("RELIANCE"));
    expect(screen.getByTestId("indicator-result-count").textContent).toContain("1");
    expect(screen.getByTestId("card-run-info").textContent).toMatch(/RUN ID:\s*IND-20260829-001/);
    expect(screen.getByTestId("card-run-info").textContent).toContain("Completed");
    expect(screen.getByTestId("run-scan-as-of").textContent).toContain("2026-08-28");
    expect(screen.getByTestId("card-scan-progress").textContent).toMatch(/100%/);
  });

  it("warns before scanning when no indicator is selected", async () => {
    fetchIndicators.mockResolvedValue([]);
    const { notify } = renderPanel({ appliedIndicator: null });
    fireEvent.click(await screen.findByTestId("btn-scan-indicator"));
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ title: "Add an indicator before scanning." }));
    expect(startIndicatorScan).not.toHaveBeenCalled();
  });

  it("auto-selects the first saved indicator so Scan can run", async () => {
    const { notify } = renderPanel({ appliedIndicator: null });
    await waitFor(() => expect((screen.getByTestId("select-saved-indicator") as HTMLSelectElement).value).toBe("ind-1"));
    fireEvent.click(screen.getByTestId("btn-scan-indicator"));
    await waitFor(() => expect(startIndicatorScan).toHaveBeenCalled());
    expect(startIndicatorScan.mock.calls[0][0]).toBe("ind-1");
    expect(notify).not.toHaveBeenCalledWith(expect.objectContaining({ title: "Add an indicator before scanning." }));
  });

  it("deduplicates saved indicators with the same name in the dropdown", async () => {
    fetchIndicators.mockResolvedValue([
      applied,
      { ...applied, id: "ind-2", updated_at: "2026-01-01T00:00:00Z" },
      { ...applied, id: "ind-1", updated_at: "2026-08-01T00:00:00Z" },
    ]);
    renderPanel();
    const select = (await screen.findByTestId("select-saved-indicator")) as HTMLSelectElement;
    await waitFor(() => expect([...select.options].filter((opt) => opt.value).map((opt) => opt.text)).toEqual(["52-Week High Breakout [SCAN]"]));
    expect(select.options).toHaveLength(1);
  });

  it("restores the completed scan from localStorage without starting a new scan", async () => {
    saveIndicatorScannerState({
      selectedId: "ind-1",
      appliedIndicator: applied,
      indicators: [applied],
      timeframe: "1D",
      scanDate: "2026-08-28",
      filters: [{ field: "52W Breakout Signal", operator: "=", value: 1 }],
      scan: {
        id: "run-1",
        scan_id: "IND-20260829-001",
        indicator_name: applied.name,
        universe: "nse-755",
        universe_size: 755,
        timeframe: "1D",
        status: "completed",
        stage: "completed",
        progress_pct: 100,
        processed_count: 755,
        total_count: 755,
        matched_count: 1,
        failed_count: 0,
        skipped_count: 0,
        as_of: "2026-08-28",
        started_at: "2026-08-28T18:23:00.000Z",
        completed_at: "2026-08-28T18:24:02.000Z",
        elapsed_seconds: 62,
      },
      results: [
        {
          symbol: "RELIANCE",
          display_name: "Reliance Industries",
          status: "ok",
          matched: true,
          as_of: "2026-08-28",
          outputs: { "52W Breakout Signal": 1, Close: 1400, "Prior 252 High": 1390 },
        },
      ],
      total: 1,
      page: 1,
      sortField: "symbol",
      sortDir: "asc",
      search: "",
      matchedOnly: true,
      diagnostics: { failed: 0, skipped: 2, successful: 753, total_symbols: 755 },
    });
    renderPanel();
    expect(screen.getByTestId("card-run-info").textContent).toMatch(/RUN ID:\s*IND-20260829-001/);
    expect(screen.getByTestId("card-scan-progress").textContent).toMatch(/100%/);
    expect(screen.getByTestId("card-scan-progress").textContent).toMatch(/MATCHED/);
    expect(screen.getByTestId("card-scan-progress").textContent).toContain("1");
    await waitFor(() => expect(screen.getByTestId("indicator-results-table").textContent).toContain("RELIANCE"));
    expect(startIndicatorScan).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("btn-indicator-diagnostics"));
    await waitFor(() => expect(screen.getByTestId("indicator-diagnostics").textContent).toContain("Skipped"));
  });

  it("replaces the restored run when Scan is clicked", async () => {
    saveIndicatorScannerState({
      selectedId: "ind-1",
      appliedIndicator: applied,
      indicators: [applied],
      timeframe: "1D",
      scanDate: "2026-08-28",
      filters: [{ field: "52W Breakout Signal", operator: "=", value: 1 }],
      scan: {
        id: "run-old",
        scan_id: "IND-OLD-001",
        indicator_name: applied.name,
        universe: "nse-755",
        universe_size: 755,
        timeframe: "1D",
        status: "completed",
        progress_pct: 100,
        processed_count: 755,
        total_count: 755,
        matched_count: 4,
      },
      results: [{ symbol: "TCS", status: "ok", matched: true, outputs: {} }],
      total: 4,
      page: 1,
      sortField: "symbol",
      sortDir: "asc",
      search: "",
      matchedOnly: true,
      diagnostics: null,
    });
    startIndicatorScan.mockResolvedValue({
      id: "run-2",
      scan_id: "IND-20260829-002",
      status: "queued",
      universe_size: 755,
      total_count: 755,
      processed_count: 0,
      progress_pct: 0,
      matched_count: 0,
      indicator_name: applied.name,
      universe: "nse-755",
      timeframe: "1D",
      started_at: "2026-08-28T19:00:00.000Z",
    });
    fetchIndicatorScan.mockResolvedValue({
      id: "run-2",
      scan_id: "IND-20260829-002",
      status: "completed",
      stage: "completed",
      universe_size: 755,
      total_count: 755,
      processed_count: 755,
      progress_pct: 100,
      matched_count: 1,
      as_of: "2026-08-28",
      success_count: 755,
      failed_count: 0,
      skipped_count: 0,
      indicator_name: applied.name,
      universe: "nse-755",
      timeframe: "1D",
      started_at: "2026-08-28T19:00:00.000Z",
      completed_at: "2026-08-28T19:01:02.000Z",
      elapsed_seconds: 62,
    });
    renderPanel();
    expect(screen.getByTestId("card-run-info").textContent).toMatch(/IND-OLD-001/);
    fireEvent.click(screen.getByTestId("btn-scan-indicator"));
    await waitFor(() => expect(startIndicatorScan).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("card-run-info").textContent).toMatch(/IND-20260829-002/));
    expect(screen.getByTestId("card-run-info").textContent).not.toMatch(/IND-OLD-001/);
  });
});
