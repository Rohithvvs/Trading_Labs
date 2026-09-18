# Research: Market Data Ingestion & Daily Update System

**Feature**: `033-market-data-ingestion`  
**Date**: 2026-08-08  
**Status**: Complete — all planning unknowns resolved for design purposes

---

## 1. Strategy-grade storage vs ACS

**Decision:** Dedicated strategy tables (`daily_ohlcv`, `index_ohlcv`, `data_load_log`) as scanner/strategy SoT; ACS and legacy candle tables unchanged and not dual-written.

**Rationale:** Clarification session 2026-08-08 (Option A). Delivery fields, load ownership, and EOD semantics do not fit multi-resolution ACS without invasive schema and regression risk.

**Alternatives considered:**
- Unified ACS extension — cleaner long-term, high risk to production scanner/cache paths in one sprint.
- Dual-write — compatibility tax and consistency burden without immediate benefit.

---

## 2. Universe table vs `stocks_master`

**Decision:** Reuse `stocks_master` as universe; add missing lifecycle columns rather than create a second `universe` table.

**Rationale:** Avoid duplicate membership sources; existing import + startup seed already depend on `stocks_master`.

**Alternatives considered:**
- New `universe` table + sync job — double source of truth.
- Rename table — unnecessary migration churn.

---

## 3. OHLCV provider

**Decision:** FYERS history API via existing `FyersService` for equity and index daily bars; keep existing retry/concurrency patterns.

**Rationale:** Already production-wired for NIFTY500-scale scanning; auth and normalization exist.

**Alternatives considered:**
- yfinance-only — weaker reliability/identity for NSE cash.
- ACS-only backfill — does not add delivery/load product.

---

## 4. Delivery data provider

**Decision:** New `NseDeliveryProvider` consuming official NSE public delivery/bhav-style session reports (file-per-day), joined by ISIN/symbol. Exact published URLs/columns verified at implement time against live NSE artifacts — no invented private APIs.

**Rationale:** App explicitly lacks delivery (`research_service` NA). FYERS path used in-app does not supply delivery %. NSE reports are the domain-standard source for delivery quantity.

**Alternatives considered:**
- Skip delivery until Phase 2 — rejected by clarification (delivery in scope; soft global / hard STR-041).
- Per-symbol scraping — slow and fragile vs bulk daily file.

---

## 5. Delivery gate strictness

**Decision:** Global freshness = OHLCV coverage ≥99% + index present. STR-041 hard-requires delivery per symbol.

**Rationale:** Clarification Option B; avoids ops meltdown when delivery file is late while still protecting STR-041 integrity.

---

## 6. ADTV-20 storage

**Decision:** Compute on demand from last 20 `daily_ohlcv` rows (`close * volume` average). Store `turnover` on each row at ingest for convenience.

**Rationale:** 20 rows × 500 symbols is cheap; avoids third fact table and staleness of pre-aggregates.

**Alternatives considered:**
- Materialized ADTV column updated daily — extra write path, little benefit.
- Redis cache — unnecessary for EOD scanner cadence.

---

## 7. Weekly OHLCV

**Decision:** On-demand resample of daily bars (pandas already used in analysis routes); no weekly table.

**Rationale:** Spec forbids permanent weekly storage; matches STR-045 need.

---

## 8. Daily update trigger

**Decision:** APScheduler post-close job + CLI catch-up.

**Rationale:** Clarification Option B; scanners need data without relying on human operators.

**Clock guidance:** Configurable after 15:30 IST (e.g. 16:30–18:00 IST) with retry when delivery file missing.

---

## 9. Single-flight concurrency

**Decision:** One mutating FULL or DAILY load at a time via `acquire_singleton_lease` (or shared lock name `market_data:load`).

**Rationale:** Clarification Option A; prevents double writers and FYERS stampede.

---

## 10. Operator alert channels

**Decision:** Structured logs + diagnostics/health/status surface; no email requirement for v1.

**Rationale:** Clarification Option B; SMTP optional later.

---

## 11. Package layout

**Decision:** `backend/app/services/market_data_ingestion/{providers,pipelines,validators}` + `backend/app/cli/market_data_cli.py`.

**Rationale:** Matches monolith structure; user’s preferred names become subpackages without inventing a second app root.

**Alternatives considered:**
- Top-level `data_providers/` at repo root — duplicates architecture.

---

## 12. Polars

**Decision:** Not required for v1; stay on pandas/SQLAlchemy bulk paths already dominant.

**Rationale:** Zero Polars dependency today; performance targets achievable with batch SQL + bounded async. Revisit only if profiling shows transform bottlenecks.

---

## 13. Index symbol mapping

**Decision:** Store canonical `NIFTY500`. Configure provider ticker in settings (expected pattern `NSE:NIFTY500-INDEX` consistent with other index symbols in codebase). Validate with live FYERS during implement.

**Rationale:** Aligns with `sector_rs_service` index naming; avoids hardcoding wrong instrument.

---

## 14. Feature flag for gate

**Decision:** Optional `STRATEGY_MARKET_DATA_GATE_ENABLED` (or equivalent) so deploy order can be: migrate → full-load → enable fail-closed gate.

**Rationale:** Prevents total scanner outage on empty strategy tables day one.

---

## 15. load_log vs existing backfill_progress

**Decision:** New `data_load_log` table; do not overload taxonomy `backfill_progress`.

**Rationale:** Different domain, different columns, different operators.
