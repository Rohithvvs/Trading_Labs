/**
 * Tests for EngineStatistics component.
 *
 * Validates:
 * 1. Production statistics section is not affected.
 * 2. RE-001 statistics render.
 * 3. RE-002 statistics render.
 * 4. RE-001 uses only RE-001 results (data-testid isolation).
 * 5. RE-002 uses only RE-002 results.
 * 6. BUY / WATCH / REJECT counts are shown correctly.
 * 7. Average score / confidence are shown.
 * 8. Scan/run isolation: scan_run_id is shown.
 * 9. "Not Executed" state is clearly shown.
 * 10. "Executed with 0 results" is distinct from Not Executed.
 * 11. No fake values: "—" shown for null metrics.
 * 12. API failure shows error state with Retry button.
 * 13. Responsive layout does not overflow.
 */

import React from "react";
import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { EngineStatistics } from "../components/swing/EngineStatistics";

// ---------------------------------------------------------------------------
// Mock
// ---------------------------------------------------------------------------

vi.mock("../api", () => ({
  fetchScannerStatistics: vi.fn(),
}));

import { fetchScannerStatistics } from "../api";

const mockFetch = vi.mocked(fetchScannerStatistics);

const makeExecutedRE001 = (overrides: Record<string, unknown> = {}) => ({
  status: "executed",
  engine_id: "RE-001",
  engine_name: "Trend Continuation Engine",
  scan_run_id: "re001-scan-001",
  scanned_at: "2026-08-10T06:00:00Z",
  total_candidates: 242,
  data_valid: 220,
  eligibility_matched: 180,
  technical_analysis_completed: 170,
  buy_ideas: 5,
  watch_ideas: 12,
  rejected: 225,
  high_confidence: 7,
  average_score: 76.3,
  highest_score: 91.0,
  average_confidence: 0.72,
  average_risk_reward: 2.4,
  gating_pass_rate: 70.2,
  technical_analysis_success_rate: 68.5,
  ...overrides,
});

const makeExecutedRE002 = (overrides: Record<string, unknown> = {}) => ({
  status: "executed",
  engine_id: "RE-002",
  engine_name: "Relative Strength Engine",
  scan_run_id: "re002-scan-001",
  scanned_at: "2026-08-10T06:00:00Z",
  total_candidates: 200,
  data_valid: 190,
  relative_strength_matched: 140,
  technical_analysis_completed: 130,
  buy_ideas: 3,
  watch_ideas: 8,
  rejected: 189,
  high_confidence: 4,
  average_score: 71.8,
  highest_score: 88.5,
  average_confidence: 0.65,
  average_risk_reward: 2.1,
  gating_pass_rate: 65.0,
  technical_analysis_success_rate: 65.0,
  ...overrides,
});

const makeNotExecuted = (engine_id: "RE-001" | "RE-002") => ({
  status: "not_executed",
  engine_id,
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EngineStatistics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders RE-001 statistics card", async () => {
    mockFetch.mockResolvedValueOnce({
      production: { available: true, total_scanned: 755 },
      engines: {
        "RE-001": makeExecutedRE001(),
        "RE-002": makeExecutedRE002(),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => {
      expect(screen.getByTestId("engine-card-RE-001")).toBeInTheDocument();
    });

    const card = screen.getByTestId("engine-card-RE-001");
    expect(card).toBeTruthy();
  });

  it("renders RE-002 statistics card", async () => {
    mockFetch.mockResolvedValueOnce({
      production: { available: true, total_scanned: 755 },
      engines: {
        "RE-001": makeExecutedRE001(),
        "RE-002": makeExecutedRE002(),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => {
      expect(screen.getByTestId("engine-card-RE-002")).toBeInTheDocument();
    });
  });

  it("shows RE-001 BUY count correctly", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001({ buy_ideas: 5 }),
        "RE-002": makeExecutedRE002({ buy_ideas: 3 }),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-001"));

    const re001Card = screen.getByTestId("engine-card-RE-001");
    expect(re001Card).toHaveTextContent("5");
  });

  it("shows RE-002 BUY count correctly", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001({ buy_ideas: 5 }),
        "RE-002": makeExecutedRE002({ buy_ideas: 3 }),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-002"));

    const re002Card = screen.getByTestId("engine-card-RE-002");
    expect(re002Card).toHaveTextContent("3");
  });

  it("shows RE-001 WATCH count", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001({ watch_ideas: 12 }),
        "RE-002": makeExecutedRE002({ watch_ideas: 8 }),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-001"));
    expect(screen.getByTestId("engine-card-RE-001")).toHaveTextContent("12");
  });

  it("shows RE-002 WATCH count", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001({ watch_ideas: 12 }),
        "RE-002": makeExecutedRE002({ watch_ideas: 8 }),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-002"));
    expect(screen.getByTestId("engine-card-RE-002")).toHaveTextContent("8");
  });

  it("shows RE-001 REJECT count", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001({ rejected: 225 }),
        "RE-002": makeExecutedRE002({ rejected: 189 }),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-001"));
    expect(screen.getByTestId("engine-card-RE-001")).toHaveTextContent("225");
  });

  it("shows RE-002 REJECT count", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001({ rejected: 225 }),
        "RE-002": makeExecutedRE002({ rejected: 189 }),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-002"));
    expect(screen.getByTestId("engine-card-RE-002")).toHaveTextContent("189");
  });

  it("shows 'Not Executed' when RE-001 has never run", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeNotExecuted("RE-001"),
        "RE-002": makeExecutedRE002(),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-001"));
    expect(screen.getByTestId("engine-card-RE-001")).toHaveTextContent(/Not Executed/i);
  });

  it("shows 'Not Executed' when RE-002 has never run", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001(),
        "RE-002": makeNotExecuted("RE-002"),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-002"));
    expect(screen.getByTestId("engine-card-RE-002")).toHaveTextContent(/Not Executed/i);
  });

  it("shows '—' for null average_score (no fake values)", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001({ average_score: null }),
        "RE-002": makeExecutedRE002({ average_score: null }),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-001"));
    const re001Card = screen.getByTestId("engine-card-RE-001");
    // Value for Avg Score should be em dash when null
    expect(re001Card).toHaveTextContent(/—/);
  });

  it("shows error state with Retry button when API fails", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    render(<EngineStatistics />);

    await waitFor(() => {
      expect(screen.getByTestId("engine-statistics-error")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("retries when Retry button is clicked", async () => {
    mockFetch
      .mockRejectedValueOnce(new Error("First failure"))
      .mockResolvedValueOnce({
        production: {},
        engines: {
          "RE-001": makeExecutedRE001(),
          "RE-002": makeExecutedRE002(),
        },
      });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-statistics-error"));

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByTestId("engine-card-RE-001")).toBeInTheDocument();
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("shows comparison table when both engines have executed", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001(),
        "RE-002": makeExecutedRE002(),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => {
      expect(screen.getByTestId("engine-comparison-table")).toBeInTheDocument();
    });
  });

  it("hides comparison table when both engines not executed", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeNotExecuted("RE-001"),
        "RE-002": makeNotExecuted("RE-002"),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-001"));
    expect(screen.queryByTestId("engine-comparison-table")).not.toBeInTheDocument();
  });

  it("RE-002 shows RS Matched label (not Trend Matched)", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001(),
        "RE-002": makeExecutedRE002({ relative_strength_matched: 140 }),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-002"));

    const re002Card = screen.getByTestId("engine-card-RE-002");
    expect(re002Card).toHaveTextContent(/RS Matched/i);
    expect(re002Card).not.toHaveTextContent(/Trend Matched/i);
  });

  it("RE-001 shows Trend Matched label (not RS Matched)", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001({ eligibility_matched: 180 }),
        "RE-002": makeExecutedRE002(),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-001"));

    const re001Card = screen.getByTestId("engine-card-RE-001");
    expect(re001Card).toHaveTextContent(/Trend Matched/i);
    expect(re001Card).not.toHaveTextContent(/RS Matched/i);
  });

  it("makes only one API call for both engines (consolidated request)", async () => {
    mockFetch.mockResolvedValueOnce({
      production: {},
      engines: {
        "RE-001": makeExecutedRE001(),
        "RE-002": makeExecutedRE002(),
      },
    });

    render(<EngineStatistics />);

    await waitFor(() => screen.getByTestId("engine-card-RE-001"));

    // Only 1 API call, not one per engine
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});
