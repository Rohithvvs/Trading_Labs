import type { ReactNode } from "react";

export type DataStatusKind = "mock" | "cached" | "fallback" | "delayed" | "unavailable" | "live";

export interface DataStatusBadgeProps {
  /** Explicit status kind */
  kind?: DataStatusKind;
  /** Or pass source string (e.g. FYERS_QUOTE, CANDLE_FALLBACK, TEST_MOCK, NO_DATA, synthetic) */
  source?: string | null;
  /** Or boolean flags */
  isMock?: boolean;
  isCached?: boolean;
  isFallback?: boolean;
  isDelayed?: boolean;
  isUnavailable?: boolean;
  warning?: string | null;
  /** Custom text override */
  label?: string;
  /** Size */
  size?: "sm" | "md";
  /** If true, shows only when NOT live (default: true) */
  hideWhenLive?: boolean;
  className?: string;
}

export function detectDataStatusKind(props: {
  kind?: DataStatusKind;
  source?: string | null;
  isMock?: boolean;
  isCached?: boolean;
  isFallback?: boolean;
  isDelayed?: boolean;
  isUnavailable?: boolean;
  warning?: string | null;
}): DataStatusKind | null {
  if (props.kind) return props.kind;

  const src = (props.source || "").toUpperCase();
  const warn = (props.warning || "").toLowerCase();

  if (props.isUnavailable || src === "NO_DATA" || src === "UNAVAILABLE" || warn.includes("unavailable")) {
    return "unavailable";
  }
  if (props.isMock || src.includes("MOCK") || src === "TEST_MOCK" || src === "SYNTHETIC" || warn.includes("mock")) {
    return "mock";
  }
  if (props.isFallback || src.includes("FALLBACK") || src === "CANDLE_FALLBACK" || warn.includes("fallback")) {
    return "fallback";
  }
  if (props.isDelayed || warn.includes("delay") || warn.includes("stale")) {
    return "delayed";
  }
  if (props.isCached || src.includes("CACHE") || src === "DB_CACHE") {
    return "cached";
  }
  if (src === "FYERS_QUOTE" || src === "FYERS" || src === "LIVE") {
    return "live";
  }
  return null;
}

const STATUS_CONFIG: Record<
  DataStatusKind,
  { label: string; icon: string; tone: "warning" | "negative" | "info" | "neutral" | "positive"; tooltip: string }
> = {
  mock: {
    label: "MOCK DATA",
    icon: "⚠️",
    tone: "warning",
    tooltip: "Simulated or test data. Do not make live trading decisions based on these values.",
  },
  cached: {
    label: "CACHED",
    icon: "⏱",
    tone: "info",
    tooltip: "Showing cached data snapshot. Revalidation occurs automatically.",
  },
  fallback: {
    label: "FALLBACK DATA",
    icon: "ℹ️",
    tone: "warning",
    tooltip: "Live stream unavailable. Showing fallback previous session data.",
  },
  delayed: {
    label: "DELAYED",
    icon: "⏳",
    tone: "warning",
    tooltip: "Market feed or quote timestamps indicate delayed/stale data.",
  },
  unavailable: {
    label: "DATA UNAVAILABLE",
    icon: "✕",
    tone: "negative",
    tooltip: "Market data provider is currently offline or symbol data is unavailable.",
  },
  live: {
    label: "LIVE DATA",
    icon: "●",
    tone: "positive",
    tooltip: "Connected to live market data feed.",
  },
};

export function DataStatusBadge({
  kind,
  source,
  isMock,
  isCached,
  isFallback,
  isDelayed,
  isUnavailable,
  warning,
  label,
  size = "sm",
  hideWhenLive = true,
  className = "",
}: DataStatusBadgeProps) {
  const detectedKind = detectDataStatusKind({
    kind,
    source,
    isMock,
    isCached,
    isFallback,
    isDelayed,
    isUnavailable,
    warning,
  });

  if (!detectedKind) return null;
  if (detectedKind === "live" && hideWhenLive) return null;

  const cfg = STATUS_CONFIG[detectedKind];
  const displayLabel = label || cfg.label;

  const toneClasses: Record<string, string> = {
    warning: "ds-badge--warning",
    negative: "ds-badge--sell",
    info: "ds-badge--watch",
    neutral: "ds-badge--neutral",
    positive: "ds-badge--buy",
  };

  return (
    <span
      className={`data-status-badge ds-badge ${toneClasses[cfg.tone]} ${size === "sm" ? "data-status-badge--sm" : ""} ${className}`.trim()}
      title={cfg.tooltip}
      aria-label={`Data status: ${displayLabel}. ${cfg.tooltip}`}
      data-testid={`data-status-${detectedKind}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        fontWeight: 600,
        letterSpacing: "0.03em",
        fontSize: size === "sm" ? "0.72rem" : "0.8rem",
        padding: size === "sm" ? "2px 7px" : "4px 10px",
        borderRadius: "4px",
        textTransform: "uppercase",
      }}
    >
      <span aria-hidden style={{ fontSize: "0.8em" }}>
        {cfg.icon}
      </span>
      <span>{displayLabel}</span>
    </span>
  );
}

/**
 * Full-width visual banner for data issues / warnings.
 */
export function DataStatusBanner({
  kind,
  source,
  warning,
  onDismiss,
}: {
  kind?: DataStatusKind;
  source?: string | null;
  warning?: string | null;
  onDismiss?: () => void;
}) {
  const detectedKind = detectDataStatusKind({ kind, source, warning });
  if (!detectedKind || detectedKind === "live") return null;

  const cfg = STATUS_CONFIG[detectedKind];

  return (
    <div
      className={`data-status-banner data-status-banner--${cfg.tone}`}
      role="status"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 14px",
        margin: "8px 0 12px",
        borderRadius: "6px",
        background:
          cfg.tone === "negative"
            ? "rgba(239, 68, 68, 0.12)"
            : cfg.tone === "warning"
              ? "rgba(245, 158, 11, 0.12)"
              : "rgba(59, 130, 246, 0.12)",
        border: `1px solid ${
          cfg.tone === "negative"
            ? "rgba(239, 68, 68, 0.3)"
            : cfg.tone === "warning"
              ? "rgba(245, 158, 11, 0.3)"
              : "rgba(59, 130, 246, 0.3)"
        }`,
        color: "inherit",
        fontSize: "0.84rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <DataStatusBadge kind={detectedKind} hideWhenLive={false} />
        <span>{warning || cfg.tooltip}</span>
      </div>
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          style={{ background: "none", border: "none", cursor: "pointer", opacity: 0.7, padding: 4 }}
          aria-label="Dismiss banner"
        >
          ✕
        </button>
      ) : null}
    </div>
  );
}
