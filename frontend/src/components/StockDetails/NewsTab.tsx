import React from "react";
import type { ArticleItem } from "../../types";

interface NewsTabProps {
  symbol: string;
  articles: ArticleItem[];
  newsSentimentLabel?: string | null;
  newsSentimentScore?: number | null;
  newsSummary?: string | null;
  corporateEvents?: Record<string, any> | null;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export const NewsTab: React.FC<NewsTabProps> = ({
  symbol,
  articles = [],
  newsSentimentLabel,
  newsSentimentScore,
  newsSummary,
  corporateEvents,
  isLoading = false,
  error = null,
  onRetry,
}) => {
  if (isLoading) {
    return (
      <div className="st-card st-card-full st-tab-loading" data-testid="news-loading">
        Loading news...
      </div>
    );
  }

  if (error) {
    return (
      <div className="st-card st-card-full st-tab-error" data-testid="news-error">
        <p>{error || "Unable to load news."}</p>
        {onRetry && (
          <button type="button" className="st-btn-primary" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    );
  }

  const earnings =
    corporateEvents?.earnings_date ??
    corporateEvents?.earnings ??
    corporateEvents?.next_earnings ??
    null;

  const exDividend =
    corporateEvents?.ex_dividend_date ??
    corporateEvents?.ex_dividend ??
    corporateEvents?.exdiv ??
    null;

  const agm = corporateEvents?.agm_date ?? corporateEvents?.agm ?? null;

  return (
    <div className="st-stock-detail-stack" style={{ display: "flex", flexDirection: "column", gap: 14 }} data-testid="card-detail-news">
      {/* Sentiment Banner if present */}
      {(newsSentimentLabel || newsSummary || newsSentimentScore != null) && (
        <section className="st-card st-card-full" data-testid="card-detail-news-sentiment">
          <div className="st-card-title">
            <span>News Sentiment & Overview</span>
            {newsSentimentLabel && (
              <span
                className={`st-status-badge ${
                  newsSentimentLabel.toLowerCase().includes("pos")
                    ? "st-status-badge--completed"
                    : newsSentimentLabel.toLowerCase().includes("neg")
                      ? "st-status-badge--failed"
                      : "st-status-badge--running"
                }`}
              >
                {newsSentimentLabel.toUpperCase()}
                {newsSentimentScore != null ? ` (${newsSentimentScore.toFixed(2)})` : ""}
              </span>
            )}
          </div>
          {newsSummary && (
            <p style={{ color: "#cbd5e1", fontSize: "0.85rem", margin: "4px 0 0 0", lineHeight: 1.5 }}>
              {newsSummary}
            </p>
          )}
        </section>
      )}

      {/* Main Articles List */}
      <section className="st-card st-card-full" data-testid="card-detail-news-articles">
        <h2 className="st-card-title">Latest News</h2>

        {articles.length === 0 ? (
          <div className="st-tab-empty" data-testid="news-empty-state">
            <p style={{ fontSize: "0.9rem", color: "#94a3b8" }}>
              No recent news available for this stock.
            </p>
            <a
              href={`https://www.google.com/search?q=${encodeURIComponent(symbol + " NSE news")}`}
              target="_blank"
              rel="noopener noreferrer"
              className="st-btn-dark"
              style={{ marginTop: 8 }}
            >
              Search Google News for {symbol} ↗
            </a>
          </div>
        ) : (
          <div className="st-news-list" style={{ marginTop: 8 }}>
            {articles.map((article, idx) => (
              <article key={article.url || idx} className="st-news-item" data-testid="news-article-item">
                <div className="st-news-meta">
                  <span className="st-news-source">{article.source || "News"}</span>
                  <span>·</span>
                  <span className="st-news-date">
                    {article.published_at
                      ? new Date(article.published_at).toLocaleDateString("en-IN", {
                          day: "2-digit",
                          month: "short",
                          year: "numeric",
                        })
                      : "—"}
                  </span>
                </div>
                <h3 className="st-news-headline">
                  {article.url ? (
                    <a href={article.url} target="_blank" rel="noopener noreferrer">
                      {article.title}
                    </a>
                  ) : (
                    article.title
                  )}
                </h3>
                {article.description && <p className="st-news-desc">{article.description}</p>}
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Corporate Events if available */}
      {(earnings || exDividend || agm) && (
        <section className="st-card st-card-full" data-testid="card-detail-corporate-events">
          <h2 className="st-card-title">Corporate Events</h2>
          <div className="st-detail-kv-list">
            <div className="st-detail-kv-row">
              <span>Earnings Date</span>
              <span>{earnings || "—"}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>Ex-Dividend Date</span>
              <span>{exDividend || "—"}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>AGM Date</span>
              <span>{agm || "—"}</span>
            </div>
          </div>
        </section>
      )}
    </div>
  );
};
