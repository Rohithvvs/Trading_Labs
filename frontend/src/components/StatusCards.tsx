import { memo, useEffect, useMemo, useState } from "react";

export function formatScanTime(isoString: string | null | undefined): string | null {
  if (!isoString) return null;
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

function formatDuration(seconds: number | null): string | null {
  if (seconds == null || seconds < 0) return null;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/** Display-only NSE cash session (IST). Does not gate trading. */
function getNseMarketSession(now = new Date()): { open: boolean; label: string } {
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Kolkata",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(now);

    const weekday = parts.find((p) => p.type === "weekday")?.value ?? "";
    const hour = Number(parts.find((p) => p.type === "hour")?.value ?? "0");
    const minute = Number(parts.find((p) => p.type === "minute")?.value ?? "0");
    const mins = hour * 60 + minute;

    // Sat / Sun closed
    if (weekday === "Sat" || weekday === "Sun") {
      return { open: false, label: "Closed" };
    }

    // Regular session 09:15 – 15:30 IST
    const open = mins >= 9 * 60 + 15 && mins < 15 * 60 + 30;
    return { open, label: open ? "Open" : "Closed" };
  } catch {
    return { open: false, label: "—" };
  }
}

type MarketStatusCardProps = {
  compact?: boolean;
};

export const MarketStatusCard = memo(function MarketStatusCard({ compact }: MarketStatusCardProps) {
  const [session, setSession] = useState(() => getNseMarketSession());

  useEffect(() => {
    const id = window.setInterval(() => setSession(getNseMarketSession()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <article
      className={`status-card${compact ? " status-card--compact" : ""}`}
      data-status={session.open ? "open" : "closed"}
      aria-label="Market status"
    >
      <span className="status-card__label">Market</span>
      <span className="status-card__value">
        <span
          className={`status-card__dot status-card__dot--${session.open ? "open" : "closed"}`}
          aria-hidden
        />
        {session.label}
      </span>
      {!compact ? (
        <span className="status-card__subtitle">NSE · 09:15–15:30 IST</span>
      ) : null}
    </article>
  );
});

type LastScanCardProps = {
  lastScanAt: string | null | undefined;
  isLoading: boolean;
  scannedSymbols: number | null | undefined;
  durationSec: number | null;
  compact?: boolean;
  runningLabel?: string | null;
};

export const LastScanCard = memo(function LastScanCard({
  lastScanAt,
  isLoading,
  scannedSymbols,
  durationSec,
  compact,
  runningLabel,
}: LastScanCardProps) {
  const formattedTime = useMemo(() => formatScanTime(lastScanAt), [lastScanAt]);
  const duration = useMemo(() => formatDuration(durationSec), [durationSec]);

  const subtitle = useMemo(() => {
    const parts: string[] = [];
    if (isLoading && formattedTime) parts.push(`Last completed: ${formattedTime}`);
    if (!isLoading && duration) parts.push(`Completed in ${duration}`);
    if (scannedSymbols != null) parts.push(`${scannedSymbols} Stocks`);
    return parts.join(" · ") || undefined;
  }, [duration, scannedSymbols, isLoading, formattedTime]);

  return (
    <article
      className={`status-card${compact ? " status-card--compact" : ""}`}
      aria-label="Last scan completed"
      aria-live="polite"
    >
      <span className="status-card__label">Last Scan Completed</span>
      <span className="status-card__value">
        {isLoading ? (runningLabel || "Scanning…") : formattedTime ?? "No scan completed"}
      </span>
      {!compact && subtitle ? <span className="status-card__subtitle">{subtitle}</span> : compact && isLoading && formattedTime ? (
        <span className="status-card__subtitle">Last completed: {formattedTime}</span>
      ) : null}
    </article>
  );
});

export type StatusCardsProps = {
  lastScanAt: string | null | undefined;
  isLoading: boolean;
  scannedSymbols: number | null | undefined;
  durationSec: number | null;
  compact?: boolean;
  className?: string;
  /** Show Market open/closed card (default true for desk header). */
  showMarket?: boolean;
  runningLabel?: string | null;
};

export const StatusCards = memo(function StatusCards({
  lastScanAt,
  isLoading,
  scannedSymbols,
  durationSec,
  compact,
  className = "",
  showMarket = true,
  runningLabel,
}: StatusCardsProps) {
  return (
    <section
      className={`status-cards-row${compact ? " status-cards-row--compact" : ""} ${className}`.trim()}
      aria-label="Scanner status"
    >
      {showMarket ? <MarketStatusCard compact={compact} /> : null}
      <LastScanCard
        lastScanAt={lastScanAt}
        isLoading={isLoading}
        scannedSymbols={scannedSymbols}
        durationSec={durationSec}
        compact={compact}
        runningLabel={runningLabel}
      />
    </section>
  );
});
