# Research: RE-002 Relative Strength Momentum Engine Integration

**Feature**: `031-re002-rs-momentum`  
**Date**: 2026-08-04  
**Purpose**: Resolve technical unknowns for planning. No implementation code.

**Sources**: RE-002 Docs 01–04, REDS v1.0, feature spec + clarify session 2026-08-04, existing multi-engine Lab (RE-001 package + `recommendation_engine_decisions`), ExperimentService.

---

## R1 — Multi-engine persistence

**Decision**: Reuse existing first-class multi-engine decisions store (`recommendation_engine_decisions` / `RecommendationEngineDecision`) with `engine_id = "RE-002"`.

**Rationale**: Table is already EngineID-namespaced with uniqueness on `recommendation_id` and indexes on engine/symbol/scan/state. Avoids a second SoR and enables Lab multi-engine comparison without schema redesign.

**Alternatives considered**:
- Separate `re002_decisions` table — rejected (duplication, harder multi-engine compare).
- Namespaced JSON only on `analysis_history` — rejected by REDS/lab SoR requirements (same as RE-001).

---

## R2 — Isolation and orchestrator placement

**Decision**: Mirror RE-001 pattern: after Baseline production recommendation resolves per shortlist symbol, invoke `run_re002_isolated_*` inside try/except + timeout; fail-open for production.

**Rationale**: Proven production-safe envelope already in orchestrator; operators understand behavior; reduces novel risk.

**Alternatives considered**:
- Separate async batch after full scan — deferred (acceptable later; MVP piggybacks scan path per FR-017).
- In-process without timeout — rejected (latency/DoS risk to scan).

---

## R3 — Experiment binding

**Decision**: One long-lived Experiment record for RE-002 (via ExperimentService); stamp `experiment_id` on Decision Objects / paper provenance / metrics while active; pause or stage OFF stops new side effects.

**Rationale**: Spec clarify A; matches governance list/show/metric/report usage; avoids experiment sprawl per scan.

**Alternatives considered**:
- Per-day auto experiments — rejected (noise, harder history).
- Stage-only without experiment entity — rejected (FR-028 / SC-010 require experiment identity).

---

## R4 — Relative strength inputs

**Decision**: Consume existing sector RS / relative strength services and TA-derived features; do not invent a second market-data pipeline. Unfrozen lookbacks/formulas use **conservative, versioned defaults** documented under engine_version.

**Rationale**: Docs 01–04 explicitly leave exact formulas out of business docs; REDS forbids private SCS reimplementation; FEAT sector RS already productionized.

**Alternatives considered**:
- New proprietary RS stack — rejected (architecture violation, dual truth).
- Block MVP until Doc 03 math freeze — rejected (Doc 03 also defers exact formulas; conservative defaults unblocks Lab integration).

---

## R5 — Weak RS / eligibility emission

**Decision**: For every shortlisted evaluation-set symbol, always persist a Decision Object; eligibility/RS failures → `REJECT` + explicit reason codes (`weak_relative_strength`, `failed_bull_stock_filter`, `insufficient_history`, etc.).

**Rationale**: Spec clarify A; SC-011; Lab comparison completeness.

**Alternatives considered**:
- Silent skip — rejected (comparison holes, audit gaps).
- Debug-flag-only objects — rejected (non-deterministic ops).

---

## R6 — Paper trading model

**Decision**: Same user paper account; mandatory provenance (`source_engine_id=RE-002`, version, recommendation_id, experiment_id); **operator-initiated prefill only**; no auto-orders under `PAPER_LINKED`.

**Rationale**: Spec clarify A/B; matches advisory-only and existing paper desk; Doc 04 “all recs paper-traded” is process/promotion gate, not auto-execution.

**Alternatives considered**:
- Separate RE-002 portfolio — deferred (product complexity; not required for filterable attribution).
- Auto paper all BUYs — rejected for MVP (shared-account flood risk).

---

## R7 — UI / Lab surfaces

**Decision**: Extend existing hybrid Lab pattern: symbol detail RE-002 section + multi-engine Lab comparison columns; feature key `recommendation_lab`; Admin + Trader.

**Rationale**: Spec FR-014/FR-022; reuses RE-001 UI investment; clear experimental labeling.

**Alternatives considered**:
- Admin-only — rejected (spec visibility).
- Full multi-engine marketplace console — out of MVP.

---

## R8 — Analytics MVP scope

**Decision**: MVP requires decision counts by state, run success/failure, optional mismatch, RS evidence on decisions, basic avg RS of BUYs when scores exist. Full Doc 04 leadership suite deferred.

**Rationale**: Spec clarify B / SC-012; unblocks integration without research-dashboard product.

**Alternatives considered**:
- Full Doc 04 suite in MVP — rejected (scope risk).
- Counts-only with zero RS aggregates — weaker than needed for leadership identity.

---

## R9 — Settings and stages

**Decision**: Parallel `re002_*` settings to `re001_*`; stages `OFF` | `LAB_SHADOW` | `PAPER_LINKED`; defaults OFF/false for safe deploy.

**Rationale**: Operator familiarity; independent toggle from RE-001; REDS lifecycle alignment.

**Alternatives considered**:
- Shared single lab_stage for all engines — rejected (cannot stage RE-002 independently).

---

## R10 — Coexistence with RE-001

**Decision**: Independent packages (`re002/` parallel to `re001/`); shared decisions table and Lab read models; **do not modify RE-001 strategy rules**.

**Rationale**: Multi-engine roadmap; reduces regression blast radius.

**Alternatives considered**:
- Generic single engine plugin framework rewrite first — deferred (valuable later; not required for RE-002 MVP).
- Fork RE-001 code and retune — rejected (couples philosophies; harder maintenance).

---

## R11 — Missing regime and portfolio

**Decision**: Align with RE-001 operational rules already proven: missing regime → REJECT `missing_market_context`; missing portfolio → no BUY with `portfolio_context_unavailable`.

**Rationale**: Spec FR-025/FR-026; capital preservation; consistent Lab semantics across engines.

**Alternatives considered**:
- Default to Sideways — rejected (spec forbid default regime).

---

## Open items deferred to implementation tasks (not blocking plan)

1. Exact numeric RS lookbacks and ranking weights (versioned config defaults).
2. Whether `experiment_id` already exists on decisions table or needs additive column.
3. Precise timeout_ms default (start from RE-001 order of magnitude, tune in soak).
4. Frontend component file names for Lab multi-engine extension (discover during tasks).

**All Technical Context NEEDS CLARIFICATION items**: none remaining for MVP architecture.
