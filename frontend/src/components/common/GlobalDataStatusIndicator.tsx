import { useState, useRef, useEffect } from "react";
import { useInfrastructureHealth } from "../../hooks/useInfrastructureHealth";
import { DataStatusBadge } from "./DataStatusBadge";

export function GlobalDataStatusIndicator({ onOpenFeedback }: { onOpenFeedback?: () => void }) {
  const { services, lastCheckedAt } = useInfrastructureHealth();
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  const feedSvc = services.find((s) => s.key === "feed");
  const fyersSvc = services.find((s) => s.key === "fyers");

  const isFeedOffline = feedSvc?.status === "offline" || fyersSvc?.status === "offline";
  const isFeedConnecting =
    feedSvc?.status === "connecting" ||
    fyersSvc?.status === "connecting" ||
    feedSvc?.status === "waking" ||
    fyersSvc?.status === "waking";
  const isFeedSleeping = feedSvc?.status === "sleeping" || fyersSvc?.status === "sleeping";
  const isLive = feedSvc?.status === "active" && fyersSvc?.status === "active";

  // Click outside listener
  useEffect(() => {
    if (!open) return;
    const handleOutside = (e: MouseEvent | TouchEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("touchstart", handleOutside);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("touchstart", handleOutside);
    };
  }, [open]);

  let statusBadge = <DataStatusBadge kind="live" label="Live Data" hideWhenLive={false} />;
  let summaryText = "Live market connection active.";

  if (isFeedOffline) {
    statusBadge = <DataStatusBadge kind="unavailable" label="Data Unavailable" hideWhenLive={false} />;
    summaryText = "Market feed is disconnected. Showing cached daily candles or fallback quotes.";
  } else if (isFeedConnecting) {
    statusBadge = <DataStatusBadge kind="delayed" label="Data Connecting" hideWhenLive={false} />;
    summaryText = "Connecting to market feed. Quotes may experience temporary delays.";
  } else if (isFeedSleeping) {
    statusBadge = <DataStatusBadge kind="cached" label="Cached / Inactive" hideWhenLive={false} />;
    summaryText = "Market closed or feed idle. Displaying cached session data.";
  }

  return (
    <div className="global-data-status" ref={popoverRef} style={{ position: "relative" }}>
      <button
        type="button"
        className="global-data-status__btn"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Market Data Health and Freshness"
        style={{
          background: "transparent",
          border: "none",
          padding: 0,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
        }}
      >
        {statusBadge}
      </button>

      {open && (
        <div
          className="global-data-status__popover"
          role="dialog"
          aria-label="Market Data Health"
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            right: 0,
            width: "280px",
            background: "var(--bg-surface-elevated, #1a202c)",
            border: "1px solid var(--border-subtle, #2d3748)",
            borderRadius: "8px",
            padding: "14px",
            boxShadow: "0 10px 25px rgba(0, 0, 0, 0.5)",
            zIndex: 100,
            fontSize: "0.82rem",
            color: "var(--text-primary, #f1f5f9)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontWeight: 700, fontSize: "0.86rem" }}>Market Data Status</span>
            {lastCheckedAt && (
              <span style={{ fontSize: "0.72rem", color: "var(--text-secondary, #94a3b8)" }}>
                {lastCheckedAt.toLocaleTimeString()}
              </span>
            )}
          </div>

          <p style={{ margin: "0 0 10px", color: "var(--text-secondary, #94a3b8)", lineHeight: 1.4 }}>
            {summaryText}
          </p>

          <div
            style={{
              background: "rgba(0,0,0,0.25)",
              borderRadius: "6px",
              padding: "8px 10px",
              marginBottom: "10px",
              display: "flex",
              flexDirection: "column",
              gap: "4px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-secondary, #94a3b8)" }}>Market Feed:</span>
              <span style={{ fontWeight: 600, textTransform: "capitalize" }}>{feedSvc?.status || "Unknown"}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-secondary, #94a3b8)" }}>FYERS API:</span>
              <span style={{ fontWeight: 600, textTransform: "capitalize" }}>{fyersSvc?.status || "Unknown"}</span>
            </div>
          </div>

          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary, #94a3b8)", marginBottom: "8px" }}>
            Notice anomalous prices or delayed quotes?
          </div>

          {onOpenFeedback && (
            <button
              type="button"
              className="ds-btn ds-btn--secondary ds-btn--sm"
              onClick={() => {
                setOpen(false);
                onOpenFeedback();
              }}
              style={{ width: "100%", justifyContent: "center" }}
            >
              Report Data Issue
            </button>
          )}
        </div>
      )}
    </div>
  );
}
