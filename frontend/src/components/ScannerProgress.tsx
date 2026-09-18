import { memo, useEffect, useState } from "react";

import { formatScanTime } from "./StatusCards";

interface ScannerProgressData {
  stage: string;
  progress: number;
  current_symbol?: string;
  worker_id?: number;
  done?: number;
  remaining?: number;
  total_fetch?: number;
  total_scoring?: number;
  eta_sec?: number;
  processed_count?: number;
  total_count?: number;
}

interface ScannerProgressProps {
  data: ScannerProgressData;
  error: string | null;
  onRetry?: () => void;
  startTime: number | null;
  title?: string;
  variant?: "running" | "completed";
  completedAt?: string | null;
}

function formatEta(seconds: number | undefined): string {
  if (seconds == null || seconds <= 0) return "--";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

export function formatElapsedClock(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  return `${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
}

export const ScannerProgress = memo(function ScannerProgress({
  data,
  error,
  onRetry,
  startTime,
  title,
  variant = "running",
  completedAt,
}: ScannerProgressProps) {
  const [elapsed, setElapsed] = useState(() =>
    startTime ? Math.max(0, Math.floor((Date.now() - startTime) / 1000)) : 0,
  );

  useEffect(() => {
    if (!startTime || error || variant === "completed" || data.progress >= 100) return;
    setElapsed(Math.max(0, Math.floor((Date.now() - startTime) / 1000)));
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime, error, data.progress, variant]);

  if (variant === "completed" && !error) {
    const when = formatScanTime(completedAt);
    return (
      <div className="scanner-progress scanner-progress--completed" role="status">
        <div className="scanner-progress__header">
          <div className="scanner-progress__title">
            <span className="scanner-progress__dot scanner-progress__dot--done" aria-hidden>
              ✓
            </span>
            {title || "SCAN COMPLETED"}
          </div>
        </div>
        {when ? <div className="scanner-progress__stage">Completed: {when}</div> : null}
      </div>
    );
  }

  if (error) {
    return (
      <div className="scanner-progress scanner-progress--error" role="alert">
        <div className="scanner-progress__header">
          <div className="scanner-progress__title">
            <span className="scanner-progress__dot scanner-progress__dot--error" aria-hidden />
            SCAN FAILED
          </div>
        </div>
        {data.stage ? <div className="scanner-progress__stage">Stage: {data.stage}</div> : null}
        <div className="scanner-progress__error-content">
          <span className="scanner-progress__error-icon" aria-hidden>🔴</span>
          <span>{error}</span>
        </div>
        {onRetry && (
          <button type="button" className="ds-btn ds-btn--primary" onClick={onRetry}>
            Retry Scan
          </button>
        )}
      </div>
    );
  }

  const pct = Math.min(data.progress, 100);
  const total = data.total_fetch || data.total_scoring || 0;
  const completed = data.done || 0;
  const remaining = data.remaining ?? 0;

  return (
    <div className="scanner-progress">
      <div className="scanner-progress__header">
        <div className="scanner-progress__title">
          <span className="scanner-progress__dot" aria-hidden />
          {title || "SCAN IN PROGRESS"}
        </div>
        <div className="scanner-progress__timing">
          <span className="scanner-progress__elapsed">{formatElapsedClock(elapsed)} elapsed</span>
          {data.eta_sec != null && data.eta_sec > 0 && (
            <span className="scanner-progress__eta">ETA {formatEta(data.eta_sec)}</span>
          )}
        </div>
      </div>

      <div className="scanner-progress__stage">Current stage: {data.stage}</div>

      <div className="scanner-progress__bar-track">
        <div
          className="scanner-progress__bar-fill"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="scanner-progress__stats">
        {(data.processed_count != null && data.total_count != null) ? (
          <span className="scanner-progress__stat">
            {data.processed_count} / {data.total_count}
          </span>
        ) : total > 0 ? (
          <span className="scanner-progress__stat">
            {completed} / {total}
          </span>
        ) : null}
        {data.current_symbol && (
          <span className="scanner-progress__stat">
            Current: <strong>{data.current_symbol}</strong>
          </span>
        )}
        {data.worker_id != null && (
          <span className="scanner-progress__stat">
            Worker #{data.worker_id}
          </span>
        )}
        <span className="scanner-progress__stat">
          {pct.toFixed(0)}%
        </span>
      </div>
    </div>
  );
});
