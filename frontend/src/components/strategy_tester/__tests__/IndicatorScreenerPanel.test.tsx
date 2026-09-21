import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IndicatorScreenerPanel } from "../IndicatorScreenerPanel";
import { saveIndicatorScannerState } from "../../../utils/indicatorScannerState";
import { currentCashSessionIST } from "../../../utils/tradingHours";

const fetchIndicators = vi.fn();
const startIndicatorScan = vi.fn();
const fetchIndicatorScan = vi.fn();
const fetchIndicatorScanResults = vi.fn();
const duplicateIndicator = vi.fn();
const archiveIndicator = vi.fn();
const cancelIndicatorScan = vi.fn();
const exportIndicatorScanCsv = vi.fn();
const fetchIndicatorScanDiagnostics = vi.fn();
const startIndicatorBacktest = vi.fn();
const fetchIndicatorBacktest = vi.fn();
const fetchIndicatorBacktestResults = vi.fn();
const seedLabIndicators = vi.fn(async () => ({ created: [], skipped: [], count: 0, indicators: [] }));

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
  startIndicatorBacktest: (...args: unknown[]) => startIndicatorBacktest(...args),
  fetchIndicatorBacktest: (...args: unknown[]) => fetchIndicatorBacktest(...args),
  fetchIndicatorBacktestResults: (...args: unknown[]) => fetchIndicatorBacktestResults(...args),
  seedLabIndicators: (...args: unknown[]) => seedLabIndicators(...args),
  fetchIndicatorTemplates: vi.fn(async () => []),
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
      summary: {
        positive_returns: 1,
        negative_returns: 1,
        top_positive: [
          { rank: 1, symbol: "RELIANCE", entry_price: 1000, exit_price: 1400, return_pct: 40, signal: "MATCH", key_filters: [] },
        ],
        top_negative: [
          { rank: 1, symbol: "IDEA", entry_price: 20, exit_price: 10, return_pct: -50, signal: "REJECT", key_filters: [] },
        ],
      },
    });
    fetchIndicatorScanDiagnostics.mockResolvedValue({
      total_symbols: 755,
      successful: 753,
      failed: 0,
      skipped: 2,
      as_of: "2026-08-28",
    });
    fetchIndicatorScanResults.mockImplementation(async (_id: string, params: { return_bucket?: string; signal?: string } = {}) => {
      if (params.return_bucket === "NEGATIVE") {
        return {
          total: 1,
          page: 1,
          page_size: 5,
          outputs: ["52W Breakout Signal", "Close", "Prior 252 High"],
          results: [
            {
              symbol: "IDEA",
              display_name: "Idea Ltd",
              status: "ok",
              matched: false,
              as_of: "2026-08-28",
              return_pct: -50,
              signal: "REJECT",
              outputs: { "52W Breakout Signal": 0, Close: 10, "Prior 252 High": 20 },
              ohlcv: { close: 10, volume: 1000 },
            },
          ],
        };
      }
      if (params.return_bucket === "POSITIVE") {
        return {
          total: 1,
          page: 1,
          page_size: 5,
          outputs: ["52W Breakout Signal", "Close", "Prior 252 High"],
          results: [
            {
              symbol: "RELIANCE",
              display_name: "Reliance Industries",
              status: "ok",
              matched: true,
              as_of: "2026-08-28",
              return_pct: 40,
              signal: "MATCH",
              outputs: { "52W Breakout Signal": 1, Close: 1400, "Prior 252 High": 1000 },
              ohlcv: { close: 1400, volume: 8000000 },
            },
          ],
        };
      }
      return {
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
            return_pct: 40,
            signal: "MATCH",
            outputs: { "52W Breakout Signal": 1, Close: 1400, "Prior 252 High": 1390 },
            ohlcv: { volume: 8000000 },
          },
        ],
      };
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

  it("shows the selected strategy's entry conditions instead of the aggregate signal", async () => {
    const withConditions = {
      ...applied,
      parsed_definition: {
        outputs: [
          { name: "LTM Eligible Signal", kind: "plot" },
          { name: "Momentum 252", kind: "plot" },
        ],
        entry_conditions: [
          { name: "Close > SMA 50" },
          { name: "SMA 50 > SMA 200" },
          { name: "RSI 14 > 55" },
          { name: "Volume > Average Volume 20" },
        ],
      },
    };
    fetchIndicators.mockResolvedValue([withConditions]);
    renderPanel({ appliedIndicator: withConditions });
    expect(await screen.findByTestId("indicator-strategy-conditions")).toBeTruthy();
    expect(screen.getAllByText("Close > SMA 50").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("SMA 50 > SMA 200").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("RSI 14 > 55").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Volume > Average Volume 20").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByLabelText("Filter output")).toBeNull();
    fireEvent.click(screen.getByTestId("btn-scan-indicator"));
    await waitFor(() => expect(startIndicatorScan).toHaveBeenCalled());
    expect(startIndicatorScan.mock.calls[0][1].filters).toEqual([
      { field: "LTM Eligible Signal", operator: "=", value: 1 },
    ]);
  });

  it("replaces strategy conditions when the selected indicator changes", async () => {
    const strategyA = {
      ...applied,
      id: "ind-a",
      name: "Strategy A",
      parsed_definition: {
        outputs: [{ name: "Eligible Signal", kind: "plot" }],
        entry_conditions: [{ name: "Close > SMA 50" }, { name: "RSI 14 > 55" }],
      },
    };
    const strategyB = {
      ...applied,
      id: "ind-b",
      name: "Strategy B",
      parsed_definition: {
        outputs: [{ name: "Eligible Signal", kind: "plot" }],
        entry_conditions: [{ name: "Close > EMA 20" }, { name: "RSI 14 > 60" }],
      },
    };
    fetchIndicators.mockResolvedValue([strategyA, strategyB]);
    renderPanel({ appliedIndicator: strategyA });
    expect((await screen.findAllByText("Close > SMA 50")).length).toBeGreaterThanOrEqual(1);
    fireEvent.change(screen.getByTestId("select-saved-indicator"), { target: { value: "ind-b" } });
    expect((await screen.findAllByText("Close > EMA 20")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("RSI 14 > 60").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Close > SMA 50")).toBeNull();
    expect(screen.queryByText("RSI 14 > 55")).toBeNull();
  });

  it("passes the selected indicator to Edit", async () => {
    const { onEditIndicator } = renderPanel();
    fireEvent.click(await screen.findByTestId("btn-edit-indicator"));
    expect(onEditIndicator).toHaveBeenCalledWith(expect.objectContaining({ id: "ind-1" }));
  });

  it("defaults As of to today's cash session even if localStorage still has yesterday", async () => {
    const todayIST = currentCashSessionIST();
    saveIndicatorScannerState({
      selectedId: "ind-1",
      appliedIndicator: applied,
      indicators: [applied],
      timeframe: "1D",
      scanDate: "2026-09-04",
      filters: [],
      scan: null,
      results: [],
      total: 0,
      page: 1,
      sortField: "symbol",
      sortDir: "asc",
      search: "",
      matchedOnly: true,
      diagnostics: null,
    });
    renderPanel();
    const dateInput = (await screen.findByTestId("input-indicator-scan-date")) as HTMLInputElement;
    expect(dateInput.value).toBe(todayIST);
    expect(dateInput.max).toBe(todayIST);
  });

  it("scans with the applied indicator and renders matching rows", async () => {
    renderPanel();
    fireEvent.click(await screen.findByTestId("btn-scan-indicator"));
    await waitFor(() => expect(startIndicatorScan).toHaveBeenCalled());
    expect(startIndicatorScan.mock.calls[0][0]).toBe("ind-1");
    expect(startIndicatorScan.mock.calls[0][1].filters).toEqual([
      { field: "52W Breakout Signal", operator: "=", value: 1 },
    ]);
    const todayIST = currentCashSessionIST();
    expect(startIndicatorScan.mock.calls[0][1].scan_date).toBe(todayIST);
    const dateInput = screen.getByTestId("input-indicator-scan-date") as HTMLInputElement;
    expect(dateInput.value).toBe(todayIST);
    expect(dateInput.max).toBe(todayIST);
    await waitFor(() => expect(screen.getByTestId("indicator-results-table").textContent).toContain("RELIANCE"));
    expect(screen.getByTestId("indicator-result-count").textContent).toContain("1");
    expect(screen.getByTestId("card-run-info").textContent).toMatch(/RUN ID:\s*IND-20260829-001/);
    expect(screen.getByTestId("card-run-info").textContent).toContain("Completed");
    expect(screen.getByTestId("run-scan-as-of").textContent).toContain("2026-08-28");
    expect(screen.getByTestId("card-scan-progress").textContent).toMatch(/100%/);
    expect(screen.getByTestId("card-run-summary")).toBeTruthy();
    expect(screen.getByTestId("card-strategy-builder")).toBeTruthy();
    expect(screen.getByTestId("card-top-positive")).toBeTruthy();
    expect(screen.getByTestId("card-top-negative")).toBeTruthy();
    expect(screen.getByTestId("card-filter-analytics")).toBeTruthy();
    expect(screen.getByTestId("card-filter-funnel")).toBeTruthy();
    expect(screen.getByTestId("card-signal-distribution")).toBeTruthy();
    expect(screen.getByTestId("pill-filter-matched").textContent).toContain("MATCHED");
    expect(screen.getByTestId("pill-filter-rejected").textContent).toContain("REJECTED");
    expect(screen.getByTestId("pill-filter-skipped").textContent).toContain("SKIPPED");
    expect(screen.getByTestId("row-top-positive-RELIANCE")).toBeTruthy();
    expect(screen.getByTestId("row-top-negative-IDEA")).toBeTruthy();
  });

  it("filters All Scanned Stock Results by MATCHED, REJECTED, and SKIPPED pills", async () => {
    renderPanel();
    fireEvent.click(await screen.findByTestId("btn-scan-indicator"));
    await waitFor(() => expect(screen.getByTestId("indicator-row-RELIANCE")).toBeTruthy());
    fetchIndicatorScanResults.mockClear();
    fireEvent.click(screen.getByTestId("pill-filter-matched"));
    await waitFor(() => expect(fetchIndicatorScanResults).toHaveBeenCalled());
    expect(fetchIndicatorScanResults.mock.calls.at(-1)?.[1]).toEqual(
      expect.objectContaining({ signal: "MATCH" }),
    );
    fireEvent.click(screen.getByTestId("pill-filter-rejected"));
    await waitFor(() =>
      expect(fetchIndicatorScanResults.mock.calls.at(-1)?.[1]).toEqual(expect.objectContaining({ signal: "REJECT" })),
    );
    fireEvent.click(screen.getByTestId("pill-filter-skipped"));
    await waitFor(() =>
      expect(fetchIndicatorScanResults.mock.calls.at(-1)?.[1]).toEqual(expect.objectContaining({ signal: "SKIPPED" })),
    );
  });

  it("shows a closed-session note when the scan bar is the last 1D session", async () => {
    fetchIndicatorScan.mockResolvedValue({
      id: "run-1",
      scan_id: "IND-20260905-001",
      status: "completed",
      stage: "completed",
      universe_size: 750,
      total_count: 750,
      processed_count: 750,
      progress_pct: 100,
      matched_count: 89,
      as_of: "2026-09-04",
      success_count: 710,
      failed_count: 0,
      skipped_count: 40,
      indicator_name: applied.name,
      universe: "nse-755",
      timeframe: "1D",
      started_at: "2026-09-05T03:44:00.000Z",
      completed_at: "2026-09-05T03:45:00.000Z",
      elapsed_seconds: 40,
      summary: {
        scan_as_of: "2026-09-04",
        requested_as_of: "2026-09-05",
        scan_bar_note: "NSE cash market was closed on 2026-09-05. Scan bar is the last 1D session 2026-09-04.",
      },
    });
    renderPanel();
    fireEvent.click(await screen.findByTestId("btn-scan-indicator"));
    await waitFor(() => expect(screen.getByTestId("scan-bar-note").textContent).toMatch(/closed on 2026-09-05/));
    expect(screen.getByTestId("run-scan-as-of").textContent).toContain("2026-09-04");
  });

  it("shows fetching current market data before scanning symbols", async () => {
    const fetching = {
      id: "run-1",
      scan_id: "IND-20260909-001",
      status: "running",
      stage: "fetching_current_data",
      universe_size: 750,
      total_count: 750,
      processed_count: 0,
      progress_pct: 2,
      matched_count: 0,
      indicator_name: applied.name,
      universe: "nse-755",
      timeframe: "1D",
      started_at: "2026-09-09T04:00:00.000Z",
    };
    startIndicatorScan.mockResolvedValue(fetching);
    fetchIndicatorScan.mockResolvedValue(fetching);
    renderPanel();
    fireEvent.click(await screen.findByTestId("btn-scan-indicator"));
    await waitFor(() => expect(screen.getByTestId("btn-scan-indicator").textContent).toMatch(/Fetching data/));
    expect(screen.getByTestId("card-scan-progress").textContent).toMatch(/Fetching current market data/);
  });

  it("opens stock details with the indicator scan id, not a Strategy Tester run", async () => {
    const { navigate } = renderPanel();
    fireEvent.click(await screen.findByTestId("btn-scan-indicator"));
    await waitFor(() => expect(screen.getByTestId("indicator-row-RELIANCE")).toBeTruthy());
    fireEvent.click(screen.getByTestId("indicator-row-RELIANCE"));
    expect(navigate).toHaveBeenCalledWith(
      expect.stringContaining("/stock/RELIANCE"),
      expect.objectContaining({
        state: expect.objectContaining({ runId: "IND-20260829-001" }),
      }),
    );
    expect(String(navigate.mock.calls[0][0])).toContain("runId=IND-20260829-001");
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

  it("does not keep polling a stale running scan restored from localStorage", async () => {
    saveIndicatorScannerState({
      selectedId: "ind-1",
      appliedIndicator: applied,
      indicators: [applied],
      timeframe: "1D",
      scanDate: "2026-08-31",
      filters: [],
      scan: {
        id: "run-zombie",
        scan_id: "IND-20260831-003",
        indicator_name: applied.name,
        universe: "nse-755",
        universe_size: 750,
        timeframe: "1D",
        status: "running",
        stage: "repairing_market_data",
        progress_pct: 0,
        processed_count: 0,
        total_count: 750,
        matched_count: 0,
        started_at: "2026-08-31T05:26:40.000Z",
      },
      results: [],
      total: 0,
      page: 1,
      sortField: "symbol",
      sortDir: "asc",
      search: "",
      matchedOnly: false,
      diagnostics: null,
    });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("card-run-info").textContent).toMatch(/Failed/));
    expect(screen.getByTestId("card-run-info").textContent).toMatch(/interrupted/i);
    expect(fetchIndicatorScan).not.toHaveBeenCalled();
    expect(startIndicatorScan).not.toHaveBeenCalled();
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

  it("launches and renders LEAN backtest results on saved indicator", async () => {
    startIndicatorBacktest.mockResolvedValue({
      jobId: "LEAN-TEST-001",
      strategyId: "09_52w_breakout",
      strategyName: applied.name,
      status: "COMPLETED",
      progressPct: 100,
      stage: "Completed",
      request: {},
      result: {
        jobId: "LEAN-TEST-001",
        strategyId: "09_52w_breakout",
        strategyName: applied.name,
        engine: "LEAN",
        status: "COMPLETED",
        startDate: "2020-01-01",
        endDate: "2026-09-08",
        symbols: ["ALL_755"],
        summary: {
          initialCapital: 100000,
          finalEquity: 245300,
          netProfit: 145300,
          netProfitPct: 145.3,
          cagr: 0.182,
          sharpeRatio: 1.45,
          sortinoRatio: 2.1,
          maximumDrawdown: 18500,
          maximumDrawdownPct: 0.125,
          calmarRatio: 1.45,
          totalTrades: 42,
          winningTrades: 28,
          losingTrades: 14,
          winRate: 0.667,
          profitFactor: 2.35,
          averageTrade: 3459.5,
          averageWinningTrade: 6800.0,
          averageLosingTrade: -2100.0,
          expectancy: 1.25,
          totalCommission: 850,
          totalSlippage: 850,
          executionModel: "LEAN NextBarOpen",
          dataSource: "Trading Labs NSE Data",
          dataCoverageRatio: 0.99,
          tradingDaysCount: 1512,
        },
        trades: [
          {
            tradeId: 1,
            symbol: "RELIANCE",
            entryDate: "2021-03-15",
            entryPrice: 1950.0,
            exitDate: "2021-08-20",
            exitPrice: 2250.0,
            quantity: 50,
            direction: "LONG",
            grossPnL: 15000.0,
            commission: 40.0,
            slippage: 40.0,
            netPnL: 14920.0,
            returnPct: 0.1538,
            holdingPeriod: 105,
            entryReason: "52W High Breakout",
            exitReason: "Trailing Stop 20%",
            isOpen: false,
          },
        ],
        equityCurve: [
          { date: "2020-01-01", equity: 100000, cash: 100000, investedCapital: 0, drawdown: 0, drawdownPct: 0 },
          { date: "2026-09-08", equity: 245300, cash: 245300, investedCapital: 0, drawdown: 0, drawdownPct: 0 },
        ],
        positions: [],
        runtimeMetrics: {},
      },
    });

    renderPanel();
    const btnOpen = screen.getByTestId("btn-open-lean-backtest");
    expect(btnOpen).toBeDefined();

    fireEvent.click(btnOpen);
    expect(screen.getByTestId("indicator-lean-backtest-modal")).toBeDefined();

    fireEvent.click(screen.getByTestId("btn-confirm-start-lean-backtest"));

    await waitFor(() => {
      expect(startIndicatorBacktest).toHaveBeenCalledWith(
        "ind-1",
        expect.objectContaining({
          start_date: "2020-01-01",
          initial_capital: 100000,
          engine: "LEAN",
          max_positions: 10,
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("indicator-lean-backtest-panel")).toBeDefined();
    });

    expect(screen.getByTestId("lean-kpi-grid")).toBeDefined();
    expect(screen.getByTestId("lean-equity-chart")).toBeDefined();
    expect(screen.getByTestId("lean-trades-table")).toBeDefined();
    expect(screen.getByText("RELIANCE")).toBeDefined();
    expect(screen.getByText("+15.38%")).toBeDefined();
  });

  it("warns when EMA 20 = 1 is used as a Pine Screener filter and offers the signal column", async () => {
    const pulse = {
      ...applied,
      id: "ind-pulse",
      name: "Momentum Pulse Finder",
      parsed_definition: {
        outputs: [
          { name: "EMA 20", kind: "plot" },
          { name: "Momentum Signal", kind: "plotshape" },
          { name: "Momentum Pulse", kind: "alertcondition" },
        ],
        entry_conditions: [{ name: "Close > EMA 20" }, { name: "RSI 14 crosses above 50" }],
      },
    };
    fetchIndicators.mockResolvedValue([pulse]);
    saveIndicatorScannerState({
      selectedId: "ind-pulse",
      appliedIndicator: pulse,
      indicators: [pulse],
      timeframe: "1D",
      scanDate: currentCashSessionIST(),
      filters: [{ field: "EMA 20", operator: ">=", value: 1 }],
      scan: null,
      results: [],
      total: 0,
      page: 1,
      sortField: "symbol",
      sortDir: "asc",
      search: "",
      matchedOnly: false,
      diagnostics: null,
    });
    renderPanel({ appliedIndicator: pulse });
    expect(await screen.findByTestId("pine-screener-filter-warning")).toBeTruthy();
    expect(screen.getByTestId("pine-screener-filter-warning").textContent).toMatch(/No symbols match your filters/i);
    const valueInput = screen.getByLabelText("Filter value") as HTMLInputElement;
    expect((screen.getByLabelText("Filter operator") as HTMLSelectElement).value).toBe("=");
    expect(valueInput.value).toBe("1");
    fireEvent.click(screen.getByTestId("btn-use-screener-signal-filter"));
    expect((screen.getByLabelText("Filter output") as HTMLSelectElement).value).toBe("Momentum Signal");
    expect((screen.getByLabelText("Filter operator") as HTMLSelectElement).value).toBe("is_true");
    fireEvent.click(screen.getByTestId("btn-scan-indicator"));
    await waitFor(() => expect(startIndicatorScan).toHaveBeenCalled());
    expect(startIndicatorScan.mock.calls[0][1].filters).toEqual([
      { field: "Momentum Signal", operator: "is_true" },
    ]);
  });

  it("opens Manual setup from Momentum Signal and saves the selected condition", async () => {
    const pulse = {
      ...applied,
      id: "ind-pulse",
      name: "Momentum Pulse Finder",
      parsed_definition: {
        outputs: [
          { name: "EMA 20", kind: "plot" },
          { name: "Momentum Signal", kind: "plotshape" },
          { name: "Momentum Pulse", kind: "alertcondition" },
        ],
        entry_conditions: [{ name: "Close > EMA 20" }, { name: "RSI 14 crosses above 50" }],
      },
    };
    fetchIndicators.mockResolvedValue([pulse]);
    renderPanel({ appliedIndicator: pulse });
    fireEvent.click(await screen.findByTestId("screener-column-Momentum Signal"));
    expect(await screen.findByTestId("signal-manual-setup")).toBeTruthy();
    expect(screen.getByTestId("signal-manual-setup-name").textContent).toBe("MOMENTUM SIGNAL");
    fireEvent.click(screen.getByTestId("signal-condition-trigger"));
    expect(await screen.findByTestId("signal-condition-dropdown")).toBeTruthy();
    expect(screen.getByTestId("signal-condition-above").textContent).toMatch(/Above/);
    expect(screen.getByTestId("signal-condition-above_or_equal").textContent).toMatch(/Above or equal/);
    expect(screen.getByTestId("signal-condition-below").textContent).toMatch(/Below/);
    expect(screen.getByTestId("signal-condition-below_or_equal").textContent).toMatch(/Below or equal/);
    expect(screen.getByTestId("signal-condition-crosses").textContent).toMatch(/Crosses/);
    expect(screen.getByTestId("signal-condition-crosses_up").textContent).toMatch(/Crosses up/);
    expect(screen.getByTestId("signal-condition-crosses_down").textContent).toMatch(/Crosses down/);
    expect(screen.getByTestId("signal-condition-between").textContent).toMatch(/Between/);
    expect(screen.getByTestId("signal-condition-outside").textContent).toMatch(/Outside/);
    expect(screen.getByTestId("signal-condition-equal").textContent).toMatch(/Equal/);
    fireEvent.keyDown(document, { key: "ArrowDown" });
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(screen.getByTestId("signal-condition-below").className).toMatch(/is-active/);
    fireEvent.keyDown(document, { key: "ArrowDown" });
    fireEvent.keyDown(document, { key: "ArrowDown" });
    fireEvent.keyDown(document, { key: "ArrowDown" });
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(screen.getByTestId("signal-condition-crosses_down").className).toMatch(/is-active/);
    fireEvent.click(screen.getByTestId("signal-condition-below"));
    fireEvent.change(screen.getByTestId("signal-value-input"), { target: { value: "0" } });
    fireEvent.click(screen.getByTestId("signal-setup-apply"));
    await waitFor(() => expect(screen.queryByTestId("signal-manual-setup")).toBeNull());
    fireEvent.click(screen.getByTestId("screener-column-Momentum Signal"));
    expect((await screen.findByTestId("signal-condition-trigger")).textContent).toMatch(/Below/);
    expect((screen.getByTestId("signal-value-input") as HTMLInputElement).value).toBe("0");
    fireEvent.click(screen.getByTestId("signal-setup-apply"));
    fireEvent.click(screen.getByTestId("btn-scan-indicator"));
    await waitFor(() => expect(startIndicatorScan).toHaveBeenCalled());
    expect(startIndicatorScan.mock.calls[0][1].filters).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          field: "Momentum Signal",
          operator: "<",
          value: 0,
          condition: "below",
          setup_type: "signal",
        }),
      ]),
    );
  });

  it("opens a compact True/Remove menu for Momentum Pulse and can remove it", async () => {
    const pulse = {
      ...applied,
      id: "ind-pulse",
      name: "Momentum Pulse Finder",
      parsed_definition: {
        outputs: [
          { name: "EMA 20", kind: "plot" },
          { name: "Momentum Signal", kind: "plotshape" },
          { name: "Momentum Pulse", kind: "alertcondition" },
        ],
        entry_conditions: [{ name: "Close > EMA 20" }, { name: "RSI 14 crosses above 50" }],
      },
    };
    fetchIndicators.mockResolvedValue([pulse]);
    renderPanel({ appliedIndicator: pulse });
    fireEvent.click(await screen.findByTestId("screener-column-Momentum Pulse"));
    expect(await screen.findByTestId("pulse-dropdown")).toBeTruthy();
    expect(screen.queryByTestId("signal-manual-setup")).toBeNull();
    expect(screen.getByTestId("pulse-option-true").textContent).toBe("True");
    fireEvent.click(screen.getByTestId("pulse-option-true"));
    fireEvent.click(screen.getByTestId("screener-column-Momentum Pulse"));
    fireEvent.click(await screen.findByTestId("pulse-option-remove"));
    await waitFor(() => expect(screen.queryByTestId("screener-column-Momentum Pulse")).toBeNull());
    expect(screen.getByTestId("screener-column-Momentum Signal")).toBeTruthy();
  });

  it("filters scanned results by search query and does not revert to all stocks", async () => {
    saveIndicatorScannerState({
      selectedId: "ind-1",
      appliedIndicator: applied,
      indicators: [applied],
      timeframe: "1D",
      scanDate: "2026-08-29",
      filters: [],
      scan: {
        id: "run-search-test",
        scan_id: "IND-20260829-SEARCH",
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
        started_at: "2026-08-29T05:26:40.000Z",
        completed_at: "2026-08-29T05:27:10.000Z",
      },
      results: [
        {
          symbol: "TCS",
          display_name: "Tata Consultancy Services",
          status: "ok",
          matched: true,
          as_of: "2026-08-28",
          outputs: { "52W Breakout Signal": 1, Close: 4200, "Prior 252 High": 4150 },
        },
        {
          symbol: "INFY",
          display_name: "Infosys Ltd",
          status: "ok",
          matched: false,
          as_of: "2026-08-28",
          outputs: { "52W Breakout Signal": 0, Close: 1800, "Prior 252 High": 1900 },
        },
      ],
      total: 2,
      page: 1,
      sortField: "symbol",
      sortDir: "asc",
      search: "",
      matchedOnly: false,
      diagnostics: null,
    });
    renderPanel();
    const table = screen.getByTestId("indicator-results-table");
    await waitFor(() => expect(table.textContent).toContain("TCS"));
    expect(table.textContent).toContain("INFY");

    const searchInput = screen.getByTestId("input-search-stocks") as HTMLInputElement;
    fireEvent.change(searchInput, { target: { value: "TCS" } });

    await waitFor(() => {
      expect(table.textContent).toContain("TCS");
      expect(table.textContent).not.toContain("INFY");
    });
  });
});
