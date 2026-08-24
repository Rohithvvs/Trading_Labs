import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScannerProgress } from "../ScannerProgress";

describe("ScannerProgress", () => {
  it("shows strategy-specific in-progress title and backend stage", () => {
    render(
      <ScannerProgress
        title="LTM SCAN IN PROGRESS"
        data={{ stage: "Running portfolio backtest...", progress: 40, current_symbol: "" }}
        error={null}
        startTime={Date.now() - 5000}
      />,
    );
    expect(screen.getByText("LTM SCAN IN PROGRESS")).toBeTruthy();
    expect(screen.getByText(/Current stage: Running portfolio backtest/)).toBeTruthy();
    expect(screen.getByText("40%")).toBeTruthy();
    expect(screen.queryByText("STR-500")).toBeNull();
  });

  it("shows failed state without claiming completion", () => {
    render(
      <ScannerProgress
        title="52-WEEK HIGH BREAKOUT SCAN IN PROGRESS"
        data={{ stage: "Evaluating universe...", progress: 5 }}
        error="MARKET_DATA_STALE"
        startTime={Date.now()}
      />,
    );
    expect(screen.getByText("SCAN FAILED")).toBeTruthy();
    expect(screen.getByText(/MARKET_DATA_STALE/)).toBeTruthy();
  });

  it("shows a compact completed banner with backend completed_at", () => {
    render(
      <ScannerProgress
        title="52-WEEK HIGH BREAKOUT SCAN COMPLETED"
        data={{ stage: "completed", progress: 100 }}
        error={null}
        startTime={null}
        variant="completed"
        completedAt="2026-08-16T10:11:00.000Z"
      />,
    );
    expect(screen.getByText("52-WEEK HIGH BREAKOUT SCAN COMPLETED")).toBeTruthy();
    expect(screen.getByText(/Completed:/)).toBeTruthy();
    expect(screen.queryByText(/SCAN IN PROGRESS/)).toBeNull();
  });

  it("formats elapsed as 00m 08s", () => {
    render(
      <ScannerProgress
        title="LTM SCAN IN PROGRESS"
        data={{ stage: "Scanning universe...", progress: 18, current_symbol: "RELIANCE" }}
        error={null}
        startTime={Date.now() - 8000}
      />,
    );
    expect(screen.getByText(/00m 08s elapsed/)).toBeTruthy();
    expect(screen.getByText(/Current:/)).toBeTruthy();
    expect(screen.getByText("RELIANCE")).toBeTruthy();
  });
});
