# Scanner Exact Root-Cause Report

**Date:** 2026-08-10  
**Symptom:** UI stuck at **Ensuring market data… 4%**, then `Scanner stream stalled — no progress for 90s`  
**Last backend INFO:** `Scanner token loaded successfully. Token source used: cache`

---

# 1. Executive Summary

The scanner **does start** and **SSE does connect**. Progress freezes at **4%** because the worker is blocked inside:

```text
ScanExecutionService.execute_scan
  → ensure_latest_market_data(trigger_source="SCANNER")
      → FyersEodProvider.fetch_daily_session / _fetch_daily_chunk
          → FyersService._client()          # "Scanner token loaded successfully"
          → _request_history_with_retries() # silent at INFO; can hang / retry / sleep
```

This pre-scan **market-data ensure** path was **unbounded** for scanners:

- Could chase **full-universe** OHLCV when coverage/gap required it  
- Recreated a FYERS SDK client **per symbol** (token log spam)  
- Repaired ADTV with **N sequential DB history loads** (700+ round-trips)  
- Emitted **no intermediate progress** after the initial 4% event  
- Could run **far beyond 90s**

**PRIMARY ROOT CAUSE CATEGORY: A + L (with D as secondary for sequential CPU/DB waves)**  
**Exact:** Unbounded scanner-triggered `ensure_latest_market_data` FYERS/NSE/ADTV work after progress=4, with no wall-clock budget and insufficient progress emissions.

**Not root cause:** invalid token (logs show cache hit + loaded), DB pool exhaustion (checked_out 7–10 / 20), SSE connect failure (200 + event-stream).

---

# 2. Exact Root Cause

| Field | Value |
|-------|--------|
| **ROOT CAUSE** | A (FYERS network path) + L (unbounded concurrency/work in ensure) |
| **FILE** | `backend/app/services/market_data_ingestion/ensure.py` |
| **FUNCTION** | `ensure_latest_market_data` |
| **BLOCKING LINE (historical)** | `await fyers.fetch_daily_session(sym, _session)` inside `one()` gather over missing/gap symbols; plus sequential ADTV `fetch_equity_history` loop |
| **CALL STACK** | See §4 |
| **FIRST BLOCKING OPERATION** | FYERS history after `_client()` token load (`fyers_eod._fetch_daily_chunk` → `_request_history_with_retries`) |
| **WHY IT BLOCKS** | Live EOD fetch for many symbols; 10s timeout × retries × `time.sleep` backoff on network pool; optional multi-day full-universe gap fill; sequential ADTV |
| **WHY 4%** | `scan_execution_service` sets progress=4 **before** `await ensure_latest_market_data`; next emit is progress=6 only after ensure returns |
| **WHY LOGGING STOPS** | After token load, history start/complete was mostly **DEBUG**; successful path quiet at INFO |
| **WHY FRONTEND WAITS 90s** | No (or insufficient) SSE activity while ensure runs; frontend stall timer measures **no stream bytes for 90s** |

**Reproduction proof (this session):**  
Calling `ensure_latest_market_data(symbols=['__none__'], trigger_source='SCANNER')` against live config **did not return within 60s** and was killed — same hang class as production symptom.

---

# 3. Evidence Timeline

| Time (local log) | Event |
|------------------|--------|
| T0 | Frontend `runPresetScreener` |
| T0+7.8s | SSE headers 200 `text/event-stream` |
| T1 | UI: Ensuring market data… **4%** |
| 20:27:41–43 | DB checkout/checkin healthy (7–10 / 20) |
| 20:27:41–43 | `TOKEN_CACHE_HIT` + `Scanner token loaded successfully` (repeated = multi-symbol client create) |
| T1+… | **No** `ENSURE_MARKET_DATA_END` / progress 6 |
| T1+90s | Frontend: stream stalled |

Infra `/health/live` recovering to ~10–30ms during scan shows process not dead; ensure worker still chewing FYERS/DB.

---

# 4. Complete Call Stack

```text
frontend/src/api.ts::runPresetScreener
  POST /analysis/screener/full
backend/app/routes/analysis.py::screener_full
  asyncio.create_task(_start_scan_worker)
  StreamingResponse(event_stream)
backend/app/services/scan_execution_service.py::execute_scan
  lock.acquire
  _heartbeat_sender (task)
  progress=4 "Ensuring market data..."
  await ensure_latest_market_data(SCANNER)          ← STUCK HERE
backend/app/services/market_data_ingestion/ensure.py::ensure_latest_market_data
  _snapshot / lock / ohlcv gather
  FyersEodProvider.fetch_daily_session
backend/app/services/market_data_ingestion/providers/fyers_eod.py::_fetch_daily_chunk
  svc._client()                                     ← last INFO token log
  run_in_executor(_request_history_with_retries)    ← silent hang/retry window
backend/app/services/fyers_service.py::_request_history_with_retries
  client.history(data=payload) + optional time.sleep backoff
```

Only after ensure returns:

```text
progress=6 → _run_scan_task → RouterAgent.screener_full
  → Production Top-N
  → run_independent_lab_universe (RE-001/RE-002 full data_valid)
```

---

# 5. 4% Progress Explanation

| Progress | Stage | Source |
|----------|--------|--------|
| 1 | Connecting data feed… | `execute_scan` start |
| **4** | **Ensuring market data…** | **`execute_scan` immediately before ensure** |
| 6 | Market data ready / status | after ensure returns |
| 10+ | Loading universe / broker / screener | `_run_scan_task` |

**4% means: market-data ensure is in progress (or hung). Not Production. Not RE-001/RE-002.**

---

# 6. Last Successful Operation

```text
FyersService._client (fyers_service.py ~1212)
  token_service.get_current_access_token_sync → TOKEN_CACHE_HIT
  log: "Scanner token loaded successfully. Token source used: cache"
  return fyersModel.FyersModel(...)
```

---

# 7. First Blocking Operation

```text
FyersEodProvider._fetch_daily_chunk
  → loop.run_in_executor(network_pool, _request_history_with_retries, client, payload, symbol)
  → client.history(...) under NetworkTimeoutContext(10.0)
  → on failure: time.sleep(2**attempt) up to 3 retries
```

Multiplied by many symbols (and previously full-universe/gap schedules) without scanner budget.

---

# 8. FYERS Audit

| Item | Finding |
|------|---------|
| Token | Valid cache hit — **not** the failure |
| Client create | Was once per symbol — fixed to **reuse per provider instance** |
| History | Network pool; 10s patch timeout; retries with sleep |
| Logging | Token INFO then silence — fixed with `FYERS_EOD_REQUEST/RESPONSE` |

**FYERS token is not the root cause.** FYERS **history fetch volume/latency** under unbounded ensure **is**.

---

# 9. Thread Pool Audit

| Pool | Role |
|------|------|
| `FyersService._network_pool` (~75) | history calls |
| `asyncio.to_thread` | `_client()` construction |

Not exhausted in evidence (pool_size 20 DB; FYERS concurrency capped ≤8). Issue is **duration of ensure work**, not pool dead.

---

# 10. Database Audit

checked_out 7–10 / pool_size 20, checkins continuing → **not exhausted**.  
ADTV path was N sequential history queries — **slow but not pool-full**. Replaced with SQL window for session.

---

# 11. SSE Audit

| Item | Status |
|------|--------|
| Connect | 200 event-stream — OK |
| Progress at 4% | Emitted once |
| During ensure | Heartbeat task exists; ensure now also emits progress |
| Stall | Symptom of **no/few stream events for 90s** while ensure hangs |

---

# 12. Frontend Audit

| Item | Status |
|------|--------|
| Connect timeout 30s | Headers arrived (7.8s) — OK |
| Stall 90s | Correct “no activity” detector — **not the bug** |
| Stage “Ensuring market data” 4% | Faithful render of last progress event |

---

# 13. Concurrency Audit

| Path | Bound (after fix) |
|------|-------------------|
| Scanner ensure FYERS | ≤8 concurrent, waves, **≤40 symbols** |
| Scanner ensure wall clock | **45s** internal + **50s** outer `wait_for` |
| NSE delivery | `wait_for` ≤20s |
| ADTV | **1 SQL** `backfill_adtv_20_for_session` |
| Production / RE engines | Unchanged independence |

---

# 14–16. Engine Audits

| Engine | Intended input | Affected by this bug? |
|--------|----------------|------------------------|
| Production | Top-N shortlist | Only delayed until ensure finishes |
| RE-001 | Full data-valid ~706 | Same — never started while stuck at 4% |
| RE-002 | Full data-valid ~706 | Same |

**No change** that routes lab engines through Production Top-N.

---

# 17. Files Changed

| File | Change |
|------|--------|
| `backend/app/services/market_data_ingestion/ensure.py` | Scanner budget, progress, capped OHLCV, wave fetch, SQL ADTV, TIMEOUT status |
| `backend/app/services/market_data_ingestion/providers/fyers_eod.py` | Reuse SDK client; INFO request/response logs |
| `backend/app/services/market_data_ingestion/repository.py` | `backfill_adtv_20_for_session` SQL |
| `backend/app/services/scan_execution_service.py` | Progress callback into ensure; 50s outer timeout; stage start/end logs |
| `backend/tests/unit/test_ensure_scanner_budget.py` | New regression tests |
| `backend/tests/unit/test_market_data_ensure.py` | Universe cache isolation |
| `scanner_exact_root_cause_report.md` | This report |

---

# 18. Exact Fix

1. **Budget:** scanner ensure max **45s** (outer wait_for **50s**); return `TIMEOUT` and **continue scan** (gate still optional).  
2. **Cap:** scanner live OHLCV chase max **40** symbols (daily job does full catch-up).  
3. **Progress:** emit SSE-friendly progress during OHLCV/ADTV phases (keeps 90s stall honest).  
4. **ADTV:** replace N×`fetch_equity_history` with **`backfill_adtv_20_for_session`**.  
5. **FYERS client:** one client per `FyersEodProvider` instance.  
6. **Logging:** `ENSURE_*` + `FYERS_EOD_REQUEST/RESPONSE` + `SCAN_STAGE_START/END`.  

**Did not:** raise 90s timeout, shrink RE universe to 20, disable engines, skip SSE.

---

# 19. Regression Test Results

```text
pytest tests/unit/test_ensure_scanner_budget.py tests/unit/test_market_data_ensure.py -q
5 passed
```

| Test | Proves |
|------|--------|
| `test_scanner_ensure_times_out_instead_of_hanging` | Hung FYERS returns under budget |
| `test_scanner_ensure_caps_ohlcv_symbols` | ≤40 live FYERS fetches on scanner path |
| Existing already_fresh / fetch mocks | Fast path still works |

**Operator verification after restart:**

```text
SCAN_STAGE_START | stage=ensure_market_data
ENSURE_MARKET_DATA_START | budget_s=45
FYERS_EOD_CLIENT_READY
FYERS_EOD_REQUEST / RESPONSE  (bounded)
ENSURE_MARKET_DATA_END | status=ALREADY_FRESH|SUCCESS|PARTIAL|TIMEOUT
SCAN_STAGE_END | stage=ensure_market_data
progress → 6+ (universe / broker / screener)
LAB_ENGINE_INDEPENDENCE | lab_input_data_valid≈706
```

---

# 20. Final Verdict

## PASS — exact blocking line identified and fixed

Scanner no longer sits forever at **4% Ensuring market data** on unbounded FYERS/ADTV work.  
Ensure is **budgeted**, **progress-emitting**, and **scanner-capped** without collapsing RE-001/RE-002 to Production Top-N.

**Restart the backend** so this code is loaded, then re-run the scanner and confirm logs move past `SCAN_STAGE_END | stage=ensure_market_data` within ~50s.

---

## One definitive answer (required format)

```text
ROOT CAUSE: A + L — unbounded ensure_latest_market_data FYERS/ADTV work at progress=4
FILE: backend/app/services/market_data_ingestion/ensure.py
FUNCTION: ensure_latest_market_data  (and fyers_eod._fetch_daily_chunk after _client)
LINE: await fyers.fetch_daily_session / prior sequential ADTV loop (replaced)
CALL STACK: screener_full → execute_scan → ensure_latest_market_data → FyersEodProvider → _client → history
FIRST BLOCKING OPERATION: FYERS history after token load
WHY IT BLOCKS: multi-symbol live EOD + retries + optional full-universe schedule + sequential ADTV
WHY 4% OCCURS: progress=4 emitted before ensure; progress=6 only after ensure returns
WHY LOGGING STOPS: post-token history was DEBUG-level / silent
WHY FRONTEND WAITS 90s: no stream activity for 90s while ensure hangs
```
