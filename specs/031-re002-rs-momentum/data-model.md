# Data Model: RE-002 Relative Strength Momentum Engine Integration

**Feature**: `031-re002-rs-momentum`  
**Date**: 2026-08-04  
**Source**: [spec.md](./spec.md) Key Entities + Clarifications  
**Note**: Logical model only — no SQL DDL, no migration scripts, no ORM code.

---

## 1. Entity Overview

```text
RecommendationEngineRegistration (config/logical)  engine_id=RE-002
        │
        ▼
LongLivedExperiment (governance Experiment) 1──* EngineDecisionRecord
        │
        ▼
EngineDecisionRecord  1──*  (optional link)  AnalysisHistory (production)
        │                         │
        │                         └── production action/score comparison
        │
        ├── EvidencePayload (embedded/JSON)  — includes RS fields
        ├── ExplanationPayload (embedded/JSON)
        ├── ValidationResultSet (embedded/JSON)
        └── StrategyTrace (embedded/JSON)

ScanRunIdentity (logical) 1──* EngineDecisionRecord
PaperOrder / Prefill (existing) *── provenance → EngineDecisionRecord + Experiment
```

**Reuse note**: `EngineDecisionRecord` maps to the existing multi-engine decisions store used by RE-001. RE-002 adds rows with `engine_id = "RE-002"` and experiment attribution.

---

## 2. Entities

### 2.1 RecommendationEngineRegistration (RE-002)

Logical/config entity (settings-backed in MVP).

| Attribute | Type (logical) | Required | Notes |
| --------- | -------------- | -------- | ----- |
| engine_id | string | yes | Constant `RE-002` |
| name | string | yes | Relative Strength Momentum Engine |
| engine_version | string | yes | e.g. `1.0` |
| stage | enum | yes | `OFF` \| `LAB_SHADOW` \| `PAPER_LINKED` |
| enabled | boolean | yes | master switch (`re002_enabled`) |
| updated_at | datetime | no | if persisted |

**Uniqueness**: `engine_id` + `engine_version` (or single active version config).

---

### 2.2 LongLivedExperiment (governance)

Existing Experiment entity used as RE-002 attribution root.

| Attribute | Type (logical) | Required | Notes |
| --------- | -------------- | -------- | ----- |
| experiment_id | UUID | yes | Primary key |
| engine_id | string | yes | Metadata / tag = `RE-002` |
| status | enum | yes | active / paused / completed / etc. (existing model) |
| name / description | string | yes | Operator-visible identity |
| engine_version | string | preferred | Snapshot at registration |
| started_at / completed_at | datetime | as applicable | Lifecycle |

**Rules**:
- MVP: **one active** long-lived RE-002 experiment for attribution at a time.
- Pause/complete ⇒ no new RE-002 side effects (with stage OFF also stopping side effects).
- History retained after complete; a new long-lived experiment may be registered later manually.

---

### 2.3 EngineDecisionRecord (system of record, multi-engine)

Persisted first-class row for one RE-002 evaluation outcome (shared table pattern).

| Attribute | Type (logical) | Required | Notes |
| --------- | -------------- | -------- | ----- |
| recommendation_id | UUID/string | yes | stable Decision Object id |
| engine_id | string | yes | `RE-002` |
| engine_version | string | yes | |
| experiment_id | UUID/string | preferred | Long-lived experiment attribution |
| symbol | string | yes | App symbol key |
| mode | string | yes | e.g. swing |
| scan_run_id | string/int | preferred | Completed-scan identity family |
| analysis_history_id | int | optional | Link to production analysis row |
| market_regime | string | yes* | Bull / Sideways / Bear / `UNKNOWN` |
| trading_objective | string | yes | REDS field |
| trading_style | string | yes | long-only swing |
| strategy_family | string | conditional | required for BUY/WATCH; may be null on early REJECT |
| strategy_name | string | conditional | primary strategy identity |
| recommendation_state | enum | yes | `BUY` \| `WATCH` \| `REJECT` |
| confidence_score | number | yes | finite |
| risk_profile | object/string | yes | |
| portfolio_decision | object/string | yes | |
| evidence | object | yes | **Must include RS-related fields when computable** |
| explanation | object/string | yes | Leadership-focused rationale |
| reason_codes | list[string] | yes | e.g. `missing_market_context`, `weak_relative_strength`, `portfolio_context_unavailable` |
| trade_guidance | object | optional | entry/SL/target; `complete` flag for paper prefill |
| production_action | string | optional | comparison |
| production_score | number | optional | comparison |
| is_mismatch | boolean | optional | production_action != recommendation_state |
| created_at | datetime | yes | UTC |
| evaluation_status | enum | yes | `success` \| `rejected_by_rules` \| `error` \| `timeout` |

\* Missing market context: store regime `UNKNOWN` **and** `recommendation_state=REJECT` with `missing_market_context`.

**Cardinality rule (SC-011)**: For each enabled lab run, **one Decision Object per shortlisted evaluation-set symbol** (including eligibility REJECT).

**Uniqueness (recommended)**: one decision per (`engine_id`, `symbol`, `scan_run_id`, `engine_version`) — prefer append-with-run uniqueness for audit; idempotent on `recommendation_id`.

**Indexes (logical)**:
- `(engine_id, created_at)`
- `(symbol, created_at)`
- `(scan_run_id)`
- `(recommendation_state)`
- `(experiment_id)` when present
- `(analysis_history_id)` if linked

---

### 2.4 Recommendation Decision Object (payload contract)

Maps onto EngineDecisionRecord columns + JSON payloads. Required REDS fields per FR-004; EngineID constant `RE-002`. See [contracts/re002-decision-object.md](./contracts/re002-decision-object.md).

---

### 2.5 StrategyTrace (embedded)

| Field | Description |
| ----- | ----------- |
| primary_strategy | One of: Relative Strength Leadership, Relative Strength Momentum Continuation, Sector Leadership Alignment, Strong RS + Trend Alignment |
| supporting_strategies | Multi-timeframe RS, volume leadership, sector RS, breadth, price structure quality |
| rejected_strategies | List with reasons |
| validation_results | Regime, liquidity, risk, portfolio, leadership quality, policy, bull_stock_filter, rs_prefilter |

---

### 2.6 EvidencePayload (RS-focused)

| Field | Required | Notes |
| ----- | -------- | ----- |
| rs_vs_market | preferred | Score/rank when available |
| rs_vs_sector | preferred | |
| multi_timeframe_rs | optional | |
| rs_persistence | optional | slope/stability |
| leadership_rank | optional | |
| supporting_confirmations | optional | volume, breadth, structure |
| eligibility | yes | bull_stock_pass, rs_prefilter_pass, reason_codes |

Never invent RS ranks when inputs missing — use reason codes instead.

---

### 2.7 Paper Trade Provenance (existing entity extension)

| Field | Required when RE-002-originated | Notes |
| ----- | ------------------------------- | ----- |
| source_engine_id | yes | `RE-002` |
| engine_version | yes | |
| recommendation_id | yes | Link to Decision Object |
| experiment_id | preferred | Long-lived experiment |
| account_id | yes | **Same user paper account** (no separate RE-002 account) |

---

### 2.8 Engine Run Diagnostics / Metrics

Logical observations (metrics log / experiment metrics):

| Field | Notes |
| ----- | ----- |
| engine_id | RE-002 |
| experiment_id | long-lived |
| scan_run_id | |
| symbols_evaluated | should equal shortlist size when healthy |
| counts_by_state | BUY/WATCH/REJECT |
| success / error / timeout counts | |
| duration_ms | |
| avg_rs_of_buys | when RS available (SC-012) |
| mismatch_rate_vs_production | optional |

---

## 3. Relationships

| From | To | Cardinality | Notes |
| ---- | -- | ----------- | ----- |
| LongLivedExperiment | EngineDecisionRecord | 1 : * | Attribution while active |
| ScanRunIdentity | EngineDecisionRecord | 1 : * | Lab comparison by scan |
| EngineDecisionRecord | AnalysisHistory | * : 0..1 | Production compare link |
| EngineDecisionRecord | PaperOrder | 1 : * | Operator-initiated only |
| Registration | EngineDecisionRecord | 1 : * | version stamp |

---

## 4. State Transitions

### Engine stage

```text
OFF ⇄ LAB_SHADOW ⇄ PAPER_LINKED
         │
         └── ACTIVE reserved / out of scope
```

### Experiment lifecycle (long-lived)

```text
registered → active → paused ⇄ active → completed
                         │
                         └── no new side effects when paused/completed
```

### Recommendation state (per decision)

```text
(evaluation) → BUY | WATCH | REJECT
```

No other states. Validation/eligibility can only produce WATCH/REJECT downgrades from candidate BUY — never create BUY alone.

---

## 5. Validation Rules (data)

1. `engine_id` must be `RE-002` for this feature’s writes.
2. `recommendation_state` ∈ {BUY, WATCH, REJECT}.
3. BUY/WATCH require primary strategy identity (family + name).
4. REJECT for missing regime must include `missing_market_context`.
5. REJECT for weak RS must include explicit RS reason code.
6. `confidence_score` finite.
7. Evidence object present; RS fields preferred when computable.
8. `experiment_id` present when long-lived experiment active and persist enabled.
9. No silent omission for evaluation-set symbols when engine active.

---

## 6. What is not modeled here

- Exact SQL types, indexes DDL, Alembic revision bodies.
- Full Experiment table physical schema (reuse existing).
- Full paper account ledger redesign.
- Doc 04 full leadership analytics warehouse.
