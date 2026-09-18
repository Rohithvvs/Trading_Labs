import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IndicatorLeanBacktestModal } from "../IndicatorLeanBacktestModal";

describe("IndicatorLeanBacktestModal", () => {
  const onStartBacktest = vi.fn();
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    render(
      <IndicatorLeanBacktestModal
        isOpen={false}
        onClose={onClose}
        indicatorName="52W High Breakout"
        onStartBacktest={onStartBacktest}
      />,
    );
    expect(screen.queryByTestId("indicator-lean-backtest-modal")).toBeNull();
  });

  it("renders form controls when isOpen is true", () => {
    render(
      <IndicatorLeanBacktestModal
        isOpen={true}
        onClose={onClose}
        indicatorName="52W High Breakout"
        onStartBacktest={onStartBacktest}
      />,
    );
    expect(screen.getByTestId("indicator-lean-backtest-modal")).toBeDefined();
    expect(screen.getByText("52W High Breakout")).toBeDefined();
    expect(screen.getByTestId("lean-start-date")).toBeDefined();
    expect(screen.getByTestId("lean-end-date")).toBeDefined();
    expect(screen.getByTestId("lean-initial-capital")).toBeDefined();
    expect(screen.getByTestId("lean-max-positions")).toBeDefined();
  });

  it("submits configured backtest parameters", async () => {
    onStartBacktest.mockResolvedValue(undefined);
    render(
      <IndicatorLeanBacktestModal
        isOpen={true}
        onClose={onClose}
        indicatorName="52W High Breakout"
        onStartBacktest={onStartBacktest}
      />,
    );

    fireEvent.change(screen.getByTestId("lean-initial-capital"), { target: { value: "200000" } });
    fireEvent.change(screen.getByTestId("lean-max-positions"), { target: { value: "15" } });

    fireEvent.click(screen.getByTestId("btn-confirm-start-lean-backtest"));

    await waitFor(() => {
      expect(onStartBacktest).toHaveBeenCalledWith({
        start_date: "2020-01-01",
        end_date: expect.any(String),
        initial_capital: 200000,
        universe_id: "nse-755",
        engine: "LEAN",
        max_positions: 15,
      });
    });

    expect(onClose).toHaveBeenCalled();
  });

  it("displays validation error when start date is after end date", async () => {
    render(
      <IndicatorLeanBacktestModal
        isOpen={true}
        onClose={onClose}
        indicatorName="52W High Breakout"
        onStartBacktest={onStartBacktest}
      />,
    );

    fireEvent.change(screen.getByTestId("lean-start-date"), { target: { value: "2025-01-01" } });
    fireEvent.change(screen.getByTestId("lean-end-date"), { target: { value: "2024-01-01" } });

    fireEvent.click(screen.getByTestId("btn-confirm-start-lean-backtest"));

    expect(await screen.findByText("Start date must be earlier than end date.")).toBeDefined();
    expect(onStartBacktest).not.toHaveBeenCalled();
  });
});
