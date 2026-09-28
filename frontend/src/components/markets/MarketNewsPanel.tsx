import React, { memo } from "react";

interface NewsItem {
  id: string;
  time: string;
  headline: string;
  category?: string;
  source?: string;
}

interface MarketNewsPanelProps {
  news?: NewsItem[] | null;
}

const DEFAULT_NEWS: NewsItem[] = [
  { id: "1", time: "11:42", headline: "RBI keeps repo rate unchanged, maintains neutral stance", category: "MACRO" },
  { id: "2", time: "11:25", headline: "IT stocks gain amid strong global cues", category: "SECTOR" },
  { id: "3", time: "10:58", headline: "Crude oil prices rise 2% on supply concerns", category: "COMMODITY" },
  { id: "4", time: "10:32", headline: "Auto sector under pressure after weak sales data", category: "SECTOR" },
  { id: "5", time: "09:45", headline: "India VIX spikes 12% — volatility expected", category: "MARKET" },
  { id: "6", time: "09:20", headline: "FIIs net sell ₹3,245 Cr in cash segment", category: "FLOWS" },
];

export const MarketNewsPanel: React.FC<MarketNewsPanelProps> = memo(function MarketNewsPanel({
  news,
}) {
  const displayNews = news && news.length > 0 ? news : DEFAULT_NEWS;

  return (
    <section className="terminal-card" aria-label="Latest Market News">
      <div className="terminal-card__header">
        <h3 className="terminal-card__title">
          <span>Latest Market News</span>
        </h3>
        <span className="terminal-card__subtitle">Market Wire</span>
      </div>

      <div className="news-list">
        {displayNews.map((item) => (
          <article key={item.id} className="news-item">
            <span className="news-time">{item.time}</span>
            <div style={{ flex: 1 }}>
              <span className="news-headline">{item.headline}</span>
              {item.category && (
                <span
                  style={{
                    display: "inline-block",
                    marginLeft: 8,
                    fontSize: "0.68rem",
                    padding: "1px 5px",
                    borderRadius: 3,
                    background: "var(--mk-surface-raised)",
                    color: "var(--mk-text-muted)",
                    border: "1px solid var(--mk-border)",
                  }}
                >
                  {item.category}
                </span>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
});
