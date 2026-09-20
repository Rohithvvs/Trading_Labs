import React from "react";
import type { StrategyResultRow } from "../../api_strategy_tester";

interface AllStockResultsTableProps {
  title?: string;
  results: StrategyResultRow[];
  totalResults: number;
  selectedSymbol: string | null;
  searchQuery: string;
  signalFilter: string;
  returnFilter: string;
  sortColumn: string;
  sortDirection: "asc" | "desc";
  currentPage: number;
  pageSize: number;
  visibleColumns?: Set<string>;
  buyCount?: number;
  watchCount?: number;
  rejectCount?: number;
  failedCount?: number;
  onSearchChange: (q: string) => void;
  onSignalFilterChange: (sig: string) => void;
  onReturnFilterChange: (ret: string) => void;
  onSortChange: (col: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onStockSelect: (symbol: string) => void;
  onColumnsClick: () => void;
  onExportClick: () => void;
  variant?: "strategy" | "scanner";
  caption?: string;
}

export function formatINR(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return `₹${val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatVolume(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
  return val.toLocaleString("en-IN");
}

const signalOrderWeight = (sig: string | null | undefined, variant: "strategy" | "scanner" = "strategy"): number => {
  const s = (sig || "").toUpperCase();
  if (variant === "scanner") {
    if (s === "MATCH" || s === "MATCHED") return 1;
    if (s === "REJECT" || s === "FAILED") return 2;
    if (s === "SKIPPED") return 3;
    return 4;
  }
  if (s === "BUY") return 1;
  if (s === "WATCH") return 2;
  if (s === "REJECT") return 3;
  if (s === "FAILED") return 4;
  return 5;
};

export const AllStockResultsTable: React.FC<AllStockResultsTableProps> = ({
  title,
  results,
  totalResults,
  selectedSymbol,
  searchQuery,
  signalFilter,
  returnFilter,
  sortColumn,
  sortDirection,
  currentPage,
  pageSize,
  visibleColumns,
  buyCount = 42,
  watchCount = 183,
  rejectCount = 530,
  failedCount = 0,
  onSearchChange,
  onSignalFilterChange,
  onReturnFilterChange,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  onStockSelect,
  onColumnsClick,
  onExportClick,
  variant = "strategy",
  caption,
}) => {
  const isColVisible = (colKey: string) => {
    if (!visibleColumns) return true;
    return visibleColumns.has(colKey);
  };

  const totalPages = Math.max(1, Math.ceil(totalResults / pageSize));
  const from = totalResults > 0 ? (currentPage - 1) * pageSize + 1 : 0;
  const to = Math.min(currentPage * pageSize, totalResults);

  const sortedRows = React.useMemo(() => {
    if (variant !== "scanner" && signalFilter !== "ALL" && signalFilter !== "") {
      return results;
    }
    return [...results].sort((a, b) => {
      const weightA = signalOrderWeight(a.signal, variant);
      const weightB = signalOrderWeight(b.signal, variant);
      if (weightA !== weightB) {
        return weightA - weightB;
      }
      if (sortColumn === "return_pct") {
        const retA = a.return_pct ?? -999999;
        const retB = b.return_pct ?? -999999;
        return sortDirection === "asc" ? retA - retB : retB - retA;
      }
      if (sortColumn === "rank") {
        const rankA = a.rank ?? 999999;
        const rankB = b.rank ?? 999999;
        return sortDirection === "asc" ? rankA - rankB : rankB - rankA;
      }
      if (sortColumn === "symbol") {
        return sortDirection === "asc"
          ? a.symbol.localeCompare(b.symbol)
          : b.symbol.localeCompare(a.symbol);
      }
      if (sortColumn === "entry_price") {
        const pA = a.entry_price ?? 0;
        const pB = b.entry_price ?? 0;
        return sortDirection === "asc" ? pA - pB : pB - pA;
      }
      if (sortColumn === "exit_price") {
        const pA = a.exit_price ?? 0;
        const pB = b.exit_price ?? 0;
        return sortDirection === "asc" ? pA - pB : pB - pA;
      }
      return 0;
    });
  }, [results, signalFilter, sortColumn, sortDirection, variant]);

  // Generate pagination items
  const renderPaginationButtons = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      if (currentPage <= 4) {
        pages.push(1, 2, 3, 4, 5, "...", totalPages);
      } else if (currentPage >= totalPages - 3) {
        pages.push(1, "...", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
      } else {
        pages.push(1, "...", currentPage - 1, currentPage, currentPage + 1, "...", totalPages);
      }
    }

    return (
      <div className="st-pagination-pages">
        <button
          type="button"
          className="st-page-num-btn"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          aria-label="Previous page"
        >
          &lt;
        </button>
        {pages.map((p, idx) =>
          typeof p === "number" ? (
            <button
              key={p}
              type="button"
              className={`st-page-num-btn ${p === currentPage ? "is-active" : ""}`}
              onClick={() => onPageChange(p)}
            >
              {p}
            </button>
          ) : (
            <span key={`dots-${idx}`} style={{ color: "#64748b", padding: "0 4px" }}>
              ...
            </span>
          )
        )}
        <button
          type="button"
          className="st-page-num-btn"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          aria-label="Next page"
        >
          &gt;
        </button>
      </div>
    );
  };

  return (
    <section className="st-results-card" id="all-results-section" aria-label="Strategy test results table">
      {/* Table Header: Title + Signal Quick Access Pills */}
      <div className="st-results-header">
        <div className="st-results-title-group">
          <h2 className="st-results-title">
            {title || `All ${totalResults} Stock Results`}
          </h2>
          <p className="st-results-caption" data-testid="scan-semantics-caption">
            {caption ||
              (variant === "scanner"
                ? "MATCHED means every required strategy entry condition passed on the scan bar. REJECTED means at least one required condition did not pass. SKIPPED means the name did not have enough history."
                : "BUY is the last daily bar (same as TradingView Pine Screener): Close ≥ prior 252-session high, volume &gt; 20-day average, Nifty 500 &gt; SMA 50. Hold Return is buy-and-hold from the window start — not a 52-week ATR-trail trade list.")}
          </p>

          {/* Quick Access Signal Selector */}
          <div className="st-signal-quick-pills" role="group" aria-label="Quick signal filters">
            {variant === "scanner" ? (
              <>
                <button
                  type="button"
                  className={`st-signal-pill buy ${signalFilter === "MATCH" ? "is-active" : ""}`}
                  onClick={() => {
                    onSignalFilterChange(signalFilter === "MATCH" ? "ALL" : "MATCH");
                    onPageChange(1);
                  }}
                  data-testid="pill-filter-matched"
                  title="Show MATCHED stocks"
                >
                  <span className="st-pill-dot buy" />
                  <span>MATCHED</span>
                  <span className="st-pill-count">{buyCount}</span>
                </button>
                <button
                  type="button"
                  className={`st-signal-pill reject ${signalFilter === "REJECT" ? "is-active" : ""}`}
                  onClick={() => {
                    onSignalFilterChange(signalFilter === "REJECT" ? "ALL" : "REJECT");
                    onPageChange(1);
                  }}
                  data-testid="pill-filter-rejected"
                  title="Show REJECTED stocks"
                >
                  <span className="st-pill-dot reject" />
                  <span>REJECTED</span>
                  <span className="st-pill-count">{rejectCount}</span>
                </button>
                <button
                  type="button"
                  className={`st-signal-pill watch ${signalFilter === "SKIPPED" ? "is-active" : ""}`}
                  onClick={() => {
                    onSignalFilterChange(signalFilter === "SKIPPED" ? "ALL" : "SKIPPED");
                    onPageChange(1);
                  }}
                  data-testid="pill-filter-skipped"
                  title="Show SKIPPED stocks"
                >
                  <span className="st-pill-dot watch" />
                  <span>SKIPPED</span>
                  <span className="st-pill-count">{watchCount}</span>
                </button>
              </>
            ) : (
              <>
            <button
              type="button"
              className={`st-signal-pill buy ${signalFilter === "BUY" ? "is-active" : ""}`}
              onClick={() => {
                onSignalFilterChange(signalFilter === "BUY" ? "ALL" : "BUY");
                onPageChange(1);
              }}
              data-testid="pill-filter-buy"
              title="Show BUY stocks"
            >
              <span className="st-pill-dot buy" />
              <span>BUY</span>
              <span className="st-pill-count">{buyCount}</span>
            </button>

            <button
              type="button"
              className={`st-signal-pill watch ${signalFilter === "WATCH" ? "is-active" : ""}`}
              onClick={() => {
                onSignalFilterChange(signalFilter === "WATCH" ? "ALL" : "WATCH");
                onPageChange(1);
              }}
              data-testid="pill-filter-watch"
              title="Show WATCH stocks"
            >
              <span className="st-pill-dot watch" />
              <span>WATCH</span>
              <span className="st-pill-count">{watchCount}</span>
            </button>

            <button
              type="button"
              className={`st-signal-pill reject ${signalFilter === "REJECT" ? "is-active" : ""}`}
              onClick={() => {
                onSignalFilterChange(signalFilter === "REJECT" ? "ALL" : "REJECT");
                onPageChange(1);
              }}
              data-testid="pill-filter-reject"
              title="Show REJECT stocks"
            >
              <span className="st-pill-dot reject" />
              <span>REJECT</span>
              <span className="st-pill-count">{rejectCount}</span>
            </button>

            <button
              type="button"
              className={`st-signal-pill failed ${signalFilter === "FAILED" ? "is-active" : ""}`}
              onClick={() => {
                onSignalFilterChange(signalFilter === "FAILED" ? "ALL" : "FAILED");
                onPageChange(1);
              }}
              data-testid="pill-filter-failed"
              title="Show FAILED stocks"
            >
              <span className="st-pill-dot failed" />
              <span>FAILED</span>
              <span className="st-pill-count">{failedCount}</span>
            </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Left-Aligned Controls Toolbar */}
      <div className="st-results-toolbar">
        {/* Search Box */}
        <div className="st-search-box">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search by symbol or company"
            value={searchQuery}
            onChange={(e) => {
              onSearchChange(e.target.value);
              onPageChange(1);
            }}
            data-testid="input-search-stocks"
            aria-label="Search by symbol or company"
          />
          {searchQuery ? (
            <button
              type="button"
              className="st-search-clear"
              onClick={() => {
                onSearchChange("");
                onPageChange(1);
              }}
              aria-label="Clear search"
            >
              ✕
            </button>
          ) : null}
        </div>

        {/* Signals Filter - Strict Order: All Signals -> BUY -> WATCH -> REJECT -> FAILED */}
        <select
          className="st-select-small"
          value={signalFilter}
          onChange={(e) => {
            onSignalFilterChange(e.target.value);
            onPageChange(1);
          }}
          data-testid="select-signal-filter"
          aria-label="Filter by Signal"
        >
          {variant === "scanner" ? (
            <>
              <option value="ALL">All Results ▼</option>
              <option value="MATCH">MATCHED</option>
              <option value="REJECT">REJECTED</option>
              <option value="SKIPPED">SKIPPED</option>
            </>
          ) : (
            <>
              <option value="ALL">All Signals ▼</option>
              <option value="BUY">BUY</option>
              <option value="WATCH">WATCH</option>
              <option value="REJECT">REJECT</option>
              <option value="FAILED">FAILED</option>
            </>
          )}
        </select>

        {/* Returns Filter */}
        <select
          className="st-select-small"
          value={returnFilter}
          onChange={(e) => {
            onReturnFilterChange(e.target.value);
            onPageChange(1);
          }}
          data-testid="select-return-filter"
          aria-label="Filter by Return"
        >
          <option value="ALL">All Returns ▼</option>
          <option value="POSITIVE">Positive Returns</option>
          <option value="NEGATIVE">Negative Returns</option>
          <option value="FLAT">Flat Returns</option>
        </select>

        {/* Columns Button */}
        <button
          type="button"
          className="st-btn-small"
          onClick={onColumnsClick}
          data-testid="btn-columns-modal"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          Columns
        </button>

        {/* Export CSV Button */}
        <button
          type="button"
          className="st-btn-small"
          onClick={onExportClick}
          data-testid="btn-export-csv"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          Export CSV
        </button>
      </div>

      {/* Main Table */}
      <div className="st-main-table-container">
        <table className="st-main-table" data-testid="table-strategy-results">
          <thead>
            <tr>
              {isColVisible("rank") && <th className="sortable" onClick={() => onSortChange("rank")}>Rank</th>}
              {isColVisible("symbol") && <th className="sortable" onClick={() => onSortChange("symbol")}>Symbol</th>}
              {isColVisible("company") && <th>Company</th>}
              {isColVisible("signal") && <th className="sortable" onClick={() => onSortChange("signal")}>Signal</th>}
              {isColVisible("entry_price") && <th className="sortable" style={{ textAlign: "right" }} onClick={() => onSortChange("entry_price")}>{variant === "scanner" ? "Entry" : "Window Start"}</th>}
              {isColVisible("exit_price") && <th className="sortable" style={{ textAlign: "right" }} onClick={() => onSortChange("exit_price")}>{variant === "scanner" ? "Exit" : "Close"}</th>}
              {isColVisible("return_pct") && <th className="sortable" style={{ textAlign: "right" }} onClick={() => onSortChange("return_pct")}>{variant === "scanner" ? "Return %" : "Hold Return %"}</th>}
              {isColVisible("evaluation_date") && <th className="sortable" onClick={() => onSortChange("evaluation_date")}>Scan Date</th>}
              {isColVisible("high_252") && <th className="sortable" style={{ textAlign: "right" }} onClick={() => onSortChange("high_252")}>Prior 252 High</th>}
              {isColVisible("rsi") && <th style={{ textAlign: "right" }}>RSI</th>}
              {isColVisible("sma_20") && <th style={{ textAlign: "right" }}>SMA 20</th>}
              {isColVisible("sma_50") && <th style={{ textAlign: "right" }}>SMA 50</th>}
              {isColVisible("sma_200") && <th style={{ textAlign: "right" }}>SMA 200</th>}
              {isColVisible("volume") && <th style={{ textAlign: "right" }}>Volume</th>}
              {isColVisible("avg_volume") && <th style={{ textAlign: "right" }}>Avg Volume</th>}
              {isColVisible("pass_count") && <th style={{ textAlign: "right" }}>Pass</th>}
              {isColVisible("fail_count") && <th style={{ textAlign: "right" }}>Fail</th>}
              {isColVisible("primary_failure") && <th>Primary Failure</th>}
            </tr>
          </thead>
          <tbody>
            {sortedRows.length === 0 ? (
              <tr>
                <td colSpan={16} style={{ textAlign: "center", padding: "30px", color: "#64748b" }}>
                  No stock results match the selected filters.
                </td>
              </tr>
            ) : (
              sortedRows.map((row) => {
                const isSelected = selectedSymbol?.toUpperCase() === row.symbol?.toUpperCase();
                const returnPct = row.return_pct ?? 0;
                const isPos = returnPct > 0;
                const isNeg = returnPct < 0;

                return (
                  <tr
                    key={row.symbol}
                    className={isSelected ? "is-selected" : ""}
                    onClick={() => onStockSelect(row.symbol)}
                    data-testid={variant === "scanner" ? `indicator-row-${row.symbol}` : `row-stock-${row.symbol}`}
                    style={{ cursor: "pointer" }}
                  >
                    {isColVisible("rank") && <td style={{ color: "#64748b", fontWeight: 600 }}>{row.rank ?? "—"}</td>}
                    {isColVisible("symbol") && (
                      <td
                        style={{ fontWeight: 700, color: "#ffffff" }}
                        data-testid={`stock-symbol-${row.symbol}`}
                      >
                        {row.symbol}
                      </td>
                    )}
                    {isColVisible("company") && (
                      <td style={{ color: "#94a3b8", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }} title={row.company || ""}>
                        {row.company || "—"}
                      </td>
                    )}
                    {isColVisible("signal") && (
                      <td>
                        <span className={`st-badge-signal ${row.signal || "REJECT"}`}>
                          {row.signal || "REJECT"}
                        </span>
                      </td>
                    )}
                    {isColVisible("entry_price") && (
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {formatINR(row.entry_price)}
                      </td>
                    )}
                    {isColVisible("exit_price") && (
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {formatINR(row.close ?? row.exit_price)}
                      </td>
                    )}
                    {isColVisible("return_pct") && (
                      <td
                        style={{
                          textAlign: "right",
                          fontWeight: 700,
                          color: isPos ? "#4ade80" : isNeg ? "#f87171" : "#94a3b8",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {isPos ? `+${returnPct.toFixed(2)}%` : `${returnPct.toFixed(2)}%`}
                      </td>
                    )}
                    {isColVisible("evaluation_date") && (
                      <td style={{ color: "#94a3b8", fontVariantNumeric: "tabular-nums" }}>
                        {row.evaluation_date || row.indicators?.evaluation_date || "—"}
                      </td>
                    )}
                    {isColVisible("high_252") && (
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {formatINR(row.high_252 ?? row.indicators?.high_252 ?? null)}
                      </td>
                    )}
                    {isColVisible("rsi") && (
                      <td style={{ textAlign: "right", color: "#f1f5f9" }}>
                        {row.rsi != null ? row.rsi.toFixed(1) : "—"}
                      </td>
                    )}
                    {isColVisible("sma_20") && (
                      <td style={{ textAlign: "right" }}>
                        {formatINR(row.sma_20)}
                      </td>
                    )}
                    {isColVisible("sma_50") && (
                      <td style={{ textAlign: "right" }}>
                        {formatINR(row.sma_50)}
                      </td>
                    )}
                    {isColVisible("sma_200") && (
                      <td style={{ textAlign: "right" }}>
                        {formatINR(row.sma_200)}
                      </td>
                    )}
                    {isColVisible("volume") && (
                      <td style={{ textAlign: "right" }}>
                        {formatVolume(row.volume)}
                      </td>
                    )}
                    {isColVisible("avg_volume") && (
                      <td style={{ textAlign: "right" }}>
                        {formatVolume(row.avg_volume)}
                      </td>
                    )}
                    {isColVisible("pass_count") && (
                      <td style={{ textAlign: "right", color: "#4ade80", fontWeight: 600 }}>
                        {row.filters_passed ?? row.pass_count ?? 0}
                      </td>
                    )}
                    {isColVisible("fail_count") && (
                      <td style={{ textAlign: "right", color: "#f87171", fontWeight: 600 }}>
                        {row.filters_failed ?? row.fail_count ?? 0}
                      </td>
                    )}
                    {isColVisible("primary_failure") && (
                      <td style={{ color: "#94a3b8", fontSize: "0.72rem" }}>
                        {row.primary_failure_reason ||
                          row.primary_failure ||
                          (variant === "scanner"
                            ? row.signal === "MATCH" || row.signal === "MATCHED"
                              ? "None"
                              : "—"
                            : row.signal === "BUY"
                              ? "None"
                              : "—")}
                      </td>
                    )}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Bar */}
      <div className="st-pagination-bar">
        <div>
          Showing {from} to {to} of {totalResults} results
        </div>

        {renderPaginationButtons()}

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <select
            className="st-select-small"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            data-testid="select-page-size"
            aria-label="Results per page"
          >
            <option value={25}>25 / page ▼</option>
            <option value={50}>50 / page ▼</option>
            <option value={100}>100 / page ▼</option>
          </select>
        </div>
      </div>
    </section>
  );
};
