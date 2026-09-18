# Business Profile

## Nature of Business

### 1. Basic Details

- Name of concern: [TO FILL]
- Product / project name: Trading Labs
- Constitution: [TO FILL]
- Promoter / authorised person: VVS Rohith
- Business address: [TO FILL]
- Nature of business: Information Technology — software product development
- Main activity: Development of software for Indian equities market-data analysis, stock scanning, strategy evaluation, and paper (simulated) trading.

### 2. Product Description

Trading Labs is a software product under development. It is a research and paper-trading workstation for Indian listed equities. The product consists of a web application (React) and a backend application (Python / FastAPI), with data stored in a PostgreSQL database.

The software collects and displays market data. It integrates with the FYERS market-data API to obtain quotes and historical OHLCV (open, high, low, close, volume) candles for NSE stocks. Where configured, other public market-data sources may be used as a fallback. Daily bars and related market data are stored in the application database and shown on Markets, Scanner, and stock-detail screens.

Users can run stock scanners over configured universes (for example NIFTY 500). The scanners apply technical rules, score names, and produce a shortlist with BUY / WATCH / REJECT style research labels. Strategy-specific scans in the product include swing screening, long-term momentum, and 52-week high breakout. A Strategy Tester and Indicator Scanner allow the user to define or import filter rules, run scans on stored price history, and review backtest-style results.

A shortlisted stock can be opened for further research. The software presents technical indicators, charts, news and sentiment where available, a trade-plan summary, and backtest statistics. Users can maintain a watchlist of selected symbols. Scan history, saved scanner presets, and analysis records are stored for later review.

Paper trading in the product is simulated. Each authenticated user has a virtual paper account with a starting paper balance (default ten lakh rupees of simulated capital). Users can place simulated orders, track paper positions, and review paper cash balance, realised and unrealised profit and loss, trade history, and performance analytics. Paper fills use market prices obtained from the market-data feed. They are not sent to a broker as live exchange orders, and they do not move real money or securities.

User access is controlled by authentication. The software supports email-and-password registration and login, optional Google sign-in, session cookies, password reset, and role-based access (trader and admin). An admin panel supports user management and feature-permission controls. The application stores analysis history, paper-trading records, and operational logs in the database.

The FYERS connection is used to fetch market data (quotes, candles, and live ticks used for paper-order simulation) and to store an access token so the application can retrieve that data. The product’s own disclaimer states that the system is advisory only, does not place live trades, and is not financial advice.

### 3. Nature of the Business

This concern is an Information Technology / software product development business. It develops and operates software for market-data analysis and paper or simulated trading.

The product is technology software. Paper trades are simulated inside the application using virtual capital. They do not result in this business buying or selling securities on an exchange for clients.

The software does not hold client funds or securities. Paper-account balances are internal simulated figures used for research and practice. The business is not presenting itself as a stock broker, portfolio manager (PMS), non-banking financial company (NBFC), lender, or payment business. Market data is obtained from a broker’s API (FYERS) for analysis and simulation only.

### 4. Present Stage

The product is under active development and testing. The repository contains a working local development setup (backend, frontend, and database) and cloud hosting configuration for a backend service and a frontend application. Internal project records describe the system as advisory-only software that does not place live trades. The repository does not show a commercially launched brokerage, PMS, or client-money business.

The Current Account will be used for the software business’s own legitimate receipts and operating expenses.

### 5. Intended Account Usage

- Expected credits: founder capital and, when applicable, software, subscription, licence, or IT-service receipts.
- Expected debits: cloud hosting, market-data APIs, software tools, professional fees, contractors, and other business operating expenses.
- Expected transaction mode: primarily digital payments such as NEFT, RTGS, IMPS, UPI, and bank transfers.
- Cash transactions, if any, will be limited to ordinary small business expenses.

### 6. Declaration

I confirm that the above information is true to the best of my knowledge and that the Current Account will be used only for the stated software and IT business.

Place: [TO FILL]

Date: 12 September 2026

Signature: ____________________

Name: VVS Rohith

Designation: [TO FILL]

Mobile: [TO FILL]

Email: [TO FILL]

## Internal Evidence Notes

These notes are for internal review and can be removed before printing.

1. `README.md` — Product described as a stock analysis and recommendation system; advisory only; live order execution is not included.
2. `docs/architecture/SystemOverview.md` — Describes Trading Labs as an advisory-only Indian-equities research and paper-trading workstation that does not place live broker orders; FYERS used for market data.
3. `backend/app/config/settings.py` — Application name “Trading System”; disclaimer: “Advisory only. This system does not place live trades and is not financial advice.”
4. `docs/TRADINGVIEW_VS_TRADING_LABS.md` — Uses the product name Trading Labs; states advisory only and no live broker orders.
5. `backend/app/services/fyers_service.py` — FYERS client used for quotes, OHLCV history, and related market-data retrieval (not live client order placement).
6. `backend/app/routes/paper_trading.py` and `backend/app/models/paper_trading.py` — Paper-trading APIs and virtual paper accounts, positions, orders, and P&L; default simulated starting balance of ₹10,00,000.
7. `backend/app/routes/auth.py` — Email/password signup and login, Google sign-in, session cookies, and password-reset flows.
8. `frontend/src/layout/navConfig.tsx` — Application surfaces: Markets, Strategy Tester, Paper Desk, Performance, and Profile.
9. `docs/USER_MANUAL.md` — End-user flow: connect FYERS for price data, run scanners, review charts and trade plans, and place paper trades.
10. `docs/INDICATOR_SCANNER.md` — Strategy Tester / Indicator Scanner described as research and paper-trading only; not investment advice.
11. `specs/033-market-data-ingestion/spec.md` — Market-data ingestion and daily update of NSE / NIFTY 500 bars into the application database.
12. `render.yaml` and `frontend/vercel.json` — Cloud hosting configuration for the backend and frontend; evidence of development/hosting setup, not of a commercially launched brokerage.
