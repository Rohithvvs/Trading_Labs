# Contract: RE-002 Lab Read / Integration API (Logical)

**Feature**: `031-re002-rs-momentum`  
**Status**: Planning contract (not implementation)  
**Alignment**: Spec FR-013–FR-017, FR-022, FR-027–FR-028, FR-033–FR-034

---

## Purpose

Define **logical** interfaces operators and internal clients use to register, evaluate results, compare engines, and prefill paper trades for RE-002. This is not an OpenAPI implementation and does not prescribe routes as code.

---

## Auth and permissions

| Surface | Auth | Permission |
| ------- | ---- | ---------- |
| Lab reads (detail, compare, history) | Required | Feature key `recommendation_lab` for Admin + Trader |
| Stage/flag configuration | Required | Admin-appropriate |
| Paper prefill from RE-002 | Required | Existing paper + lab visibility rules |
| Unauthenticated | Forbidden | — |

---

## Logical capabilities

### C1 — Engine registration read

**Input**: none (or engine_id filter)  
**Output**: `{ engine_id: "RE-002", name, engine_version, stage, enabled }`  
**Rules**: Reflect settings; stage ∈ {OFF, LAB_SHADOW, PAPER_LINKED}.

### C2 — Active experiment resolve

**Input**: engine_id=RE-002  
**Output**: long-lived experiment summary `{ experiment_id, status, engine_id, version, started_at }` or null if none active  
**Rules**: At most one active long-lived RE-002 experiment for attribution.

### C3 — Decisions for scan

**Input**: `scan_run_id`, optional `engine_id=RE-002`  
**Output**: list of Decision Object summaries (state, confidence, strategy, reason_codes, production_action, mismatch, rs summary)  
**Rules**: One entry per evaluation-set symbol when run healthy (SC-011); includes REJECT rows.

### C4 — Decision for symbol

**Input**: `symbol`, `scan_run_id` or latest, `engine_id=RE-002`  
**Output**: full Decision Object + strategy trace + evidence  
**Rules**: 404/empty when none; never invent.

### C5 — Multi-engine comparison for scan

**Input**: `scan_run_id`  
**Output**: rows per symbol with production state + RE-002 state (+ RE-001 if present)  
**Rules**: Production fields remain Baseline-sourced; lab engines namespaced by EngineID.

### C6 — History query

**Input**: filters `{ engine_id=RE-002, experiment_id?, symbol?, state?, from, to, limit }`  
**Output**: paged Decision Object summaries  
**Rules**: Deterministic ordering by created_at desc default.

### C7 — Health / metrics (MVP)

**Input**: window, engine_id=RE-002, optional experiment_id  
**Output**: `{ counts_by_state, run_success, run_failure, optional mismatch_rate, avg_rs_of_buys? }`  
**Rules**: SC-012; full Doc 04 leadership suite not required.

### C8 — Paper prefill intent

**Input**: `recommendation_id` (RE-002)  
**Output**: prefill payload `{ symbol, trade_guidance or production_plan_fallback, provenance: { engine_id, version, recommendation_id, experiment_id } }`  
**Rules**: Operator confirms create; **no auto-order** endpoint side effect that places orders without operator action.

---

## Orchestrator integration (internal contract)

**When**: After Baseline production recommendation is resolved for a shortlist/full-analysis symbol.  
**If**: `re002_enabled` and stage ∈ {LAB_SHADOW, PAPER_LINKED} and long-lived experiment allows side effects.  
**Then**: Build context → isolated evaluate → persist Decision Object with experiment_id → optional attach to response `lab_engines["RE-002"]`.  
**On error/timeout**: Log + metrics; production path continues; prefer REJECT object when partial evaluation possible, else count error without failing production.

---

## Response compatibility

- Production shortlist and BUY/WATCH arrays remain Baseline-driven.
- Lab payloads are optional additive fields or dedicated lab read capabilities.
- Clients that ignore unknown fields continue to work.
- RE-001 payloads remain independent under `engine_id=RE-001`.

---

## Non-goals

- Public third-party API productization.
- Auto paper order placement API.
- Promotion-to-production API.
- Exact URL paths, HTTP status tables, or OpenAPI schemas (tasks/implementation).
