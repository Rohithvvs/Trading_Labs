import type { CandidateRow, BacktestEquityPoint } from "../types";
import { InfoTooltip } from "./InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";
import { memo, useMemo, useState, useCallback, useEffect } from "react";
import { SignalBadge as DsSignalBadge } from "../design-system";
import { useResearchPrefetch } from "../hooks/useResearchPrefetch";
import { useIsCompactViewport } from "../hooks/useMediaQuery";
import { FeatureGuard } from "./FeatureGuard";
import { displayCanonicalSymbol } from "../utils/canonicalSymbol";
import { Sparkline, downsampleValues } from "./Sparkline";

export const SCANNER_TABLE_PAGE_SIZE = 40;

function rowEquityValues(
  row: CandidateRow,
  backtestData: { equity_curve?: BacktestEquityPoint[] } | undefined,
): number[] {
  const fromBt = backtestData?.equity_curve || [];
  if (fromBt.length > 0) {
    return downsampleValues(fromBt.map((point) => Number(point.equity)).filter(Number.isFinite));
  }
  const fromStrategy = row.w52?.equity_curve || row.ltm?.equity_curve || [];
  if (fromStrategy.length > 0) {
    return downsampleValues(fromStrategy.map((point) => Number(point.equity)).filter(Number.isFinite));
  }
  const ohlcv = row.analysisItem?.ohlcv || [];
  if (ohlcv.length === 0) return [];
  return downsampleValues(ohlcv.slice(-60).map((c) => c.close).filter(Number.isFinite));
}

type CandidateTableProps = {
  rows: CandidateRow[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onBuy?: (row: CandidateRow) => void;
  liveTicks?: Record<string, number>;
  /** Optional export filename prefix. */
  exportFilePrefix?: string;
  sectionLabel?: string;
  heading?: string;
};

export const CandidateTable = memo(function CandidateTable({
  rows,
  selectedSymbol,
  onSelect,
  onBuy,
  liveTicks,
  exportFilePrefix = "scan_results",
  sectionLabel = "Favorites",
  heading = "Scan results",
}: CandidateTableProps) {
  const { handlePrefetch } = useResearchPrefetch();
  const isCompact = useIsCompactViewport();
  const [visibleCount, setVisibleCount] = useState(SCANNER_TABLE_PAGE_SIZE);

  useEffect(() => {
    setVisibleCount(SCANNER_TABLE_PAGE_SIZE);
  }, [rows]);

  useEffect(() => {
    if (!selectedSymbol) return;
    const idx = rows.findIndex((row) => row.symbol === selectedSymbol);
    if (idx >= SCANNER_TABLE_PAGE_SIZE) {
      setVisibleCount((current) => Math.max(current, Math.ceil((idx + 1) / SCANNER_TABLE_PAGE_SIZE) * SCANNER_TABLE_PAGE_SIZE));
    }
  }, [selectedSymbol, rows]);

  const visibleRows = useMemo(() => rows.slice(0, visibleCount), [rows, visibleCount]);
  const hasMore = visibleCount < rows.length;
  const metricHeading = useMemo(() => scoreColumnLabel(visibleRows.length ? visibleRows : rows), [visibleRows, rows]);

  const handleExportCsv = useCallback(() => {
    if (!rows.length) return;
    const headers = ["Rank", "Symbol", "Company Name", "Signal", "Score", "Confidence"];
    const csvRows = rows.map((r) =>
      [
        r.rank ?? "",
        displayCanonicalSymbol(r.symbol),
        r.companyName ?? "",
        r.signal ?? "",
        r.score ?? "",
        r.confidence ?? "",
      ].join(","),
    );
    const blob = new Blob([[headers.join(","), ...csvRows].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${exportFilePrefix}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [rows, exportFilePrefix]);

  const showMore = useCallback(() => {
    setVisibleCount((current) => Math.min(current + SCANNER_TABLE_PAGE_SIZE, rows.length));
  }, [rows.length]);

  if (!rows.length) {
    return (
      <section className="panel table-panel">
        <div className="ds-empty" role="status" aria-live="polite">
          <h3 className="ds-empty__title">No matching stocks</h3>
          <p className="ds-empty__desc">
            Try relaxing the signal filter, score range, or search term to see more scan results.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel table-panel">
      <div className="panel-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <p className="section-label">{sectionLabel}</p>
          <h2>{heading}</h2>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <p className="panel-helper">
            <abbr title="Signal comes from the strategy recommendation. Momentum is not a 0–100 composite score.">Signal</abbr>, metric, trade plan, and support evidence stay aligned in one table.
          </p>
          <FeatureGuard feature="export_data" loadingFallback={null}>
            <button
              type="button"
              onClick={handleExportCsv}
              className="ds-btn ds-btn--secondary ds-btn--sm"
              data-testid="export-data-btn"
              style={{ padding: "4px 12px", fontSize: "0.85rem" }}
            >
              Export CSV
            </button>
          </FeatureGuard>
        </div>
      </div>

      {isCompact ? (
        <div className="candidate-cards" data-testid="candidate-cards">
          {visibleRows.map((row) => (
            <CandidateCard
              key={row.symbol}
              row={row}
              livePrice={liveTicks?.[row.symbol]}
              isSelected={selectedSymbol === row.symbol}
              onSelect={onSelect}
              onBuy={onBuy}
              onPrefetch={handlePrefetch}
            />
          ))}
        </div>
      ) : (
        <div className="table-scroll table-scroll--sticky">
          <table className="candidate-table candidate-table--pro" style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
            <thead>
              <tr>
                <th className="col-sticky-left" style={{ minWidth: "3rem" }}>Rank</th>
                <th className="col-sticky-symbol" style={{ minWidth: "6.5rem" }}>Symbol</th>
                <th style={{ minWidth: "12rem" }}>Company Name</th>
                <th style={{ minWidth: "6.5rem" }}>Signal</th>
                <th style={{ minWidth: "8rem" }}>{metricHeading}</th>
                <th style={{ minWidth: "11rem" }}>Trade plan <InfoTooltip content={TOOLTIPS.SCANNER.ENTRY_PRICE} /></th>
                <th style={{ minWidth: "7rem" }}>Curve <InfoTooltip content="Backtested trailing equity curve" /></th>
                <th style={{ minWidth: "5.5rem" }}>Trend</th>
                <th style={{ minWidth: "5rem" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <CandidateTableRow
                  key={row.symbol}
                  row={row}
                  livePrice={liveTicks?.[row.symbol]}
                  isSelected={selectedSymbol === row.symbol}
                  onSelect={onSelect}
                  onBuy={onBuy}
                  onPrefetch={handlePrefetch}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasMore ? (
        <div className="table-pager" data-testid="scanner-table-pager">
          <span className="muted-copy">
            Showing {visibleRows.length} of {rows.length}
          </span>
          <button
            type="button"
            className="ds-btn ds-btn--secondary ds-btn--sm"
            onClick={showMore}
            data-testid="scanner-show-more"
          >
            Show more
          </button>
        </div>
      ) : rows.length > SCANNER_TABLE_PAGE_SIZE ? (
        <div className="table-pager">
          <span className="muted-copy">Showing all {rows.length} names</span>
        </div>
      ) : null}
    </section>
  );
});

const CandidateCard = memo(function CandidateCard({
  row,
  livePrice,
  isSelected,
  onSelect,
  onBuy,
  onPrefetch,
}: {
  row: CandidateRow;
  livePrice?: number;
  isSelected: boolean;
  onSelect: (symbol: string) => void;
  onBuy?: (row: CandidateRow) => void;
  onPrefetch: (symbol: string) => void;
}) {
  const distanceToEntry = useMemo(() => {
    if (!livePrice || !row.entryHigh) return null;
    return (((livePrice - row.entryHigh) / row.entryHigh) * 100).toFixed(2);
  }, [livePrice, row.entryHigh]);

  const dynamicRiskReward = useMemo(() => {
    if (!livePrice || !row.stopLoss || !row.target1 || livePrice <= row.stopLoss) return null;
    return ((row.target1 - livePrice) / (livePrice - row.stopLoss)).toFixed(2);
  }, [livePrice, row.stopLoss, row.target1]);

  const equityValues = useMemo(
    () => rowEquityValues(row, row.analysisItem?.backtests?.[0]),
    [row],
  );
  const regime = row.newsSentiment === "Bullish" || row.newsSentiment === "Bearish" ? "CATALYST" : "STANDARD";
  const prefetch = () => onPrefetch(row.symbol);

  return (
    <article
      className={`candidate-card ${isSelected ? "is-selected" : ""}`}
      onClick={() => onSelect(row.symbol)}
      onMouseEnter={prefetch}
      onFocus={prefetch}
      onTouchStart={prefetch}
      tabIndex={0}
      role="button"
      aria-label={`${row.symbol} - ${row.signal} - ${metricLabel(row)} ${formatMetric(row)}`}
    >
      <div className="candidate-card__top">
        <div className="candidate-card__symbol-area">
          <span className="candidate-card__rank">#{row.rank ?? "--"}</span>
          <div className="candidate-card__symbol-meta">
            <div className="candidate-card__symbol" title={displayCanonicalSymbol(row.symbol)} data-testid="candidate-symbol">
              {displayCanonicalSymbol(row.symbol)}
            </div>
            {row.companyName ? <div className="candidate-card__company">{row.companyName}</div> : null}
            <div className="candidate-card__volume">{row.volume} Vol</div>
          </div>
        </div>
        <div className="candidate-card__signal">
          <SignalBadge value={row.signal} />
        </div>
      </div>

      <div className="candidate-card__score-row">
        <div className="candidate-card__score-bar">
          <div
            className="candidate-card__score-fill"
            style={{
              width: `${Math.min(metricBarValue(row), 100)}%`,
              background: "var(--accent)",
            }}
          />
        </div>
        <div className="candidate-card__score-label">
          <span>{metricLabel(row)} <strong>{formatMetric(row)}</strong></span>
          <span>Conf <strong>{row.confidence === null || row.confidence === undefined ? "—" : `${Math.round(row.confidence * 100)}%`}</strong></span>
        </div>
      </div>

      <div className="candidate-card__info-grid">
        <div className="candidate-card__info-item">
          <span className="candidate-card__info-label">Entry</span>
          <span className="candidate-card__info-value">
            {formatZone(row.entryLow, row.entryHigh)}
            {livePrice && distanceToEntry != null ? (
              <span style={{ fontSize: "0.85em", marginLeft: "3px", color: livePrice > (row.entryHigh ?? Infinity) ? "var(--negative)" : "var(--positive)" }}>
                live {formatNumber(livePrice)} ({distanceToEntry}%)
              </span>
            ) : null}
          </span>
        </div>
        <div className="candidate-card__info-item">
          <span className="candidate-card__info-label">SL / TP</span>
          <span className="candidate-card__info-value">{formatLevel(row.stopLoss)} / {formatLevel(row.target1)}</span>
        </div>
        <div className="candidate-card__info-item">
          <span className="candidate-card__info-label">R:R</span>
          <span className="candidate-card__info-value" style={{ color: "var(--accent)" }}>
            {dynamicRiskReward !== null ? `${dynamicRiskReward}x` : formatRiskReward(row.riskReward)}
          </span>
        </div>
        <div className="candidate-card__info-item">
          <span className="candidate-card__info-label">Regime</span>
          <span className="candidate-card__info-value">
            <span style={{
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "4px",
              backgroundColor: regime === "CATALYST" ? "var(--positive)" : "var(--surface-2)",
              color: regime === "CATALYST" ? "#fff" : "var(--text-muted)",
            }}>
              {regime}
            </span>
          </span>
        </div>
      </div>

      <div className="candidate-card__equity">
        {equityValues.length > 1 ? (
          <Sparkline values={equityValues} width={220} height={48} />
        ) : (
          <span className="sparkline-empty">No chart data</span>
        )}
      </div>

      <div className="candidate-card__trend">
        <span className="candidate-card__trend-item">{row.trend}</span>
        <span className="candidate-card__trend-item">{row.momentum}</span>
      </div>

      <div className="candidate-card__actions">
        <button
          type="button"
          className="ds-btn ds-btn--buy"
          onClick={(event) => {
            event.stopPropagation();
            onBuy?.(row);
          }}
          disabled={!onBuy || row.signal === "REJECT"}
          title={"BUY on Paper Desk"}
          aria-label={`Buy ${row.symbol}`}
        >
          BUY
        </button>
      </div>
    </article>
  );
});

const CandidateTableRow = memo(function CandidateTableRow({
  row,
  livePrice,
  isSelected,
  onSelect,
  onBuy,
  onPrefetch,
}: {
  row: CandidateRow;
  livePrice?: number;
  isSelected: boolean;
  onSelect: (symbol: string) => void;
  onBuy?: (row: CandidateRow) => void;
  onPrefetch: (symbol: string) => void;
}) {
  const distanceToEntry = useMemo(() => {
    if (!livePrice || !row.entryHigh) return null;
    return (((livePrice - row.entryHigh) / row.entryHigh) * 100).toFixed(2);
  }, [livePrice, row.entryHigh]);

  const dynamicRiskReward = useMemo(() => {
    if (!livePrice || !row.stopLoss || !row.target1 || livePrice <= row.stopLoss) return null;
    return ((row.target1 - livePrice) / (livePrice - row.stopLoss)).toFixed(2);
  }, [livePrice, row.stopLoss, row.target1]);

  const equityValues = useMemo(
    () => rowEquityValues(row, row.analysisItem?.backtests?.[0]),
    [row],
  );

  const regime = row.newsSentiment === "Bullish" || row.newsSentiment === "Bearish" ? "CATALYST" : "STANDARD";
  const prefetch = () => onPrefetch(row.symbol);

  return (
    <tr
      className={isSelected ? "is-selected" : ""}
      onClick={() => onSelect(row.symbol)}
      onMouseEnter={prefetch}
      onFocus={prefetch}
      style={{ cursor: "pointer", borderBottom: "1px solid var(--border-color)" }}
      tabIndex={0}
    >
      <td className="col-sticky-left" style={{ textAlign: "center", color: "var(--text-muted)" }}>{row.rank ?? "--"}</td>
      <td className="symbol-cell col-sticky-symbol">
        <strong data-testid="candidate-symbol">{displayCanonicalSymbol(row.symbol)}</strong>
        <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
          {row.volume} Vol
        </div>
      </td>
      <td className="candidate-table__company" title={row.companyName ?? undefined}>
        {row.companyName || "—"}
      </td>
      <td>
        <SignalBadge value={row.signal} />
        <div style={{ marginTop: "6px" }}>
          <span style={{
            fontSize: "10px",
            fontWeight: 700,
            padding: "2px 6px",
            borderRadius: "4px",
            backgroundColor: regime === "CATALYST" ? "var(--signal-bullish)" : "var(--bg-surface-elevated)",
            color: regime === "CATALYST" ? "#fff" : "var(--text-secondary)",
            letterSpacing: "0.5px",
          }}>
            {regime}
          </span>
        </div>
      </td>
      <td>
        <div style={{ marginBottom: "6px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "2px" }}>
            <span>{metricLabel(row)}</span>
            <strong>{formatMetric(row)}</strong>
          </div>
          <div style={{ width: "100%", height: "4px", background: "var(--bg-surface-elevated)", borderRadius: "2px", overflow: "hidden" }}>
            <div style={{ width: `${Math.min(metricBarValue(row), 100)}%`, height: "100%", background: "var(--accent-primary)" }}></div>
          </div>
        </div>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "2px", color: "var(--text-secondary)" }}>
            <span>Conviction</span>
            <strong>{row.confidence === null || row.confidence === undefined ? "N/A" : `${Math.round(row.confidence * 100)}%`}</strong>
          </div>
          <div style={{ width: "100%", height: "4px", background: "var(--bg-surface-elevated)", borderRadius: "2px", overflow: "hidden" }}>
            <div style={{ width: `${Math.min((row.confidence || 0) * 100, 100)}%`, height: "100%", background: "var(--text-muted)" }}></div>
          </div>
        </div>
      </td>
      <td style={{ fontSize: "13px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-muted)" }}>Entry:</span>
            <strong>
              {formatZone(row.entryLow, row.entryHigh)}
              {livePrice && distanceToEntry != null ? (
                <span style={{ fontSize: "0.85em", marginLeft: "4px", color: livePrice > (row.entryHigh ?? Infinity) ? "var(--signal-bearish)" : "var(--signal-bullish)" }}>
                  live {formatNumber(livePrice)} ({distanceToEntry}%)
                </span>
              ) : null}
            </strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-muted)" }}>SL / TP:</span>
            <span style={{ fontWeight: 500 }}>{formatLevel(row.stopLoss)} <span style={{ color: "var(--border-color)" }}>|</span> {formatLevel(row.target1)}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-muted)" }}>R:R:</span>
            <span style={{ color: "var(--accent-primary)", fontWeight: 600 }}>{dynamicRiskReward !== null ? `${dynamicRiskReward}x` : formatRiskReward(row.riskReward)}</span>
          </div>
        </div>
      </td>
      <td>
        <div className="sparkline-cell">
          {equityValues.length > 1 ? (
            <Sparkline values={equityValues} />
          ) : (
            <span className="sparkline-empty">No chart data</span>
          )}
        </div>
      </td>
      <td style={{ fontSize: "12px" }}>
        <div>{row.trend}</div>
        <div style={{ color: "var(--text-muted)", marginTop: "2px" }}>{row.momentum}</div>
      </td>
      <td>
        <button
          type="button"
          className="ds-btn ds-btn--buy ds-btn--sm"
          onClick={(event) => {
            event.stopPropagation();
            onBuy?.(row);
          }}
          disabled={!onBuy || row.signal === "REJECT"}
          title={"BUY on Paper Desk"}
          aria-label={`Buy ${row.symbol}`}
        >
          BUY
        </button>
      </td>
    </tr>
  );
});

function SignalBadge({ value }: { value: CandidateRow["signal"] }) {
  return <DsSignalBadge signal={value} />;
}

function metricLabel(row: CandidateRow) {
  return row.scoreLabel || (row.scoreKind === "momentum_252" ? "Momentum 252" : row.scoreKind === "momentum_60" ? "Momentum 60" : "Score");
}

function scoreColumnLabel(rows: CandidateRow[]) {
  const labels = new Set(rows.map((row) => metricLabel(row)));
  return labels.size === 1 ? [...labels][0] : "Metric";
}

function formatMetric(row: CandidateRow) {
  if (row.scoreKind === "momentum_252" || row.scoreKind === "momentum_60") {
    return row.momentumValue == null ? "—" : `${row.momentumValue.toFixed(1)}%`;
  }
  return row.score == null ? "—" : row.score.toFixed(1);
}

function metricBarValue(row: CandidateRow) {
  if (row.scoreKind === "momentum_252" || row.scoreKind === "momentum_60") {
    return row.momentumValue ?? 0;
  }
  return row.score ?? 0;
}

function formatNumber(value: number | null) {
  return value == null ? "—" : value.toFixed(2);
}

function formatLevel(value: number | null) {
  return value == null ? "Not available" : value.toFixed(2);
}

function formatRiskReward(value: number | null) {
  return value == null ? "—" : `${value.toFixed(2)}x`;
}

function formatZone(low: number | null, high: number | null) {
  if (low == null && high == null) return "Not available";
  if (low != null && high != null && low === high) return low.toFixed(2);
  if (low != null && high != null) return `${low.toFixed(2)} - ${high.toFixed(2)}`;
  return (low ?? high)!.toFixed(2);
}
