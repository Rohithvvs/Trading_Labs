import React, { memo, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMarketSession } from "../../utils/tradingHours";
import { fetchUniverseInstruments, type UniverseInstrument } from "../../api";

interface MarketHeaderProps {
  selectedTimeframe: string;
  onTimeframeChange: (tf: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
  lastUpdated?: string | null;
}

export const MarketHeader: React.FC<MarketHeaderProps> = memo(function MarketHeader({
  selectedTimeframe,
  onTimeframeChange,
  onRefresh,
  refreshing,
  lastUpdated,
}) {
  const navigate = useNavigate();
  const [currentTime, setCurrentTime] = useState<string>("");
  const [marketStatus, setMarketStatus] = useState<string>("OPEN");
  const [instruments, setInstruments] = useState<UniverseInstrument[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);

  // Update live clock and market status
  useEffect(() => {
    function updateClock() {
      const now = new Date();
      const statusCheck = getMarketSession(now);
      setMarketStatus(statusCheck.isOpen ? "OPEN" : statusCheck.status);

      const options: Intl.DateTimeFormatOptions = {
        timeZone: "Asia/Kolkata",
        weekday: "short",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      };
      setCurrentTime(new Intl.DateTimeFormat("en-IN", options).format(now));
    }

    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  // Pre-load instruments for quick search
  useEffect(() => {
    let mounted = true;
    fetchUniverseInstruments("NIFTY500")
      .then((data) => {
        if (mounted && Array.isArray(data)) setInstruments(data);
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  const filtered = searchQuery.trim()
    ? instruments
        .filter(
          (inst) =>
            inst.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
            inst.company_name?.toLowerCase().includes(searchQuery.toLowerCase())
        )
        .slice(0, 8)
    : [];

  const handleSelectSymbol = (sym: string) => {
    setSearchQuery("");
    setSearchFocused(false);
    navigate(`/scanner?symbol=${encodeURIComponent(sym)}`);
  };

  return (
    <header className="market-header" aria-label="Market overview topbar">
      <div className="market-header__info">
        <div className="market-header__title-row">
          <h1 className="market-header__title">Market Overview</h1>
          <span className="market-header__meta-chip" title="Live Market Feed">
            <span
              className={`market-status-dot ${marketStatus === "CLOSED" ? "is-closed" : ""}`}
              aria-hidden
            />
            <span>• LIVE DATA</span>
          </span>
        </div>
        <p className="market-header__subtitle">
          Get a complete view of the market — indices, trend, breadth, sectors, movers, and latest opportunities.
        </p>
      </div>

      <div className="market-header__controls">
        {/* Market Status & Time */}
        <div className="market-header__meta-chip" title="Exchange Status">
          <span>{currentTime || "IST Live"}</span>
          <span style={{ opacity: 0.5 }}>|</span>
          <span style={{ fontWeight: 600, color: marketStatus === "OPEN" ? "var(--mk-green)" : "var(--mk-red)" }}>
            Market {marketStatus}
          </span>
          <span style={{ opacity: 0.5 }}>•</span>
          <span>NSE | BSE</span>
        </div>

        {/* Global Timeframe Selector */}
        <div className="market-timeframe-pills" role="tablist" aria-label="Market Timeframe">
          {["1D", "1W", "1M", "6M", "1Y"].map((tf) => (
            <button
              key={tf}
              type="button"
              role="tab"
              aria-selected={selectedTimeframe === tf}
              className={`market-pill-btn ${selectedTimeframe === tf ? "is-active" : ""}`}
              onClick={() => onTimeframeChange(tf)}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Search Stock Input */}
        <div className="market-search-box">
          <span className="market-search-icon" aria-hidden>
            🔍
          </span>
          <input
            type="text"
            className="market-search-input"
            placeholder="Search stocks, e.g. RELIANCE, TCS..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
            aria-label="Search stocks"
          />
          {searchFocused && filtered.length > 0 && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                left: 0,
                right: 0,
                marginTop: 4,
                background: "var(--mk-surface-raised)",
                border: "1px solid var(--mk-border)",
                borderRadius: "var(--mk-radius-sm)",
                zIndex: 50,
                maxHeight: 280,
                overflowY: "auto",
                boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
              }}
            >
              {filtered.map((item) => (
                <button
                  key={item.symbol}
                  type="button"
                  onMouseDown={() => handleSelectSymbol(item.symbol)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    width: "100%",
                    padding: "8px 12px",
                    background: "transparent",
                    border: "none",
                    borderBottom: "1px solid var(--mk-border)",
                    color: "var(--mk-text-primary)",
                    cursor: "pointer",
                    textAlign: "left",
                    fontSize: "0.82rem",
                  }}
                >
                  <strong>{item.symbol}</strong>
                  <span style={{ fontSize: "0.75rem", color: "var(--mk-text-muted)" }}>
                    {item.company_name || ""}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Refresh Button */}
        <button
          type="button"
          className="market-pill-btn"
          style={{
            background: "var(--mk-surface-raised)",
            border: "1px solid var(--mk-border)",
            padding: "8px 14px",
            color: "var(--mk-text-primary)",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
          }}
          onClick={onRefresh}
          disabled={refreshing}
          title={lastUpdated ? `Last updated: ${new Date(lastUpdated).toLocaleTimeString()}` : "Refresh market quotes"}
        >
          <span style={{ display: "inline-block", transform: refreshing ? "rotate(180deg)" : "none", transition: "transform 0.5s ease" }}>
            🔄
          </span>
          <span>{refreshing ? "Updating…" : "Refresh"}</span>
        </button>
      </div>
    </header>
  );
});
