import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fetchLtmSymbolDetail, fetchW52SymbolDetail } from "../../../api";
import type { StrategyResultRow } from "../../../api_strategy_tester";
import { BacktestTab } from "../BacktestTab";

global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

vi.mock("../../../api", () => ({
  fetchSymbolDetail: vi.fn(async () => ({ ohlcv: [] })),
  fetchW52SymbolDetail: vi.fn(async () => ({
    symbol: "RATEGAIN",
    dashboard: {
      never_selected_in_window: true,
      trade_count: 0,
      total_return: null,
      window: "3Y",
      replay_kind: "symbol_window",
      equity_curve: [],
    },
  })),
  fetchLtmSymbolDetail: vi.fn(async () => ({
    symbol: "RATEGAIN",
    dashboard: {
      never_selected_in_window: true,
      trade_count: 0,
      total_return: null,
      window: "3Y",
      replay_kind: "symbol_window",
      equity_curve: [],
    },
  })),
}));

const stock: StrategyResultRow = {
  rank: 1,
  symbol: "RATEGAIN",
  company: "Rategain Travel Technologies Ltd.",
  status: "ok",
  signal: "MATCH",
  evaluation_date: "2026-09-04",
  entry_price: 495.05,
  exit_price: 869.75,
  return_pct: 76,
  close: 869.75,
  volume: null,
  avg_volume: null,
  rsi: null,
  sma_20: null,
  sma_50: null,
  sma_200: null,
  high_252: null,
  filters_passed: 1,
  filters_failed: 0,
  passed_filters: ["Momentum 252 > 0.5"],
  failed_filters: [],
  primary_failure_reason: null,
  source: "indicator_scanner",
  strategy_name: "LTM Momentum 252 [SCAN]",
};

describe("BacktestTab indicator scanner", () => {
  it("does not use the LTM/W52 strategy book for indicator scan rows", async () => {
    render(
      <BacktestTab
        symbol="RATEGAIN"
        stock={stock}
        runStatus={{
          id: "IND-20260904-001",
          run_id: "IND-20260904-001",
          strategy_name: "LTM Momentum 252 [SCAN]",
          status: "completed",
          timeframe: "1D",
          universe: "750 Stocks",
          universe_size: 750,
          progress_pct: 100,
          processed_count: 750,
          total_count: 750,
          start_date: null,
          end_date: "2026-09-04",
          initial_capital: 100000,
          buy: 89,
          watch: 40,
          reject: 621,
        }}
        history={[
          {
            run_id: "IND-20260904-001",
            strategy_name: "LTM Momentum 252 [SCAN]",
            date: "2026-09-04",
            signal: "MATCH",
            entry_price: 495.05,
            exit_price: 869.75,
            return_pct: 76,
            status: "completed",
          },
        ]}
        strategyName="LTM Momentum 252 [SCAN]"
        runId="IND-20260904-001"
        endDate="2026-09-04"
        initialCapital={100000}
      />,
    );

    expect(await screen.findByTestId("card-detail-backtest")).toBeTruthy();
    expect(fetchLtmSymbolDetail).not.toHaveBeenCalled();
    expect(fetchW52SymbolDetail).not.toHaveBeenCalled();
    expect(screen.queryByText(/not selected in the strategy book/i)).toBeNull();
    expect(screen.getByTestId("backtest-total-return").textContent).toBe("+76.00%");
  });
});
