# Transaction Cost, Brokerage & Statutory Taxation Engine

## 1. Executive Summary & Architecture

The **Transaction Cost & Brokerage Engine** provides high-precision, versioned, configurable, and audited transaction fee and statutory taxation calculations for the Trading Labs paper-trading platform.

Initially specialized for **Indian cash-equity delivery swing trades** (on NSE and BSE), the engine is designed for zero code coupling with trade and P&L execution logic. It models realistic broker structures, regulatory turnover fees, depository fees, and Indian statutory taxes, providing traders with genuine net-of-charges performance tracking and analytical break-even pricing.

```
                      ┌─────────────────────────────────────────┐
                      │              ChargeProfile              │
                      │  (Broker, Exchange, Segment, Version)   │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
┌─────────────────────────┐     ┌─────────────────────┐     ┌─────────────────────────┐
│     Order Previews      │◄────┤    ChargeEngine     ├────►│  Live Trade Execution   │
│  (/charges/preview API) │     │ (Decimal Arithmetic)│     │  (_try_fill_order)      │
└─────────────────────────┘     └──────────┬──────────┘     └────────────┬────────────┘
                                           │                             │
                                           ▼                             ▼
                                ┌─────────────────────┐     ┌─────────────────────────┐
                                │ Break-Even Pricing  │     │  TradeChargeBreakdown   │
                                │   Net P&L >= 0.00   │     │  (Immutable Audit Log)  │
                                └─────────────────────┘     └─────────────────────────┘
```

---

## 2. Indian Cash Delivery Statutory Rules & Rates

The default profile `INDIA_EQUITY_DELIVERY_DEFAULT` adheres strictly to Indian equity delivery regulations:

| Charge Component | Buy Side | Sell Side | Taxable Base |
| :--- | :--- | :--- | :--- |
| **Brokerage** | 0.00 (or flat / % capped) | 0.00 (or flat / % capped) | Order Turnover |
| **STT (Securities Transaction Tax)** | 0.10% (0.0010) | 0.10% (0.0010) | Order Turnover |
| **Exchange Turnover Fee (NSE)** | 0.00307% (0.0000307) | 0.00307% (0.0000307) | Order Turnover |
| **SEBI Turnover Fee** | ₹10 / crore (0.00010%) | ₹10 / crore (0.00010%) | Order Turnover |
| **Clearing Charges** | 0.00 | 0.00 | Order Turnover |
| **Goods & Services Tax (GST)** | 18.00% | 18.00% | **Taxable Services ONLY** (Brokerage + Exchange + SEBI + Clearing) |
| **Stamp Duty** | 0.015% (0.00015) | ₹0.00 (Exempt) | Order Turnover |
| **DP Charges (Depository)** | ₹0.00 (Exempt) | Configurable (e.g. ₹0 to ₹15.93) | Per sell order or ISIN/day |

> [!IMPORTANT]
> **Strict GST Rule**: GST is legally applicable *only* to service charges (Brokerage, Exchange charges, SEBI turnover fees, and Clearing charges). STT, Stamp Duty, and Depository fees are statutory taxes/levies and are **strictly exempt from GST**.

---

## 3. Financial & Accounting Ledger Integrity

### Buy Orders (Entry)
1. **Cash Outlay**: The account's available cash is debited by:
   $$\text{Cash Deducted} = \text{Turnover} + \text{Total Buy Charges}$$
2. **Cost Basis Tracking**:
   - `PaperPosition.invested_value` stores $\text{qty} \times \text{avg\_price}$.
   - `PaperPosition.total_buy_charges` accumulates the exact transaction costs incurred across entries.
3. **Break-Even Price ($P_{\text{be}}$)**: Computed analytically and persisted on `PaperPosition.break_even_price`.

### Sell Orders (Exit)
1. **Cash Realization**:
   $$\text{Net Proceeds Credited} = \text{Turnover} - \text{Total Sell Charges}$$
2. **Buy-side Charge Allocation**:
   $$\text{Allocated Buy Charges} = \text{total\_buy\_charges} \times \frac{\text{exit\_qty}}{\text{position\_qty}}$$
3. **Realized Gross P&L**:
   $$\text{Gross P\&L} = (\text{exit\_price} - \text{avg\_entry\_price}) \times \text{exit\_qty}$$
4. **Total Trade Charges**:
   $$\text{Total Charges} = \text{Allocated Buy Charges} + \text{Total Sell Charges}$$
5. **Realized Net P&L**:
   $$\text{Net P\&L} = \text{Gross P\&L} - \text{Total Charges}$$
6. **Net Return %**:
   $$\text{Net Return \%} = \frac{\text{Net P\&L}}{\text{Invested Capital} + \text{Allocated Buy Charges}} \times 100$$

### Open Positions (Unrealized P&L)
For any open position evaluated at current market price ($P_{\text{ltp}}$):
- **Gross Unrealized P&L**: $(P_{\text{ltp}} - P_{\text{entry}}) \times \text{qty}$
- **Estimated Exit Charges**: Calculated via `calculate_delivery_charges(side='SELL', price=P_ltp, qty=qty)`
- **Net Unrealized P&L**: $\text{Gross Unrealized P\&L} - \text{total\_buy\_charges} - \text{estimated\_exit\_charges}$
- **Net Return %**: $\frac{\text{Net Unrealized P\&L}}{\text{invested\_value} + \text{total\_buy\_charges}} \times 100$

---

## 4. Analytical Break-Even Calculation

To exit a position without losing capital, the sell price must cover the initial purchase value, the buy charges already paid, and all variable/fixed sell charges.

### Mathematical Formulation
Let:
- $V_{\text{buy}} = \text{Turnover}_{\text{buy}} + C_{\text{buy}}$ (Total capital committed on entry)
- $F_{\text{sell}} = \text{DP Charges} + \text{Fixed Brokerage}$ (Fixed sell-side fees)
- $r_v = \text{STT}_{\text{sell}} + \text{Exch}_{\text{sell}} + \text{SEBI} + \text{Brokerage}_{\%} + \text{GST}_{\text{variable}}$ (Total variable sell rate)

The required sell price $P^*$ satisfies:
$$P^* \times Q \times (1 - r_v) - F_{\text{sell}} = V_{\text{buy}}$$

Solving for $P^*$:
$$P^* = \frac{V_{\text{buy}} + F_{\text{sell}}}{Q \times (1 - r_v)}$$

### Step-Up Guarantee
Because individual charge items undergo `ROUND_HALF_UP` rounding to 2 decimal places, the engine evaluates the candidate price through the full calculation suite. If the resulting Net P&L $< 0$, the engine increments the price in $0.01$ (one paisa) intervals until:
$$\text{Net P\&L}(P_{\text{be}}) \ge 0.00$$

---

## 5. Database Schema & Migration

### `charge_profiles`
Versioned profiles capturing broker and exchange rates:
- `id` (Integer Primary Key)
- `broker_id` (String, e.g. "DEFAULT", "ZERODHA", "FYERS")
- `exchange` ("NSE", "BSE")
- `segment` ("EQUITY_DELIVERY", "EQUITY_INTRADAY", etc.)
- `brokerage_type` ("ZERO", "FLAT_PER_EXECUTED_ORDER", "PERCENTAGE", "MIN_OF_PERCENTAGE_OR_FLAT_CAP")
- Rates: `brokerage_rate_pct`, `brokerage_flat_amt`, `brokerage_cap_amt`, `stt_buy_rate`, `stt_sell_rate`, `exchange_txn_buy_rate`, `exchange_txn_sell_rate`, `sebi_turnover_rate`, `gst_rate`, `stamp_duty_buy_rate`, `dp_charge_amount`
- Metadata: `effective_from`, `effective_to`, `is_active`, `rounding_mode`, `decimal_precision`

### `trade_charge_breakdowns`
Immutable audit records persisted for every filled order and exit:
- `id`, `user_id`, `order_id`, `trade_id`, `position_id`
- `symbol`, `side`, `exchange`, `segment`
- `qty`, `price`, `turnover`
- Itemized charges: `brokerage`, `stt`, `exchange_turnover_charges`, `sebi_turnover_charges`, `clearing_charges`, `gst`, `stamp_duty`, `dp_charges`, `total_charges`
- `net_outlay_or_proceeds`, `break_even_exit_price`, `charge_profile_id`

---

## 6. REST API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/v1/paper/charges/profile` | `GET` | Fetches active charge profile for broker/exchange/segment |
| `/api/v1/paper/charges/preview` | `GET/POST` | Pre-trade calculation of turnover, itemized fees, net outlay, and break-even |
| `/api/v1/paper/orders/{order_id}/charges` | `GET` | Retrieves audited charge breakdown for a specific order fill |
| `/api/v1/paper/trades/{trade_id}/charges` | `GET` | Retrieves audited entry and exit charge breakdowns for a closed trade |
| `/api/v1/paper/positions/{position_id}/pnl` | `GET` | Detailed P&L breakdown for an open position (Gross vs Net, Paid & Est Fees) |
| `/api/v1/paper/admin/charges/profiles` | `GET/POST` | List and create new versioned charge profiles |

---

## 7. Frontend Integration

1. **`PaperOrderPage.tsx`**:
   - Risk Summary panel dynamically displays **Gross Value**, **Brokerage**, **Total Taxes & Charges**, **Net Outlay Required**, and **Break-Even Exit Price**.
   - Confirmation Modal renders a full itemized tax breakdown (STT, Exchange + SEBI fees, 18% GST, Stamp Duty / DP charges, Net Total).
2. **`PaperTradingPage.tsx`**:
   - **Open Positions Table & Cards**: Real-time display of **Break-Even Price**, **Gross P&L**, **Taxes & Charges**, **Net Unrealized P&L**, and **% Net Return**.
   - **Trade History Table & Cards**: Itemizes **Gross P&L**, **Total Charges**, **Net P&L**, and **Break-Even Price**.
   - **Trade Details Modal**: Directly fetches and renders the immutable `TradeChargeBreakdown` audit log for historical inspection.

---

## 8. Verification & Test Suite

All unit and integration tests are verified:
- `tests/unit/test_charge_engine.py`:
  - `test_default_buy_delivery_charges` (PASS)
  - `test_default_sell_delivery_charges` (PASS)
  - `test_flat_brokerage_with_dp_charges` (PASS)
  - `test_percentage_capped_brokerage` (PASS)
  - `test_break_even_sell_price_guarantee` (PASS)
- `tests/unit/test_charge_api.py`:
  - `test_charge_profile_route` (PASS)
  - `test_charge_preview_routes` (PASS)
  - `test_end_to_end_charges_execution_and_audit` (PASS)
- Frontend Build & Typecheck:
  - `npm run build` (1047 modules transformed, 0 errors, PASS)

