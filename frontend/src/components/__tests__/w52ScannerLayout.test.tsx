import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { W52RejectionBreakdown } from "../W52RejectionBreakdown";
import { W52ScanSummary } from "../W52ScanSummary";

describe("52-Week High Breakout scanner layout", () => {
  const src = readFileSync(resolve(__dirname, "../../App.tsx"), "utf8");

  it("keeps both scanner engines in the strategy tablist", () => {
    expect(src).toContain('display_name: "Long-Term Buy & Hold Momentum"');
    expect(src).toContain('display_name: "52-Week High Breakout"');
    expect(src).toContain("scanner-strategy-${s.id}");
  });

  it("renders components in order: CandidateTable -> W52ReturnBoards -> W52RejectionBreakdown -> W52ScanSummary", () => {
    const candidateTable = src.indexOf("rows={w52CandidateRows}");
    const returnBoards = src.indexOf("<W52ReturnBoards");
    const rejection = src.indexOf("<W52RejectionBreakdown");
    const summary = src.indexOf("<W52ScanSummary");

    expect(candidateTable).toBeGreaterThan(-1);
    expect(returnBoards).toBeGreaterThan(candidateTable);
    expect(rejection).toBeGreaterThan(returnBoards);
    expect(summary).toBeGreaterThan(rejection);
    expect(src.split("<W52ScanSummary").length - 1).toBe(1);
    expect(src.split("<W52RejectionBreakdown").length - 1).toBe(1);
    expect(src.split("<W52ReturnBoards").length - 1).toBe(1);
  });

  it("places rejection breakdown before the scan summary in the DOM", () => {
    render(
      <>
        <W52RejectionBreakdown
          buckets={[{ code: "other", label: "Other", count: 1, pct: 1.5 }]}
        />
        <W52ScanSummary
          payload={{
            book_status: "ACTIVE",
            survivorship_biased: true,
            data_source: "daily_ohlcv",
            evaluation_date: "2026-08-21",
            evaluation_bar: "completed_history",
            summary: {
              total: 755,
              data_valid: 744,
              evaluated: 744,
              final_candidates: 10,
              screener_matches: 12,
              buy: 5,
              hold: 5,
              watch: 0,
              reject: 734,
              data_failures: 11,
            },
            free_slots: 0,
            holdings: [{ symbol: "TEST-EQ", hwm: 100, tsl: 90, unrealized_pct: 0.1 }],
            limitations: ["Look-ahead on signal close"],
          }}
        />
      </>,
    );
    const rejection = screen.getByTestId("w52-rejection-breakdown");
    const summary = screen.getByTestId("w52-scan-summary");
    expect(rejection.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("52-WEEK HIGH BREAKOUT REJECTION BREAKDOWN")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "52-Week High Breakout" })).toBeTruthy();
    expect(screen.getByText("Current holdings")).toBeTruthy();
    expect(screen.getByText("Known limitations")).toBeTruthy();
  });
});
