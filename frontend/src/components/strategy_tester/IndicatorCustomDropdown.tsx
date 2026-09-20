import React, { useEffect, useMemo, useRef, useState } from "react";
import type { SavedIndicator } from "../../api_indicator_scanner";

interface IndicatorCustomDropdownProps {
  selected: SavedIndicator | null;
  indicators: SavedIndicator[];
  onSelect: (id: string) => void;
}

interface StrategyGroup {
  id: string;
  label: string;
  badge: string;
  items: SavedIndicator[];
}

const TOP_5_PREFIXES = ["09", "17", "03", "19", "13"];

function getCategory(name: string): "top5" | "trend" | "darvas" | "reversion" | "custom" {
  const clean = name.trim();
  const numMatch = clean.match(/^(\d{2})\s/);
  const num = numMatch ? numMatch[1] : null;

  if (
    (num && TOP_5_PREFIXES.includes(num)) ||
    clean.includes("52-Week") ||
    clean.includes("Long-Term") ||
    clean.includes("Super Trend") ||
    clean.includes("Low-Drawdown") ||
    clean.includes("Trend Pullback")
  ) {
    return "top5";
  }
  if ((num && ["01", "02", "04", "05"].includes(num)) || clean.toLowerCase().includes("darvas")) {
    return "darvas";
  }
  if (
    (num && ["06", "07", "11"].includes(num)) ||
    clean.toLowerCase().includes("reversion") ||
    clean.toLowerCase().includes("squeeze")
  ) {
    return "reversion";
  }
  if (
    (num && ["08", "10", "12", "14", "15", "16", "18", "20", "21"].includes(num)) ||
    clean.toLowerCase().includes("momentum") ||
    clean.toLowerCase().includes("golden") ||
    clean.toLowerCase().includes("trend")
  ) {
    return "trend";
  }
  return "custom";
}

export const IndicatorCustomDropdown: React.FC<IndicatorCustomDropdownProps> = ({
  selected,
  indicators,
  onSelect,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      // Focus search input on open
      setTimeout(() => searchInputRef.current?.focus(), 50);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  // Filter indicators by search
  const filtered = useMemo(() => {
    if (!search.trim()) return indicators;
    const q = search.trim().toLowerCase();
    return indicators.filter(
      (ind) =>
        ind.name.toLowerCase().includes(q) ||
        (ind.description && ind.description.toLowerCase().includes(q))
    );
  }, [indicators, search]);

  // Group filtered indicators
  const groups: StrategyGroup[] = useMemo(() => {
    const top5: SavedIndicator[] = [];
    const trend: SavedIndicator[] = [];
    const darvas: SavedIndicator[] = [];
    const reversion: SavedIndicator[] = [];
    const custom: SavedIndicator[] = [];

    filtered.forEach((item) => {
      const cat = getCategory(item.name);
      if (cat === "top5") top5.push(item);
      else if (cat === "trend") trend.push(item);
      else if (cat === "darvas") darvas.push(item);
      else if (cat === "reversion") reversion.push(item);
      else custom.push(item);
    });

    const result: StrategyGroup[] = [];
    if (top5.length > 0) {
      result.push({ id: "top5", label: "⭐ Top Recommended (Proven Backtest)", badge: "TOP 5", items: top5 });
    }
    if (trend.length > 0) {
      result.push({ id: "trend", label: "🚀 Momentum & Trend Following", badge: "MOMENTUM", items: trend });
    }
    if (darvas.length > 0) {
      result.push({ id: "darvas", label: "📦 Darvas Box Systems", badge: "DARVAS", items: darvas });
    }
    if (reversion.length > 0) {
      result.push({ id: "reversion", label: "🔄 Mean Reversion & Volatility", badge: "REVERSION", items: reversion });
    }
    if (custom.length > 0) {
      result.push({ id: "custom", label: "📁 Custom Scans & Indicators", badge: "CUSTOM", items: custom });
    }
    return result;
  }, [filtered]);

  const handleSelect = (id: string) => {
    onSelect(id);
    setIsOpen(false);
    setSearch("");
  };

  return (
    <div className="ind-custom-dropdown-container" ref={dropdownRef}>
      <button
        type="button"
        className={`ind-pill ind-pill-grow ind-custom-dd-trigger ${isOpen ? "is-open" : ""}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="ind-custom-dd-icon">📈</span>
        <span className="ind-custom-dd-label">
          {selected?.name || "Select Strategy / Indicator"}
        </span>
        <svg
          className={`ind-custom-dd-chevron ${isOpen ? "is-rotated" : ""}`}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div className="ind-custom-dd-menu" role="listbox">
          <div className="ind-custom-dd-search-wrap">
            <svg
              className="ind-custom-dd-search-icon"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref={searchInputRef}
              type="text"
              className="ind-custom-dd-search-input"
              placeholder="Search 20+ strategies (e.g. 52W, Momentum, Darvas)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button
                type="button"
                className="ind-custom-dd-clear-btn"
                onClick={() => setSearch("")}
                title="Clear search"
              >
                ✕
              </button>
            )}
          </div>

          <div className="ind-custom-dd-list">
            {groups.length === 0 ? (
              <div className="ind-custom-dd-empty">No strategies match &ldquo;{search}&rdquo;</div>
            ) : (
              groups.map((group) => (
                <div key={group.id} className="ind-custom-dd-group">
                  <div className="ind-custom-dd-group-header">
                    <span>{group.label}</span>
                    <span className="ind-custom-dd-group-badge">{group.badge}</span>
                  </div>
                  {group.items.map((item) => {
                    const isSelected = selected?.id === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        className={`ind-custom-dd-item ${isSelected ? "is-selected" : ""}`}
                        onClick={() => handleSelect(item.id)}
                      >
                        <div className="ind-custom-dd-item-text">
                          <span className="ind-custom-dd-item-title">{item.name}</span>
                          {item.description && (
                            <span className="ind-custom-dd-item-desc">
                              {item.description}
                            </span>
                          )}
                        </div>
                        {isSelected && (
                          <span className="ind-custom-dd-check">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

