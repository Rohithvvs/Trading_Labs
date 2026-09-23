import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { IndicatorCustomDropdown, getTop5Rank } from "../IndicatorCustomDropdown";
import type { SavedIndicator } from "../../../api_indicator_scanner";

describe("IndicatorCustomDropdown - Top 5 Research Strategies", () => {
  describe("getTop5Rank", () => {
    it("correctly identifies all Top 5 strategies from research reports", () => {
      expect(getTop5Rank("Top 1: App Preset Momentum [SCAN]")).toBe(1);
      expect(getTop5Rank("Top 2: 12-1 Cross-Sectional Momentum [SCAN]")).toBe(2);
      expect(getTop5Rank("Top 3: 52-Week High Breakout [SCAN]")).toBe(3);
      expect(getTop5Rank("Top 4: 52-Week Breakout ATR Sizing [SCAN]")).toBe(4);
      expect(getTop5Rank("Top 5: Minervini Stage-2 VCP [SCAN]")).toBe(5);
    });

    it("does not classify non-top5 numbered catalog strategies into top 5", () => {
      expect(getTop5Rank("01 Darvas Box Classic [SCAN]")).toBeNull();
      expect(getTop5Rank("02 Darvas ATR-5 + Nifty SMA50 [SCAN]")).toBeNull();
      expect(getTop5Rank("03 Super Trend Alignment [SCAN]")).toBeNull();
      expect(getTop5Rank("06 Mean Reversion [SCAN]")).toBeNull();
      expect(getTop5Rank("09 52-Week High Breakout [SCAN]")).toBeNull();
      expect(getTop5Rank("13 Trend Pullback [SCAN]")).toBeNull();
      expect(getTop5Rank("17 Long-Term Buy & Hold Momentum [SCAN]")).toBeNull();
      expect(getTop5Rank("19 Low-Drawdown Regime Momentum [SCAN]")).toBeNull();
      expect(getTop5Rank("21 SMA 10/50 [SCAN]")).toBeNull();
    });
  });

  describe("Dropdown rendering and categorization", () => {
    const mockIndicators: SavedIndicator[] = [
      {
        id: "id-top3",
        name: "Top 3: 52-Week High Breakout [SCAN]",
        description: "Rank #3 (+20.41% CAGR, 11.08% Max DD)",
        source_code: "plot(close)",
      },
      {
        id: "id-top1",
        name: "Top 1: App Preset Momentum [SCAN]",
        description: "Rank #1 (+24.40% CAGR, 3.21 PF)",
        source_code: "plot(close)",
      },
      {
        id: "id-top2",
        name: "Top 2: 12-1 Cross-Sectional Momentum [SCAN]",
        description: "Rank #2 (+22.86% CAGR)",
        source_code: "plot(close)",
      },
      {
        id: "id-01",
        name: "01 Darvas Box Classic [SCAN]",
        description: "Box breakout",
        source_code: "plot(close)",
      },
      {
        id: "id-06",
        name: "06 Mean Reversion [SCAN]",
        description: "RSI 30 bounce",
        source_code: "plot(close)",
      },
      {
        id: "id-09",
        name: "09 52-Week High Breakout [SCAN]",
        description: "Catalog 09 breakout",
        source_code: "plot(close)",
      },
      {
        id: "id-13",
        name: "13 Trend Pullback [SCAN]",
        description: "Trend pullback scan",
        source_code: "plot(close)",
      },
    ];

    it("renders groups with Top 5 sorted #1 to #5 and preserves catalog categories", () => {
      const onSelect = vi.fn();
      render(
        <IndicatorCustomDropdown
          selected={mockIndicators[1]}
          indicators={mockIndicators}
          onSelect={onSelect}
        />
      );

      // Trigger button
      const trigger = screen.getByRole("button", { name: /Top 1: App Preset Momentum/i });
      expect(trigger).toBeDefined();

      // Open dropdown
      fireEvent.click(trigger);

      // Verify group headers
      expect(screen.getByText("Top 5 Strategies")).toBeDefined();
      expect(screen.getByText("🚀 Momentum & Trend Following")).toBeDefined();
      expect(screen.getByText("📦 Darvas Box Systems")).toBeDefined();
      expect(screen.getByText("🔄 Mean Reversion & Volatility")).toBeDefined();

      // Verify badges on Top 5 items
      expect(screen.getByText("🥇 #1")).toBeDefined();
      expect(screen.getByText("🥈 #2")).toBeDefined();
      expect(screen.getByText("🥉 #3")).toBeDefined();

      // Verify 09 and 13 are preserved under Momentum & Trend Following
      expect(screen.getByText("09 52-Week High Breakout [SCAN]")).toBeDefined();
      expect(screen.getByText("13 Trend Pullback [SCAN]")).toBeDefined();

      // Verify 01 Darvas is preserved under Darvas Box Systems
      expect(screen.getByText("01 Darvas Box Classic [SCAN]")).toBeDefined();

      // Verify 06 Mean Reversion is preserved under Mean Reversion
      expect(screen.getByText("06 Mean Reversion [SCAN]")).toBeDefined();

      // Click on Top 2 item
      const top2Item = screen.getByText("Top 2: 12-1 Cross-Sectional Momentum [SCAN]");
      fireEvent.click(top2Item);
      expect(onSelect).toHaveBeenCalledWith("id-top2");
    });
  });
});

