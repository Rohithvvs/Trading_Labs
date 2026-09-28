import React, { memo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { placePaperOrder } from "../../api";
import type { PaperOrderTicketState } from "../../types";

export const QuickTradeWidget: React.FC = memo(function QuickTradeWidget() {
  const navigate = useNavigate();
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [symbol, setSymbol] = useState("RELIANCE");
  const [qty, setQty] = useState(1);
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">("MARKET");
  const [productType, setProductType] = useState<"MIS" | "CNC">("MIS");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; isError?: boolean } | null>(null);

  const handlePlaceOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim() || qty <= 0) return;

    setLoading(true);
    setMessage(null);

    const cleanSymbol = symbol.trim().toUpperCase().replace("-EQ", "");
    const ticket: PaperOrderTicketState = {
      symbol: cleanSymbol,
      side,
      type: orderType,
      productType,
      qty,
      limitPrice: orderType === "LIMIT" && limitPrice ? Number(limitPrice) : null,
      stopLoss: null,
      target: null,
    };

    try {
      const response = await placePaperOrder(ticket, crypto.randomUUID());
      const orderId = (response as any).order_id ?? (response as any).order?.id;
      const status = (response as any).status ?? (response as any).order?.status;
      setMessage({
        text: `✓ ${side} ${qty} ${cleanSymbol} placed (#${orderId || "OK"} - ${status || "SUBMITTED"})`,
        isError: false,
      });
      setTimeout(() => setMessage(null), 5000);
    } catch (err: any) {
      setMessage({
        text: err?.message || "Failed to place paper order",
        isError: true,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="terminal-card" aria-label="Quick Paper Trade">
      <div className="terminal-card__header">
        <h3 className="terminal-card__title">
          <span>Quick Trade</span>
          <span className="terminal-card__subtitle">(Paper Desk)</span>
        </h3>
        <button
          type="button"
          className="terminal-link-btn"
          onClick={() => navigate("/paper")}
        >
          Open Desk
        </button>
      </div>

      {/* BUY / SELL Switcher */}
      <div className="quick-trade-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={side === "BUY"}
          className={`quick-trade-tab is-buy ${side === "BUY" ? "is-active" : ""}`}
          onClick={() => setSide("BUY")}
        >
          BUY
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={side === "SELL"}
          className={`quick-trade-tab is-sell ${side === "SELL" ? "is-active" : ""}`}
          onClick={() => setSide("SELL")}
        >
          SELL
        </button>
      </div>

      <form className="quick-trade-form" onSubmit={handlePlaceOrder}>
        <div className="quick-trade-field">
          <label className="quick-trade-label">Symbol</label>
          <input
            type="text"
            className="quick-trade-input"
            placeholder="Search symbol, e.g. RELIANCE"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            required
            aria-label="Stock Symbol"
          />
        </div>

        <div className="quick-trade-row">
          <div className="quick-trade-field">
            <label className="quick-trade-label">Qty</label>
            <input
              type="number"
              min="1"
              className="quick-trade-input"
              value={qty}
              onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 1))}
              required
              aria-label="Order Quantity"
            />
          </div>

          <div className="quick-trade-field">
            <label className="quick-trade-label">Order Type</label>
            <select
              className="quick-trade-select"
              value={orderType}
              onChange={(e) => setOrderType(e.target.value as "MARKET" | "LIMIT")}
              aria-label="Order Type"
            >
              <option value="MARKET">Market</option>
              <option value="LIMIT">Limit</option>
            </select>
          </div>
        </div>

        <div className="quick-trade-row">
          <div className="quick-trade-field">
            <label className="quick-trade-label">Product</label>
            <select
              className="quick-trade-select"
              value={productType}
              onChange={(e) => setProductType(e.target.value as "MIS" | "CNC")}
              aria-label="Product Type"
            >
              <option value="MIS">Intraday (MIS)</option>
              <option value="CNC">Delivery (CNC)</option>
            </select>
          </div>

          {orderType === "LIMIT" && (
            <div className="quick-trade-field">
              <label className="quick-trade-label">Limit Price (₹)</label>
              <input
                type="number"
                step="0.05"
                min="0.05"
                placeholder="Price"
                className="quick-trade-input"
                value={limitPrice}
                onChange={(e) => setLimitPrice(e.target.value)}
                required
                aria-label="Limit Price"
              />
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={loading}
          className={`quick-trade-submit ${side === "SELL" ? "is-sell" : ""}`}
        >
          {loading ? "Placing Order…" : `Place Paper ${side} Order`}
        </button>

        {message && (
          <div
            style={{
              padding: "6px 8px",
              borderRadius: "var(--mk-radius-sm)",
              fontSize: "0.75rem",
              background: message.isError ? "var(--mk-red-bg)" : "var(--mk-green-bg)",
              color: message.isError ? "var(--mk-red)" : "var(--mk-green)",
              border: `1px solid ${message.isError ? "var(--mk-red)" : "var(--mk-green)"}`,
              textAlign: "center",
            }}
          >
            {message.text}
          </div>
        )}
      </form>
    </section>
  );
});
