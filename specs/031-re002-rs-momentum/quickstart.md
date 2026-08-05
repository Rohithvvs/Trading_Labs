# Quickstart Validation Guide: RE-002 Integration

**Feature**: `031-re002-rs-momentum`  
**Date**: 2026-08-04  
**Purpose**: Runnable validation scenarios for implementers after coding. No implementation code here.

**Related**: [spec.md](./spec.md) · [plan.md](./plan.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/)

---

## Prerequisites

1. Application boots with multi-engine decisions store available (RE-001 migration present or equivalent).
2. RE-002 defaults **OFF** (`re002_enabled=false` / `re002_stage=OFF`).
3. Ability to run backend test suite and a shortlist-producing scan (or fixtures).
4. Authenticated Admin and Trader test users; feature key **`recommendation_lab`** configurable.
5. Baseline (and RE-001 if deployed) regression suites green **before** enabling RE-002.
6. Long-lived RE-002 experiment can be registered via Experiment Framework / ops procedure.

## Ops: stages and env (canonical)

| Setting | Values | Notes |
| ------- | ------ | ----- |
| `RE002_ENABLED` / `re002_enabled` | true/false | Master switch |
| `RE002_STAGE` / `re002_stage` | `OFF` \| `LAB_SHADOW` \| `PAPER_LINKED` | `ACTIVE` reserved |
| Feature permission | `recommendation_lab` | Admin + Trader when active |
| Experiment | long-lived RE-002 experiment | Active for attribution |

`LAB_SHADOW` and `PAPER_LINKED` both evaluate+persist when enabled and experiment allows side effects; `PAPER_LINKED` marks intentional paper-validation mode (**not** auto-orders).

---

## Scenario A — Production / Baseline invariance (SC-001, SC-009)

**Setup**
1. Capture production shortlist + BUY/WATCH labels with RE-002 **OFF** (control).
2. Register/activate long-lived RE-002 experiment; enable RE-002 `LAB_SHADOW` with same market snapshot / fixtures.
3. Re-run analysis/scan.

**Expected**
- Production labels and shortlist membership **identical** to control.
- Baseline recommendation fields unchanged (beyond optional non-authoritative lab payload).
- RE-002 Decision Objects exist for shortlisted symbols.
- Scan does not fail solely because RE-002 errored on a symbol.

**Fail if**
- Any production action/score/shortlist membership changes solely due to RE-002 enablement.

---

## Scenario B — One Decision Object per shortlist symbol (SC-011)

**Setup**
1. Produce shortlist of N symbols.
2. Enable RE-002 lab mode with active experiment.
3. Run evaluation.

**Expected**
- Exactly N RE-002 Decision Objects for that scan_run_id (including REJECT for weak RS / eligibility).
- Zero silent omissions.

**Fail if**
- Any shortlist symbol has no RE-002 row when engine active and run completed.

---

## Scenario C — Weak RS pre-filter REJECT (clarify + FR-024)

**Setup**
1. Fixture a shortlisted symbol that fails RS pre-filter / weak RS.
2. Enable RE-002.
3. Evaluate.

**Expected**
- Decision Object with `recommendation_state = REJECT`.
- Reason code includes `weak_relative_strength` (or equivalent).
- No BUY.

---

## Scenario D — Missing market context (FR-025)

**Setup**
1. Force missing/unusable regime for one shortlisted symbol.
2. Enable RE-002.
3. Evaluate.

**Expected**
- REJECT with `missing_market_context`.
- No BUY; no default regime assumed.
- Production path still succeeds.

---

## Scenario E — Shortlist-only evaluation (FR-017)

**Setup**
1. Scan with matched symbols beyond shortlist top-N.
2. Enable RE-002.
3. Inspect decisions.

**Expected**
- Decisions only for shortlist / full-analysis symbols.
- Zero RE-002 decisions for non-shortlisted matched symbols.

---

## Scenario F — Flag OFF / experiment pause zero new artefacts (SC-007)

**Setup**
1. With RE-002 previously enabled, set stage OFF **or** pause long-lived experiment.
2. Run a new scan.

**Expected**
- Zero new RE-002 Decision Objects for the disabled period.
- Historical decisions remain readable.

---

## Scenario G — Long-lived experiment attribution (SC-010, FR-028)

**Setup**
1. Activate one long-lived RE-002 experiment.
2. Run two scans on different days/windows.
3. List experiment / query decisions.

**Expected**
- Both scans’ RE-002 decisions share the same experiment_id while experiment remains active.
- Experiment list/show can identify RE-002 experiment and link history.

**Fail if**
- Per-scan auto experiments are created instead of long-lived binding.

---

## Scenario H — Multi-engine coexistence (FR-033)

**Setup**
1. Enable RE-001 (if present) and RE-002 together.
2. Run scan.

**Expected**
- Separate Decision Objects by engine_id.
- Neither overwrites the other or production labels.
- Lab comparison can show production + RE-002 (+ RE-001).

---

## Scenario I — Operator paper prefill (SC-005, FR-015)

**Setup**
1. Obtain RE-002 BUY decision.
2. Operator initiates paper prefill/create from decision (do not expect auto-order).
3. Inspect ticket provenance.

**Expected**
- Same user paper account.
- Provenance: engine_id=RE-002, recommendation_id, experiment_id when available.
- Trade guidance uses complete RE-002 guidance else production trade_plans.
- No paper orders created without operator action under `PAPER_LINKED`.

---

## Scenario J — Lab UI explainability (SC-002, SC-004)

**Setup**
1. Enable UI + `recommendation_lab` for Trader/Admin.
2. Open symbol detail and Lab comparison for a completed scan.

**Expected**
- RE-002 state, strategy, RS evidence or reject reason visible without DB access.
- Production vs RE-002 reviewable in under 2 minutes.
- Surfaces labeled experimental/lab.

---

## Scenario K — Analytics MVP (SC-012)

**Setup**
1. Accumulate multiple RE-002 decisions including some BUYs with RS scores.
2. Open analytics/experiment health for RE-002.

**Expected**
- Counts by state and run success/failure visible.
- Basic average RS of BUYs when RS present.
- Full Doc 04 leadership suite **not** required to pass.

---

## Scenario L — Regime participation direction (SC-006)

**Setup**
1. Controlled fixtures: bull vs bear regime, equivalent technical quality.
2. Evaluate RE-002.

**Expected**
- Bear BUY count ≤ 50% of bull BUY count on the shared fixture set.

---

## Suggested verification order

1. A (invariance)  
2. B + C + D (emission correctness)  
3. E + F (scope and kill switch)  
4. G + H (experiment + multi-engine)  
5. I + J + K (paper + UI + analytics)  
6. L (philosophy)  
7. Full Baseline / scanner / paper / analytics / RE-001 regression packs  

---

## Rollback drill

1. Set `re002_stage=OFF` and/or `re002_enabled=false`.
2. Pause long-lived experiment.
3. Confirm no new RE-002 rows on next scan.
4. Confirm production path and UI primary workflows unaffected.
