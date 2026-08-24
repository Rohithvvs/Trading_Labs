import { memo, useCallback, useEffect, useMemo, useState } from "react";
import type { ScreenerConditionResult } from "../types";
import { InfoTooltip } from "./InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";
import { displayCanonicalSymbol } from "../utils/canonicalSymbol";
import { lookupUniverseInstrument, type UniverseInstrument } from "../utils/universeInstruments";
import { useIsCompactViewport } from "../hooks/useMediaQuery";

const ANALYZED_PAGE_SIZE = 50;

type AllAnalyzedStocksTableProps = {
  stocks: ScreenerConditionResult[];
  instruments?: Map<string, UniverseInstrument>;
};

function getRejectionReasons(conditions: Record<string, boolean>, matched: boolean): string[] {
  if (matched) {
    return ["Passed all checks"];
  }

  const reasons: string[] = [];

  if (conditions.data_source_failed) reasons.push("No live data available");
  if (conditions.data_quality_failed) reasons.push("Insufficient historical data");
  if (!conditions.broad_trend_eligibility) reasons.push("Failed broad trend check");
  if (!conditions.hard_filters_pass) reasons.push("Failed hard filters");
  if (!conditions.core_trend_filter_pass) reasons.push("Trend filter failed");
  if (!conditions.core_momentum_filter_pass) reasons.push("Momentum filter failed");
  if (!conditions.basic_liquidity_filter_pass) reasons.push("Liquidity filter failed");

  return reasons.length > 0 ? reasons : ["Failed final threshold"];
}

const EMPTY_INSTRUMENTS = new Map<string, UniverseInstrument>();

export const AllAnalyzedStocksTable = memo(function AllAnalyzedStocksTable({
  stocks,
  instruments,
}: AllAnalyzedStocksTableProps) {
  const instrumentMap = instruments ?? EMPTY_INSTRUMENTS;
  const isCompact = useIsCompactViewport();
  const [visibleCount, setVisibleCount] = useState(ANALYZED_PAGE_SIZE);

  useEffect(() => {
    setVisibleCount(ANALYZED_PAGE_SIZE);
  }, [stocks]);

  const companyName = (stock: ScreenerConditionResult) =>
    stock.company_name || lookupUniverseInstrument(stock.symbol, instrumentMap)?.company_name || "—";

  const orderedStocks = useMemo(() => {
    const passed: ScreenerConditionResult[] = [];
    const failed: ScreenerConditionResult[] = [];
    for (let i = 0; i < stocks.length; i++) {
      if (stocks[i].matched) passed.push(stocks[i]);
      else failed.push(stocks[i]);
    }
    return [...passed, ...failed];
  }, [stocks]);

  const visibleStocks = useMemo(
    () => orderedStocks.slice(0, visibleCount),
    [orderedStocks, visibleCount],
  );

  const showMore = useCallback(() => {
    setVisibleCount((current) => Math.min(current + ANALYZED_PAGE_SIZE, orderedStocks.length));
  }, [orderedStocks.length]);

  if (!stocks.length) {
    return (
      <section className="panel empty-state">
        <h2>No stocks analyzed</h2>
        <p>Run the scanner to see all analyzed stocks here.</p>
      </section>
    );
  }

  let matchedCount = 0;
  let rejectedCount = 0;
  let dataIssueCount = 0;
  for (let i = 0; i < stocks.length; i++) {
    const s = stocks[i];
    if (s.matched) matchedCount++;
    else rejectedCount++;
    if (s.conditions?.data_source_failed || s.conditions?.data_quality_failed) dataIssueCount++;
  }

  const hasMore = visibleCount < orderedStocks.length;

  return (
    <section className="panel table-panel">
      <div className="panel-header">
        <div>
          <p className="section-label">Complete Analysis</p>
          <h2>All {stocks.length} analyzed stocks</h2>
        </div>
        <p className="panel-helper">
          {matchedCount} passed, {rejectedCount} rejected
        </p>
      </div>

      {dataIssueCount > 0 ? (
        <div className="data-issue-banner" role="status" aria-live="polite">
          <strong>⚠ {dataIssueCount} stocks were skipped due to missing or low-quality data.</strong>
          <div className="data-issue-banner__hint">Check your FYERS connection or increase the lookback window.</div>
        </div>
      ) : null}

      {isCompact ? (
        <div className="analyzed-cards">
          {visibleStocks.map((stock) => {
            const reasons = getRejectionReasons(stock.conditions, stock.matched);
            const isDataIssue = stock.conditions.data_source_failed || stock.conditions.data_quality_failed;
            return (
              <article
                key={stock.symbol}
                className={`analyzed-card ${stock.matched ? "row-passed" : `row-rejected ${isDataIssue ? "row-data-issue" : ""}`}`}
              >
                <div className="analyzed-card__top">
                  <div className="analyzed-card__symbol">{displayCanonicalSymbol(stock.symbol)}</div>
                  <div className="analyzed-card__company">{companyName(stock)}</div>
                  {stock.matched ? (
                    <span className="badge badge-success">Passed</span>
                  ) : (
                    <span className={`badge ${isDataIssue ? "badge-warning" : "badge-danger"}`}>
                      {isDataIssue ? "Warning" : "Failed"}
                    </span>
                  )}
                </div>
                <div className="analyzed-card__grid">
                  <div>
                    <span>Close</span>
                    <strong>{stock.close > 0 ? stock.close.toFixed(2) : "N/A"}</strong>
                  </div>
                  <div>
                    <span>Score</span>
                    <strong>{stock.screener_score.toFixed(1)}</strong>
                  </div>
                  <div>
                    <span>Signal</span>
                    <strong>{stock.technical_signal || "—"}</strong>
                  </div>
                  <div>
                    <span>Volume</span>
                    <strong>{stock.volume > 0 ? `${(stock.volume / 1000000).toFixed(1)}M` : "N/A"}</strong>
                  </div>
                  <div>
                    <span>EMA-20</span>
                    <strong>{stock.ema_20 > 0 ? stock.ema_20.toFixed(2) : "N/A"}</strong>
                  </div>
                  <div>
                    <span>SMA-50</span>
                    <strong>{stock.sma_50 > 0 ? stock.sma_50.toFixed(2) : "N/A"}</strong>
                  </div>
                </div>
                <div className="analyzed-card__reason">{reasons.join(" · ")}</div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="table-scroll">
          <table className="candidate-table candidate-table--analyzed">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Company Name</th>
                <th>Close</th>
                <th>
                  Score <InfoTooltip content={TOOLTIPS.SCANNER.SCORE_MIN} />
                </th>
                <th>Tech Signal</th>
                <th>Status</th>
                <th>EMA-20</th>
                <th>SMA-50</th>
                <th>SMA-200</th>
                <th>
                  Volume <InfoTooltip content={TOOLTIPS.SCANNER.VOLUME} />
                </th>
                <th>Rejection Reason</th>
              </tr>
            </thead>
            <tbody>
              {visibleStocks.map((stock) => {
                const reasons = getRejectionReasons(stock.conditions, stock.matched);
                const isDataIssue = stock.conditions.data_source_failed || stock.conditions.data_quality_failed;
                return (
                  <tr
                    key={stock.symbol}
                    className={stock.matched ? "row-passed" : `row-rejected ${isDataIssue ? "row-data-issue" : ""}`}
                  >
                    <td className="symbol-cell">
                      <strong data-testid="analyzed-symbol">{displayCanonicalSymbol(stock.symbol)}</strong>
                    </td>
                    <td>{companyName(stock)}</td>
                    <td className="number-cell">{stock.close > 0 ? stock.close.toFixed(2) : "N/A"}</td>
                    <td className="number-cell">{stock.screener_score.toFixed(1)}</td>
                    <td>{stock.technical_signal}</td>
                    <td>
                      {stock.matched ? (
                        <span className="badge badge-success">Passed</span>
                      ) : (
                        <span className={`badge ${isDataIssue ? "badge-warning" : "badge-danger"}`}>
                          {isDataIssue ? "Warning" : "Failed"}
                        </span>
                      )}
                    </td>
                    <td className="number-cell">{stock.ema_20 > 0 ? stock.ema_20.toFixed(2) : "N/A"}</td>
                    <td className="number-cell">{stock.sma_50 > 0 ? stock.sma_50.toFixed(2) : "N/A"}</td>
                    <td className="number-cell">{stock.sma_200 > 0 ? stock.sma_200.toFixed(2) : "N/A"}</td>
                    <td className="number-cell">{stock.volume > 0 ? (stock.volume / 1000000).toFixed(1) : "N/A"}M</td>
                    <td>
                      {stock.matched ? (
                        <span className="badge badge-success">Passed all checks</span>
                      ) : (
                        <div className="rejection-reasons">
                          {reasons.map((reason, idx) => (
                            <div key={idx} className="reason-item">
                              {reason}
                            </div>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {hasMore ? (
        <div className="table-pager">
          <span className="muted-copy">
            Showing {visibleStocks.length} of {orderedStocks.length}
          </span>
          <button
            type="button"
            className="ds-btn ds-btn--secondary ds-btn--sm"
            onClick={showMore}
            data-testid="analyzed-show-more"
          >
            Show more
          </button>
        </div>
      ) : null}
    </section>
  );
});
