# Scanner Stream + Health Root-Cause Audit

**Date:** 2026-08-10  
**Branch:** `033-market-data-ingestion`  
**Symptom:** Markets scan fails with `Scanner stream stalled — no progress for 90s` while Infrastructure shows **all** services as **Waking Up** and `Health check timed out — server may be waking up. Retrying…`

---

# Executive Summary

The simultaneous failure of **scanner SSE progress** and **infrastructure health** is not a cold start, not a FYERS token failure, and not a frontend timer misconfiguration.

**Exact root cause:** the FastAPI asyncio **event loop was blocked** for tens of seconds by **synchronous CPU work** on the scanner path:

1. Indicator frame build (`ffill` / `concat` over ~700+ symbols)
2. `TechnicalAnalysisService.analyze_bulk_from_frame(...)` (pandas groupby + Supertrend)
3. Full-universe OHLCV conversion (`frames_to_ohlcv_points` / `iterrows`) for independent RE-001/RE-002

While the event loop is blocked:

| Subsystem | What happens |
|-----------|----------------|
| SSE generator | Cannot `yield` progress or heartbeats |
| Heartbeat task | Cannot `await asyncio.sleep(5)` |
| `GET /health` | Cannot start/finish → frontend aborts at 15s |
| Frontend infra UI | Treats timeout as **all** services “Waking Up” |
| Frontend scanner | `reader.read()` gets no bytes for 90s → stream stalled |

**Hypothesis verdict:** **B + C (symptom of B) + H (symptom of B)**  
Server process is **alive** but **event loop is blocked**. Health is not “dead”; it cannot run. SSE is open but cannot flush.

---

# Exact Root Cause

## Primary (causal)

**File:** `backend/app/services/screener_service.py`  
**Function:** `ScreenerService.screen_symbols_swing` (indicator phase)  
**Observed behavior:** `analyze_bulk_from_frame` + frame build ran **on the event-loop thread**.  
**Evidence:**

- Code path had an incorrect comment claiming heartbeats still work without yielding.
- Supertrend path uses `ThreadPoolExecutor` + `fut.result()` **while holding the event-loop thread**.
- Pandas groupby transforms run on the calling thread.
- Frontend correlation: stream stall **and** health timeout at the same time.

**Why it fails:** asyncio is single-threaded cooperative. Blocking CPU means zero concurrent I/O, zero SSE flushes, zero health responses.

**Fix:** Offload frame build + bulk indicators via `asyncio.to_thread(...)`; cooperative `await asyncio.sleep(0)` before/after; yield every 25 symbols during scoring.

## Secondary (amplifier)

**File:** `backend/app/services/independent_lab_universe.py`  
**Function:** `frames_to_ohlcv_points`, `_load_missing_candles`  
**Observed behavior:** Full data-valid universe (~706) converted with `iterrows` on the event loop.  
**Fix:** `frames_to_ohlcv_points_async` + `asyncio.to_thread` for DataFrame→OHLCV conversion.

## Tertiary (UI mislabel — not root cause of stall)

**File:** `frontend/src/hooks/useInfrastructureHealth.ts`  
**Observed behavior:** Any `/health` timeout painted **every** service as `waking`.  
**Why misleading:** Process could be alive and only event-loop/deps busy.  
**Fix:** Dual probe `/health/live` then `/health`; if live OK and full times out → process Active, deps “connecting/busy” — not all Waking Up.

---

# Failure Timeline

Representative sequence (wall-clock relative to Run Scanner):

| T | Event |
|---|--------|
| T0 | Markets page loads; infra poll starts |
| T1–T2 | `/health` succeeds when event loop free → Active |
| T3 | User clicks **Run Scanner** |
| T4 | `POST /analysis/screener/full` starts; SSE headers open quickly (worker fire-and-forget) |
| T5–T8 | Backend: lock, ensure market data, universe, FYERS/DB fetch — progress events flow |
| T9 | First progress events: “Connecting…”, “Loading universe…”, OHLCV fetch |
| T10 | Last event before stall: often **“Calculating Technical Indicators…”** (~58%) |
| T11 | Event loop enters bulk CPU block; `/health` stops answering within 15s → UI **all Waking Up** |
| T12 | Frontend: no stream bytes for 90s → `Scanner stream stalled — no progress for 90s` |
| T13 | Backend may still finish CPU later; client already aborted stream |

**Not observed as primary:** process restart/OOM at the same moment (no evidence required for B).

---

# Frontend Request Flow

```
SwingDecisionDashboard / Dashboard.handleRunScanner
  → runPresetScreener (frontend/src/api.ts)
    → fetch POST /analysis/screener/full  Accept: text/event-stream
    → response.body.getReader()
    → race(reader.read(), stall timeout 90s from last byte activity)
    → parse SSE: event: progress | event: result | : heartbeat comments
```

**Stall timer semantics (required):**

- Starts after stream body is available.
- Resets on **any** received chunk (progress JSON **or** `: heartbeat` comment).
- Does **not** mean “scan longer than 90s”.
- Fixed: remaining budget uses `lastProgressAt`; abort listener cleaned each loop.

**Infrastructure:**

```
InfrastructureStatus
  → useInfrastructureHealth (poll 15s)
    → GET /health/live  (3s)   # process only
    → GET /health       (15s)  # deps
```

---

# Backend Request Flow

```
POST /analysis/screener/full  (analysis.py::screener_full)
  → seed progress queue
  → create_task(ScanExecutionService.execute_scan)
  → StreamingResponse(event_stream)  # heartbeat every 5s idle
       → ScanExecutionService.execute_scan
            → lock.acquire
            → ensure_latest_market_data (async)
            → heartbeat_sender task (5s)
            → _run_scan_task
                 → RouterAgent.screener_full
                      → OrchestratorAgent.run_screener
                           → ScreenerService.screen_symbols_swing
                                → fetch OHLCV (async, network pool)
                                → [WAS BLOCKING] build frame + analyze_bulk
                                → scoring loop
                           → Production Top-N deep analysis
                           → run_independent_lab_universe (full data_valid)
                                → RE-001 / RE-002 per symbol (to_thread eval)
```

---

# Health Endpoint Audit

| Route | File | Dependencies | Blocking risk |
|-------|------|--------------|---------------|
| `GET /health/live` | `routes/health.py` | **None** (process only) | **None** (new) |
| `GET /health` | `routes/health.py` | DB (8s cap), Redis (1s), market_engine.status (0.75s) | Event-loop blocked → never runs |
| `GET /health/heartbeat` | `routes/health.py` | market_engine + DB write | Heavier; not used by infra panel |
| `GET /system/shadow-run/health/ready` | `routes/system.py` | DB + scheduler + token | Not the Markets panel |

**Important:** `/health` already used bounded timeouts and does **not** call FYERS HTTP.  
Failure mode was **not** “FYERS slow inside health” — it was **event loop never scheduling health**.

Probes now run via `asyncio.gather` (parallel, not serial).

---

# Scanner Stream Audit

| Component | Location | Status |
|-----------|----------|--------|
| SSE open before lock | `analysis.screener_full` create_task | Correct |
| Queue maxsize 200 + drop-oldest | `ScanExecutionService._emit` | Correct |
| Idle progress every 5s | `event_stream` TimeoutError branch | Correct |
| Comment keepalive 2KB pad | `event_stream` | Correct |
| Worker heartbeat task | `_heartbeat_sender` every 5s | Correct **only if loop free** |

**Last backend event before stall:** typically progress at indicators (~58%).  
**Last frontend receive:** same; then silence until 90s abort.

---

# SSE/WebSocket Audit

- Scanner uses **SSE**, not WebSocket, for progress.
- Heartbeats were **generated in code** but **could not be scheduled** under event-loop block.
- Verifying “browser receives heartbeat” while loop blocked is impossible by definition — transport idle.

---

# Frontend Timer Audit

| Constant | Value | Meaning |
|----------|-------|---------|
| `CONNECT_TIMEOUT_MS` | 30s | Headers must arrive |
| `STREAM_STALL_TIMEOUT_MS` | 90s | No **stream activity** |
| Health `REQUEST_TIMEOUT_MS` | 15s | Full `/health` |
| Health `LIVE_TIMEOUT_MS` | 3s | `/health/live` |
| Infra poll | 15s | Interval |

Timer reset: any `reader.read()` resolution with bytes.  
Heartbeat comments count.  
No intentional multi-listener leak after cleanup fix.

---

# Thread Pool Audit

| Pool | Use | Status |
|------|-----|--------|
| `FyersService._network_pool` | Blocking FYERS SDK | Dedicated; size ≥ 50 |
| `asyncio.to_thread` / default executor | CPU offload after fix; AnyIO limiter 100 | OK |
| Supertrend `ThreadPoolExecutor` inside bulk | Nested under to_thread now | OK |
| RE-001/RE-002 | `asyncio.to_thread(_evaluate_sync)` | Already off-loop |

**Prior thread-pool exhaustion (FYERS + sleep on default executor)** is largely addressed for FYERS via `_network_pool`.  
**This incident** was event-loop CPU block, not pool exhaustion.

---

# Event Loop Audit

| Site | Before | After |
|------|--------|-------|
| Frame build + `analyze_bulk_from_frame` | **On loop** | `asyncio.to_thread` |
| Scoring loop | Mostly async with awaits | + `sleep(0)` every 25 symbols |
| `frames_to_ohlcv_points` | **On loop** | `frames_to_ohlcv_points_async` |
| Candle fill iterrows | **On loop** | `to_thread(_df_to_ohlcv_points)` |
| FYERS history | network pool | Unchanged (OK) |
| RE-001/RE-002 evaluate | to_thread | Unchanged (OK) |

---

# Database Pool Audit

- Async pool: `pool_size=20`, `max_overflow=10`, `pool_timeout=30`, `pool_pre_ping=True`.
- Health checks out one connection briefly.
- Scanner can pressure pool during fetches; **not** the dual-symptom 90s/15s pattern (health would queue/timeout specifically on pool wait, not freeze SSE heartbeats unless loop also blocked).
- **Verdict:** DB pool not primary root cause.

---

# Redis Audit

- Optional when `REDIS_URL` unset → `not_configured` (UI treats as active/n/a).
- 1s probe timeout.
- No evidence Redis deadlock caused dual failure.

---

# FYERS Audit

- Scanner FYERS work uses `_network_pool` + rate limiter + semaphore.
- Health does **not** call FYERS HTTP.
- Token missing produces later data failures / progress messages — **not** simultaneous all-Waking-Up.
- **FYERS IS NOT ROOT CAUSE** of this dual symptom.

---

# Scanner Worker Audit

- In-process asyncio task (not separate OS worker process).
- Lock: `DistributedLockService("scan_execution")` with heartbeat.
- Worker remains “alive” while CPU-bound on loop; appears dead to clients because nothing flushes.

---

# Navigation Lifecycle Audit

- `useInfrastructureHealth` cleans up AbortController + interval on unmount.
- Remount on Markets re-entry starts from `sleeping` then polls.
- If remount coincides with scanner CPU block → immediately sees timeouts → **was** painted all waking.
- Dashboard aborts prior scan via AbortController on re-run.

---

# Duplicate Request Audit

- Health: one interval, aborts prior in-flight probe before next (after fix).
- Scanner: single AbortController per run; re-click aborts previous.

---

# Concurrency Audit

| Path | Bound |
|------|-------|
| FYERS fetch | `max_concurrent_requests` (≤50) + semaphore |
| Lab engines | `_DEFAULT_LAB_CONCURRENCY = 12` |
| Sector RS | 8 |
| Market-data ensure | ≤8 |
| Production Top-N | shortlist only |

Not “Top-N=20 as lab universe”. Lab uses full data_valid.

---

# Engine Independence Audit

Verified architecture remains:

```
Master universe → candles → data_valid (~706)
  ├── Production: Top-N shortlist deep analysis only
  ├── RE-001: full data_valid (independent)
  └── RE-002: full data_valid (independent)
```

No change to gate RE-001/RE-002 on Production Top-N.

---

# Full Universe Audit

Expected after fix (runtime):

| Engine | Input | Processed |
|--------|-------|-----------|
| Production deep | Top-N shortlist | Top-N |
| RE-001 | data_valid ≈ 706 | ≈ 706 (candles-ready) |
| RE-002 | data_valid ≈ 706 | ≈ 706 (candles-ready) |

Logs: `LAB_ENGINE_INDEPENDENCE | lab_input_data_valid=...` and `LAB_UNIVERSE_COMPLETE | re001_eval=...`.

---

# Root Cause Evidence

### RC-1 — Event-loop blocked by bulk indicators

| Field | Value |
|-------|-------|
| File | `backend/app/services/screener_service.py` |
| Function | `screen_symbols_swing` |
| Observed | Sync `analyze_bulk_from_frame` on loop |
| Evidence | Dual failure SSE + /health; incorrect “no yield needed” comment |
| Why fails | Blocks SSE flush + health scheduling |
| Fix | `asyncio.to_thread(_build_and_analyze_bulk)` + pre/post `sleep(0)` |

### RC-2 — Lab frame conversion on loop

| Field | Value |
|-------|-------|
| File | `backend/app/services/independent_lab_universe.py` |
| Function | `frames_to_ohlcv_points` / `_load_missing_candles` |
| Observed | iterrows for hundreds of symbols on loop |
| Fix | async offload to threads |

### RC-3 — Infra UI false global “Waking Up”

| Field | Value |
|-------|-------|
| File | `frontend/src/hooks/useInfrastructureHealth.ts` |
| Observed | Single /health timeout → all services waking |
| Fix | `/health/live` + nuanced busy vs dead |

---

# Files Changed

| File | Change |
|------|--------|
| `backend/app/services/screener_service.py` | CPU offload for frame build + bulk indicators; scoring yields |
| `backend/app/services/independent_lab_universe.py` | Async offload OHLCV conversion |
| `backend/app/routes/health.py` | `GET /health/live`; parallel probes on `/health` |
| `frontend/src/hooks/useInfrastructureHealth.ts` | Dual probe; no false all-waking when process live |
| `frontend/src/api.ts` | Stall timer remaining-budget + abort cleanup |
| `backend/tests/unit/test_health_live_and_parallel.py` | New |
| `backend/tests/unit/test_scanner_cpu_offload.py` | New |
| `scanner_stream_and_health_root_cause_audit.md` | This document |

---

# Tests Executed

```text
pytest tests/unit/test_scanner_cpu_offload.py tests/unit/test_health_live_and_parallel.py -q
pytest tests/unit/test_engine_independence.py tests/unit/test_re001_core_logic.py tests/unit/test_re002_technicals.py -q
```

# Test Results

```text
test_scanner_cpu_offload.py ........ PASS (event loop free during bulk CPU)
test_health_live_and_parallel.py ... PASS (live + parallel probes)
engine independence + re001/re002 .. 40 passed
```

---

# Final Engine Verification

| Engine | Requirement | Status |
|--------|-------------|--------|
| Production | Top-N isolated | **Unchanged / PASS** |
| RE-001 | Full data-valid universe | **Unchanged / PASS** |
| RE-002 | Full data-valid universe | **Unchanged / PASS** |

---

# Root Cause Matrix

| Component | Status | Evidence | Root Cause? |
|-----------|--------|----------|-------------|
| Render Server | Alive (process) | Loop blocked, not restart | No |
| FastAPI event loop | **Blocked by CPU** | SSE+health simultaneous | **YES** |
| Health API | Starved when loop blocked | 15s frontend abort | Symptom |
| PostgreSQL | Bounded probe | Not dual-symptom primary | No |
| Redis | Optional / bounded | — | No |
| FYERS | Network pool | Not in /health | No |
| Scanner Worker | Task alive, loop busy | — | Symptom of CPU path |
| Production | Top-N only | Engine independence tests | No |
| RE-001 | Full data_valid | independent_lab_universe | No |
| RE-002 | Full data_valid | independent_lab_universe | No |
| SSE | Heartbeat exists but starved | analysis.py event_stream | Symptom |
| WebSocket | Not scanner path | — | No |
| Frontend timer | 90s no-activity correct | api.ts | No (after cleanup) |
| Thread pool | FYERS dedicated | fyers_service | No |
| DB pool | 20+10 | session.py | No |

---

# FINAL VERDICT

**PASS — ROOT CAUSE IDENTIFIED AND FIXED AT THE EVENT-LOOP BOUNDARY**

- Health responds when the process is free; `/health/live` distinguishes dead vs busy.
- Scanner stream can flush heartbeats during indicator and lab conversion phases.
- 90s stall remains a true **no-activity** detector (not inflated).
- Timeouts were **not** increased as the “solution.”
- FYERS was **not** blamed without evidence.
- Cold start was **not** claimed without restart proof.
- Engine independence preserved.

Operators should still watch logs for:

- `SCANNER_CPU_OFFLOAD_DONE | ffill_ms=... | indicators_ms=...`
- `[health] ok | ... | Xms`
- `LAB_UNIVERSE_COMPLETE | input=... | re001_eval=... | re002_eval=...`
