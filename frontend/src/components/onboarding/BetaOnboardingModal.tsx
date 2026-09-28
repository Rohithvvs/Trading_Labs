import { useState, useEffect } from "react";
import { TELEGRAM_CHANNEL_URL, TELEGRAM_GROUP_URL } from "../../config";

interface BetaOnboardingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenFeedback?: () => void;
}

export const BETA_ONBOARDING_STORAGE_KEY = "tl_beta_onboarding_acknowledged";

export function hasAcknowledgedBetaOnboarding(): boolean {
  try {
    return localStorage.getItem(BETA_ONBOARDING_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function setAcknowledgedBetaOnboarding(acknowledged = true): void {
  try {
    localStorage.setItem(BETA_ONBOARDING_STORAGE_KEY, acknowledged ? "true" : "false");
  } catch {
    // Ignore storage errors
  }
}

export function BetaOnboardingModal({ isOpen, onClose, onOpenFeedback }: BetaOnboardingModalProps) {
  const [dontShowAgain, setDontShowAgain] = useState(true);

  // Close on ESC
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleAcknowledge = () => {
    if (dontShowAgain) {
      setAcknowledgedBetaOnboarding(true);
    }
    onClose();
  };

  return (
    <div
      className="ds-modal-scrim"
      role="dialog"
      aria-modal="true"
      aria-labelledby="beta-onboarding-title"
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.78)",
        backdropFilter: "blur(6px)",
        zIndex: 10000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "16px",
        overflowY: "auto",
      }}
    >
      <div
        className="beta-onboarding-dialog"
        style={{
          background: "var(--bg-surface-elevated, #161a22)",
          color: "var(--text-primary, #f1f5f9)",
          border: "1px solid var(--border-subtle, #30363d)",
          borderRadius: "14px",
          width: "100%",
          maxWidth: "640px",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
          padding: "28px",
          position: "relative",
          maxHeight: "90vh",
          overflowY: "auto",
        }}
      >
        {/* Header Badge */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
          <div>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                background: "rgba(56, 189, 248, 0.15)",
                border: "1px solid rgba(56, 189, 248, 0.35)",
                color: "#38bdf8",
                padding: "3px 10px",
                borderRadius: "20px",
                fontSize: "0.75rem",
                fontWeight: 700,
                letterSpacing: "0.05em",
                textTransform: "uppercase",
                marginBottom: "8px",
              }}
            >
              <span>🚀</span> Public Beta Welcome & Disclaimer
            </div>
            <h1 id="beta-onboarding-title" style={{ margin: "4px 0 0", fontSize: "1.5rem", fontWeight: 700 }}>
              Welcome to Trading Labs
            </h1>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close beta onboarding"
            style={{
              background: "none",
              border: "none",
              color: "var(--text-secondary, #94a3b8)",
              fontSize: "1.25rem",
              cursor: "pointer",
              padding: "4px 8px",
              borderRadius: "4px",
            }}
          >
            ✕
          </button>
        </div>

        <p style={{ margin: "0 0 20px", fontSize: "0.9rem", color: "var(--text-secondary, #94a3b8)", lineHeight: 1.5 }}>
          Trading Labs is currently in <strong>Public Beta</strong>. Before exploring strategies and simulated execution,
          please review the following vital operating principles:
        </p>

        {/* 5 Core Principles Grid */}
        <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "22px" }}>
          {/* 1. Paper trading only */}
          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
              padding: "12px 14px",
              background: "rgba(59, 130, 246, 0.08)",
              border: "1px solid rgba(59, 130, 246, 0.2)",
              borderRadius: "8px",
            }}
          >
            <div style={{ fontSize: "1.3rem", lineHeight: 1 }}>📝</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "#60a5fa" }}>Paper Trading Only</div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-secondary, #94a3b8)", marginTop: "2px" }}>
                All portfolios, orders, and balances inside this application are simulated paper trading with virtual
                capital. No real money accounts are connected.
              </div>
            </div>
          </div>

          {/* 2. No live trade orders */}
          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
              padding: "12px 14px",
              background: "rgba(239, 68, 68, 0.08)",
              border: "1px solid rgba(239, 68, 68, 0.2)",
              borderRadius: "8px",
            }}
          >
            <div style={{ fontSize: "1.3rem", lineHeight: 1 }}>🚫</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "#f87171" }}>No Live Trade Orders</div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-secondary, #94a3b8)", marginTop: "2px" }}>
                This platform will never execute real market orders or commit capital to exchanges. Any broker
                connections (e.g. FYERS) are strictly read-only for market data quotes.
              </div>
            </div>
          </div>

          {/* 3. Not investment advice */}
          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
              padding: "12px 14px",
              background: "rgba(245, 158, 11, 0.08)",
              border: "1px solid rgba(245, 158, 11, 0.2)",
              borderRadius: "8px",
            }}
          >
            <div style={{ fontSize: "1.3rem", lineHeight: 1 }}>⚖️</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "#fbbf24" }}>Not Investment Advice</div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-secondary, #94a3b8)", marginTop: "2px" }}>
                All candidate scans, indicators, scores, and signals (BUY, WATCH, REJECT) are quantitative research tools
                for educational and technical evaluation only. Always conduct independent due diligence.
              </div>
            </div>
          </div>

          {/* 4. Data may be delayed or unavailable */}
          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
              padding: "12px 14px",
              background: "rgba(168, 85, 247, 0.08)",
              border: "1px solid rgba(168, 85, 247, 0.2)",
              borderRadius: "8px",
            }}
          >
            <div style={{ fontSize: "1.3rem", lineHeight: 1 }}>⏱️</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "#c084fc" }}>
                Data May Be Delayed or Unavailable
              </div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-secondary, #94a3b8)", marginTop: "2px" }}>
                Market data feeds, quotes, and calculations may experience delays, fallbacks (e.g. daily candles), or
                temporary outages. Watch for visible status badges like <code>[DELAYED]</code>, <code>[CACHED]</code>, or{" "}
                <code>[FALLBACK DATA]</code>.
              </div>
            </div>
          </div>

          {/* 5. How to report a bug */}
          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
              padding: "12px 14px",
              background: "rgba(34, 197, 94, 0.08)",
              border: "1px solid rgba(34, 197, 94, 0.2)",
              borderRadius: "8px",
            }}
          >
            <div style={{ fontSize: "1.3rem", lineHeight: 1 }}>🐛</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "#4ade80" }}>How to Report a Bug</div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-secondary, #94a3b8)", marginTop: "2px" }}>
                Click the persistent <strong>“Send Feedback / Report Bug”</strong> button at the top or bottom of any
                screen to submit screenshots, UI issues, or data anomalies. You can also chat directly with our
                engineering team on Telegram.
              </div>
            </div>
          </div>
        </div>

        {/* Telegram Community Card */}
        <div
          style={{
            background: "rgba(255, 255, 255, 0.04)",
            border: "1px solid var(--border-subtle, #30363d)",
            borderRadius: "8px",
            padding: "14px 16px",
            marginBottom: "20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>💬 Official Telegram Beta Community</div>
            <div style={{ fontSize: "0.78rem", color: "var(--text-secondary, #94a3b8)", marginTop: "2px" }}>
              Join announcements and community discussion with developers:
            </div>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <a
              href={TELEGRAM_CHANNEL_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="ds-btn ds-btn--ghost ds-btn--sm"
              style={{ textDecoration: "none" }}
            >
              Channel ↗
            </a>
            <a
              href={TELEGRAM_GROUP_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="ds-btn ds-btn--secondary ds-btn--sm"
              style={{ textDecoration: "none" }}
            >
              Discussion Group ↗
            </a>
          </div>
        </div>

        {/* Footer actions */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "12px",
            borderTop: "1px solid var(--border-subtle, #30363d)",
            paddingTop: "16px",
          }}
        >
          <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.82rem", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => setDontShowAgain(e.target.checked)}
              style={{ cursor: "pointer" }}
            />
            <span>Don't show this screen automatically again</span>
          </label>

          <div style={{ display: "flex", gap: "10px" }}>
            {onOpenFeedback && (
              <button
                type="button"
                className="ds-btn ds-btn--ghost ds-btn--sm"
                onClick={() => {
                  onClose();
                  onOpenFeedback();
                }}
              >
                Send Feedback Now
              </button>
            )}
            <button
              type="button"
              className="ds-btn ds-btn--primary"
              onClick={handleAcknowledge}
              style={{ minWidth: "180px", fontWeight: 600 }}
            >
              I Understand & Acknowledge
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
