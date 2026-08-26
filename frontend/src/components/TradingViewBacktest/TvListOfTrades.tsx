import React, { useState, useMemo, useRef, useEffect } from "react";
import type { DashboardTrade } from "../BacktestAnalyticsDashboard";
import type { TvColumnKey, TvTradeItem } from "./types";
import { fmtTvDate, fmtTvPnl, fmtTvPct, fmtTvPrice, fmtTvSize } from "./tvFormatters";

interface TvListOfTradesProps {
  trades: DashboardTrade[];
  initialCapital?: number | null;
  currency?: string;
  symbol?: string;
  loading?: boolean;
}

type SortField = "tradeNumber" | "entry_date" | "exit_date" | "net_pnl" | "pnl_percent";
type SortDirection = "asc" | "desc";
type FilterType = "ALL" | "WINNERS" | "LOSERS" | "OPEN";
type SideFilter = "ALL" | "LONG" | "SHORT";

export const TvListOfTrades: React.FC<TvListOfTradesProps> = ({
  trades: rawTrades,
  initialCapital = 100000,
  currency = "INR",
  symbol = "STOCK",
  loading = false,
}) => {
  const [filter, setFilter] = useState<FilterType>("ALL");
  const [sideFilter, setSideFilter] = useState<SideFilter>("ALL");
  const [search, setSearch] = useState("");
  const [sortCol, setSortCol] = useState<SortField>("tradeNumber");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [showColMenu, setShowColMenu] = useState(false);

  const colMenuRef = useRef<HTMLDivElement>(null);

  // Column visibility state
  const [visibleCols, setVisibleCols] = useState<Record<TvColumnKey, boolean>>({
    trade_number: true,
    type: true,
    action: true,
    date_time: true,
    price: true,
    size: true,
    net_pnl: true,
    return: true,
  });

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (colMenuRef.current && !colMenuRef.current.contains(e.target as Node)) {
        setShowColMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const toggleColumn = (col: TvColumnKey) => {
    setVisibleCols((prev) => ({ ...prev, [col]: !prev[col] }));
  };

  // Convert raw trades to indexed trade items (1-indexed, newest highest trade number)
  const allItems: TvTradeItem[] = useMemo(() => {
    const total = rawTrades.length;
    return rawTrades.map((t, idx) => {
      const q = 1;
      const notional = t.entry_price != null ? q * t.entry_price : null;
      return {
        ...t,
        tradeNumber: idx + 1,
        quantity: q,
        notionalValue: notional,
      };
    });
  }, [rawTrades]);

  // Counts for filters
  const winnersCount = useMemo(() => allItems.filter((t) => (t.pnl_percent ?? 0) > 0 && !t.open).length, [allItems]);
  const losersCount = useMemo(() => allItems.filter((t) => (t.pnl_percent ?? 0) < 0 && !t.open).length, [allItems]);
  const openCount = useMemo(() => allItems.filter((t) => Boolean(t.open)).length, [allItems]);

  // Filter trades
  const filteredTrades = useMemo(() => {
    return allItems.filter((t) => {
      if (filter === "WINNERS" && (t.pnl_percent ?? 0) <= 0) return false;
      if (filter === "LOSERS" && (t.pnl_percent ?? 0) >= 0) return false;
      if (filter === "OPEN" && !t.open) return false;

      if (sideFilter === "LONG" && (t.type || "LONG").toUpperCase() !== "LONG") return false;
      if (sideFilter === "SHORT" && (t.type || "").toUpperCase() !== "SHORT") return false;

      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesDate = String(t.entry_date || "").includes(q) || String(t.exit_date || "").includes(q);
        const matchesType = String(t.type || "").toLowerCase().includes(q);
        const matchesNum = String(t.tradeNumber).includes(q);
        const matchesReason = String(t.reason || t.exit_reason || "").toLowerCase().includes(q);
        if (!matchesDate && !matchesType && !matchesNum && !matchesReason) return false;
      }
      return true;
    });
  }, [allItems, filter, sideFilter, search]);

  // Sort trades (default newest first = tradeNumber descending)
  const sortedTrades = useMemo(() => {
    const list = [...filteredTrades];
    list.sort((a, b) => {
      let valA: any = a[sortCol];
      let valB: any = b[sortCol];
      if (valA == null) return 1;
      if (valB == null) return -1;
      if (typeof valA === "string") {
        return sortDir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return sortDir === "asc" ? Number(valA) - Number(valB) : Number(valB) - Number(valA);
    });
    return list;
  }, [filteredTrades, sortCol, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sortedTrades.length / pageSize));
  const pagedTrades = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedTrades.slice(start, start + pageSize);
  }, [sortedTrades, currentPage, pageSize]);

  const handleSort = (field: SortField) => {
    if (sortCol === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortCol(field);
      setSortDir("desc");
    }
  };

  // Export CSV
  const handleExportCSV = () => {
    if (!allItems.length) return;
    const headers = [
      "Trade Number",
      "Type",
      "Status",
      "Entry Date",
      "Exit Date",
      "Entry Price (INR)",
      "Exit Price (INR)",
      "Size (Qty)",
      "Net PnL (INR)",
      "Return (%)",
      "Exit Reason",
    ];
    const rows = allItems.map((t) => [
      t.tradeNumber,
      t.type || "Long",
      t.open ? "Open" : "Closed",
      t.entry_date || "",
      t.open ? "" : t.exit_date || "",
      t.entry_price != null ? t.entry_price.toFixed(2) : "",
      t.exit_price != null ? t.exit_price.toFixed(2) : "",
      t.quantity,
      t.net_pnl != null ? t.net_pnl.toFixed(2) : "",
      t.pnl_percent != null ? t.pnl_percent.toFixed(2) : "",
      `"${(t.reason || t.exit_reason || "").replace(/"/g, '""')}"`,
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `tradingview_trades_${symbol}_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) {
    return (
      <section className="tv-trades-card" data-testid="tv-list-of-trades">
        <h3 className="tv-trades-title">List of trades</h3>
        <div className="tv-chart-loading-wrap">
          <div className="bt-spinner" />
          <p className="muted-copy" style={{ marginTop: 12 }}>Loading trades...</p>
        </div>
      </section>
    );
  }

  return (
    <section className="tv-trades-card" data-testid="tv-list-of-trades" id="tv-list-of-trades-section">
      {/* Header with Title and Action Icons */}
      <div className="tv-trades-header">
        <h3 className="tv-trades-title">List of trades</h3>

        <div className="tv-trades-actions">
          {/* Export CSV Button */}
          <button
            type="button"
            className="tv-tool-icon-btn"
            onClick={handleExportCSV}
            disabled={!allItems.length}
            title="Download list of trades as CSV"
            aria-label="Export CSV"
          >
            {/* Download icon */}
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
          </button>

          {/* Column Configuration Button */}
          <div className="tv-toolbar__dropdown-wrapper" ref={colMenuRef}>
            <button
              type="button"
              className="tv-tool-icon-btn"
              onClick={() => setShowColMenu(!showColMenu)}
              title="Configure visible columns"
              aria-label="Column configuration"
            >
              {/* Columns icon */}
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <line x1="9" y1="3" x2="9" y2="21" />
                <line x1="15" y1="3" x2="15" y2="21" />
              </svg>
            </button>

            {showColMenu && (
              <div className="tv-dropdown-menu tv-dropdown-menu--cols">
                <div className="tv-dropdown-header">Columns</div>
                {(
                  [
                    { key: "trade_number", label: "Trade number" },
                    { key: "type", label: "Type" },
                    { key: "date_time", label: "Date and time" },
                    { key: "price", label: "Price" },
                    { key: "size", label: "Size" },
                    { key: "net_pnl", label: "Net PnL" },
                    { key: "return", label: "Return" },
                  ] as const
                ).map(({ key, label }) => (
                  <label key={key} className="tv-col-checkbox-label">
                    <input
                      type="checkbox"
                      checked={visibleCols[key]}
                      onChange={() => toggleColumn(key)}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="tv-table-toolbar">
        <div className="tv-filter-pills">
          <button
            type="button"
            className={`tv-filter-pill ${filter === "ALL" ? "is-active" : ""}`}
            onClick={() => { setFilter("ALL"); setCurrentPage(1); }}
          >
            All ({allItems.length})
          </button>
          <button
            type="button"
            className={`tv-filter-pill ${filter === "WINNERS" ? "is-active" : ""}`}
            onClick={() => { setFilter("WINNERS"); setCurrentPage(1); }}
          >
            Winners ({winnersCount})
          </button>
          <button
            type="button"
            className={`tv-filter-pill ${filter === "LOSERS" ? "is-active" : ""}`}
            onClick={() => { setFilter("LOSERS"); setCurrentPage(1); }}
          >
            Losers ({losersCount})
          </button>
          {openCount > 0 && (
            <button
              type="button"
              className={`tv-filter-pill ${filter === "OPEN" ? "is-active" : ""}`}
              onClick={() => { setFilter("OPEN"); setCurrentPage(1); }}
            >
              Open ({openCount})
            </button>
          )}
        </div>

        <div className="tv-side-pills">
          <button
            type="button"
            className={`tv-filter-pill ${sideFilter === "ALL" ? "is-active" : ""}`}
            onClick={() => { setSideFilter("ALL"); setCurrentPage(1); }}
          >
            All Sides
          </button>
          <button
            type="button"
            className={`tv-filter-pill ${sideFilter === "LONG" ? "is-active" : ""}`}
            onClick={() => { setSideFilter("LONG"); setCurrentPage(1); }}
          >
            Long
          </button>
          <button
            type="button"
            className={`tv-filter-pill ${sideFilter === "SHORT" ? "is-active" : ""}`}
            onClick={() => { setSideFilter("SHORT"); setCurrentPage(1); }}
          >
            Short
          </button>
        </div>

        <div className="tv-search-wrap">
          <input
            type="text"
            placeholder="Search date, price, #"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setCurrentPage(1); }}
            className="tv-search-input"
            aria-label="Search trade log"
          />
        </div>
      </div>

      {/* TradingView-Style 2-Subrow Table */}
      {sortedTrades.length ? (
        <div className="tv-table-responsive-container">
          <table className="tv-trades-table">
            <thead>
              <tr>
                {visibleCols.trade_number && (
                  <th
                    className="tv-th-sortable"
                    onClick={() => handleSort("tradeNumber")}
                  >
                    Trade number {sortCol === "tradeNumber" && (sortDir === "desc" ? "↓" : "↑")}
                  </th>
                )}
                {visibleCols.type && <th>Type</th>}
                {visibleCols.date_time && (
                  <th
                    className="tv-th-sortable"
                    onClick={() => handleSort("exit_date")}
                  >
                    Date and time {sortCol === "exit_date" && (sortDir === "desc" ? "↓" : "↑")}
                  </th>
                )}
                {visibleCols.price && <th className="tv-th-right">Price</th>}
                {visibleCols.size && <th className="tv-th-right">Size</th>}
                {visibleCols.net_pnl && (
                  <th
                    className="tv-th-right tv-th-sortable"
                    onClick={() => handleSort("net_pnl")}
                  >
                    Net PnL {sortCol === "net_pnl" && (sortDir === "desc" ? "↓" : "↑")}
                  </th>
                )}
                {visibleCols.return && (
                  <th
                    className="tv-th-right tv-th-sortable"
                    onClick={() => handleSort("pnl_percent")}
                  >
                    Return {sortCol === "pnl_percent" && (sortDir === "desc" ? "↓" : "↑")}
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {pagedTrades.map((trade) => {
                const isLong = (trade.type || "LONG").toUpperCase() === "LONG";
                const isWinner = (trade.pnl_percent ?? 0) > 0;
                const isLoser = (trade.pnl_percent ?? 0) < 0;

                const pnlFmt = fmtTvPnl(trade.net_pnl, true);
                const retFmt = fmtTvPct(trade.pnl_percent, true);

                const sizeData = fmtTvSize(trade.quantity, trade.entry_price, currency);

                return (
                  <React.Fragment key={trade.tradeNumber}>
                    {/* Subrow 1: Exit / Top Row */}
                    <tr className="tv-trade-row tv-trade-row--exit">
                      {visibleCols.trade_number && (
                        <td className="tv-td-num" rowSpan={2}>
                          <span className="tv-trade-num">{trade.tradeNumber}</span>
                          <span className={`tv-trade-side-badge tv-trade-side-badge--${isLong ? "long" : "short"}`}>
                            {isLong ? "Long" : "Short"}
                          </span>
                        </td>
                      )}
                      {visibleCols.type && (
                        <td className="tv-td-action">Exit</td>
                      )}
                      {visibleCols.date_time && (
                        <td className="tv-td-date">
                          {trade.open ? (
                            <span className="tv-open-pill">OPEN</span>
                          ) : (
                            fmtTvDate(trade.exit_date)
                          )}
                        </td>
                      )}
                      {visibleCols.price && (
                        <td className="tv-td-price tv-th-right">
                          {trade.open ? "--" : `${fmtTvPrice(trade.exit_price)} `}
                          {!trade.open && <span className="tv-currency-tag">{currency}</span>}
                        </td>
                      )}
                      {visibleCols.size && (
                        <td className="tv-td-size tv-th-right">
                          {sizeData.qtyStr}
                        </td>
                      )}
                      {visibleCols.net_pnl && (
                        <td
                          className={`tv-td-pnl tv-th-right ${isWinner ? "is-pos" : isLoser ? "is-neg" : ""}`}
                          rowSpan={2}
                        >
                          <strong>{pnlFmt.formatted}</strong>
                          {pnlFmt.formatted !== "--" && <span className="tv-currency-tag">{currency}</span>}
                        </td>
                      )}
                      {visibleCols.return && (
                        <td
                          className={`tv-td-return tv-th-right ${isWinner ? "is-pos" : isLoser ? "is-neg" : ""}`}
                          rowSpan={2}
                        >
                          <strong>{retFmt.formatted}</strong>
                        </td>
                      )}
                    </tr>

                    {/* Subrow 2: Entry / Bottom Row */}
                    <tr className="tv-trade-row tv-trade-row--entry">
                      {visibleCols.type && (
                        <td className="tv-td-action">Entry</td>
                      )}
                      {visibleCols.date_time && (
                        <td className="tv-td-date">
                          {fmtTvDate(trade.entry_date)}
                        </td>
                      )}
                      {visibleCols.price && (
                        <td className="tv-td-price tv-th-right">
                          {fmtTvPrice(trade.entry_price)}{" "}
                          <span className="tv-currency-tag">{currency}</span>
                        </td>
                      )}
                      {visibleCols.size && (
                        <td className="tv-td-size tv-th-right tv-size-notional">
                          {sizeData.notionalStr}
                        </td>
                      )}
                    </tr>
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="tv-trades-empty">
          <p className="muted-copy">No trades match the selected filter criteria.</p>
        </div>
      )}

      {/* Pagination Controls */}
      {sortedTrades.length > 0 && (
        <div className="tv-pagination-row">
          <div className="tv-pagination-info">
            Showing {(currentPage - 1) * pageSize + 1}–
            {Math.min(currentPage * pageSize, sortedTrades.length)} of {sortedTrades.length} trades
          </div>

          <div className="tv-pagination-controls">
            <label className="tv-pagesize-select-wrap">
              <span>Per page:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setCurrentPage(1);
                }}
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>

            <button
              type="button"
              className="tv-page-btn"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              Previous
            </button>
            <span className="tv-page-num-display">
              Page {currentPage} of {totalPages}
            </span>
            <button
              type="button"
              className="tv-page-btn"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
