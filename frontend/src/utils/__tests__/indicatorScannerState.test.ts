import { afterEach, describe, expect, it } from "vitest";
import type { SavedIndicator } from "../../api_indicator_scanner";
import {
  INDICATOR_SCANNER_LAST_SCAN_ID_KEY,
  INDICATOR_SCANNER_STATE_KEY,
  loadIndicatorScannerState,
  saveIndicatorScannerState,
  uniqueIndicatorsById,
  uniqueIndicatorsByIdAndName,
} from "../indicatorScannerState";

function indicator(partial: Partial<SavedIndicator> & { id: string; name: string }): SavedIndicator {
  return {
    description: "",
    source_code: "indicator()",
    script_version: 6,
    language_mode: "pine_subset_v1",
    timeframe: "1D",
    validation_status: "valid",
    required_bars: 253,
    ...partial,
  };
}

describe("indicatorScannerState", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("deduplicates by id, keeping the newer record", () => {
    const rows = uniqueIndicatorsById([
      indicator({ id: "ind-1", name: "A", updated_at: "2026-01-01T00:00:00Z" }),
      indicator({ id: "ind-1", name: "A updated", updated_at: "2026-02-01T00:00:00Z" }),
      indicator({ id: "ind-2", name: "B" }),
      indicator({ id: "", name: "ignored" }),
    ]);
    expect(rows.map((row) => row.id)).toEqual(["ind-1", "ind-2"]);
    expect(rows[0].name).toBe("A updated");
  });

  it("collapses duplicate names after unique-by-id", () => {
    const rows = uniqueIndicatorsByIdAndName([
      indicator({ id: "a", name: "52-Week High Breakout [SCAN]", updated_at: "2026-01-01T00:00:00Z" }),
      indicator({ id: "b", name: "52-Week High Breakout [SCAN]", updated_at: "2026-08-01T00:00:00Z" }),
      indicator({ id: "c", name: "Custom RSI" }),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.map((row) => row.id).sort()).toEqual(["b", "c"]);
  });

  it("round-trips scan run state through localStorage", () => {
    saveIndicatorScannerState({
      selectedId: "ind-1",
      appliedIndicator: indicator({ id: "ind-1", name: "52-Week High Breakout [SCAN]" }),
      indicators: [
        indicator({ id: "ind-1", name: "52-Week High Breakout [SCAN]" }),
        indicator({ id: "ind-1", name: "52-Week High Breakout [SCAN]" }),
      ],
      timeframe: "1D",
      scanDate: "2026-08-28",
      filters: [{ field: "52W Breakout Signal", operator: "=", value: 1 }],
      scan: {
        id: "run-1",
        scan_id: "IND-20260829-001",
        indicator_name: "52-Week High Breakout [SCAN]",
        universe: "nse-755",
        universe_size: 755,
        timeframe: "1D",
        status: "completed",
        progress_pct: 100,
        processed_count: 755,
        total_count: 755,
        matched_count: 12,
      },
      results: [{ symbol: "RELIANCE", status: "ok", matched: true, outputs: { Close: 1400 } }],
      total: 12,
      page: 1,
      sortField: "symbol",
      sortDir: "asc",
      search: "",
      matchedOnly: true,
      diagnostics: { failed: 0, skipped: 3 },
    });

    expect(localStorage.getItem(INDICATOR_SCANNER_LAST_SCAN_ID_KEY)).toBe("IND-20260829-001");
    const loaded = loadIndicatorScannerState();
    expect(loaded?.scan?.scan_id).toBe("IND-20260829-001");
    expect(loaded?.scan?.indicator_id).toBe("ind-1");
    expect(loaded?.scan?.matched_count).toBe(12);
    expect(loaded?.results[0].symbol).toBe("RELIANCE");
    expect(loaded?.scansByIndicator?.["ind-1"]?.results[0].symbol).toBe("RELIANCE");
    expect(loaded?.diagnostics?.skipped).toBe(3);
    expect(loaded?.indicators).toHaveLength(1);
    expect(JSON.parse(localStorage.getItem(INDICATOR_SCANNER_STATE_KEY) || "{}").indicators).toHaveLength(1);
  });

  it("keeps the last scan for every strategy", () => {
    saveIndicatorScannerState({
      selectedId: "ind-2",
      appliedIndicator: indicator({ id: "ind-2", name: "RSI Oversold [SCAN]" }),
      indicators: [
        indicator({ id: "ind-1", name: "52-Week High Breakout [SCAN]" }),
        indicator({ id: "ind-2", name: "RSI Oversold [SCAN]" }),
      ],
      timeframe: "1D",
      scanDate: "2026-08-28",
      filters: [],
      scan: {
        id: "run-2",
        scan_id: "IND-B",
        indicator_id: "ind-2",
        indicator_name: "RSI Oversold [SCAN]",
        universe: "nse-755",
        universe_size: 755,
        timeframe: "1D",
        status: "completed",
        progress_pct: 100,
        processed_count: 755,
        total_count: 755,
        matched_count: 3,
      },
      results: [{ symbol: "TCS", status: "ok", matched: true, outputs: {} }],
      total: 3,
      page: 1,
      sortField: "symbol",
      sortDir: "asc",
      search: "",
      matchedOnly: false,
      diagnostics: null,
      scansByIndicator: {
        "ind-1": {
          scan: {
            id: "run-1",
            scan_id: "IND-A",
            indicator_id: "ind-1",
            indicator_name: "52-Week High Breakout [SCAN]",
            universe: "nse-755",
            universe_size: 755,
            timeframe: "1D",
            status: "completed",
            progress_pct: 100,
            processed_count: 755,
            total_count: 755,
            matched_count: 1,
          },
          results: [{ symbol: "RELIANCE", status: "ok", matched: true, outputs: {} }],
          total: 1,
          page: 1,
          scanDate: "2026-08-27",
          filters: [],
          diagnostics: null,
        },
      },
    });

    const loaded = loadIndicatorScannerState();
    expect(loaded?.scansByIndicator?.["ind-1"]?.results[0].symbol).toBe("RELIANCE");
    expect(loaded?.scansByIndicator?.["ind-1"]?.scan.scan_id).toBe("IND-A");
    expect(loaded?.scansByIndicator?.["ind-2"]?.results[0].symbol).toBe("TCS");
    expect(loaded?.scan?.scan_id).toBe("IND-B");
  });
});
