import React from "react";
import { STOCK_DETAIL_TABS, type StockDetailTabId } from "./types";

interface StockTabsProps {
  activeTab: StockDetailTabId;
  onTabChange: (tabId: StockDetailTabId) => void;
}

export const StockTabs: React.FC<StockTabsProps> = ({ activeTab, onTabChange }) => {
  return (
    <div className="st-stock-tabs-nav" role="tablist" aria-label="Stock analysis sections">
      {STOCK_DETAIL_TABS.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={`st-stock-tab-btn ${isActive ? "is-active" : ""}`}
            onClick={() => onTabChange(tab.id)}
            data-testid={tab.testId}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
};
