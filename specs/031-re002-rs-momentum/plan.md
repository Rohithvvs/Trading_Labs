# Implementation Plan: RE-002 Relative Strength Momentum Engine Integration

**Branch**: `031-re002-rs-momentum` | **Date**: 2026-08-04 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/031-re002-rs-momentum/spec.md` (RE-002 Docs 01–04 + REDS v1.0 + clarify session 2026-08-04)

**Note**: This is the master implementation plan for brownfield integration. It explains *how* integration will be executed. It does **not** contain implementation code, SQL, API bodies, or task lists (`tasks.md` is produced by `/speckit-tasks`).

---

## 1. Executive Summary

### Goal

Integrate **RE-002 (Relative Strength Momentum Engine)** as a **new Recommendation Engine** that executes as a **long-lived Experiment** inside the Recommendation Lab of the existing production Trading Application—without replacing or redesigning the Baseline/composite recommendation engine, scanner, technical analysis, paper fill engine, analytics formulas, scheduler jobs, or Recommendation Lab architecture.

### Approach

1. **Keep production path authoritative** for shortlists and retail BUY/WATCH/REJECT (Baseline untouched).
2. **Register RE-002** as a lab engine with stages `OFF` | `LAB_SHADOW` | `PAPER_LINKED` (`ACTIVE` reserved/out of scope).
3. **Bind RE-002 to one long-lived experiment** for decision/paper/metric attribution until pause/complete.
4. **Run RE-002 only on production shortlist / full-analysis symbols**, after production recommendations resolve.
5. **Emit a Decision Object for every evaluation-set symbol**, including early REJECT for weak RS / eligibility failures (no silent skips).
6. **Isolate failures** so RE-002 never fails production scans.
7. **Persist** REDS Decision Objects in the **existing multi-engine first-class decisions store** (`recommendation_engine_decisions` pattern; EngineID = `RE-002`).
8. **Surface** results via symbol-detail RE-002 section + multi-engine Lab comparison.
9. **Paper**: same user account, operator-initiated prefill only, mandatory provenance tags (no auto-orders, no separate portfolio).
10. **Analytics**: decision/run health + RS evidence + basic aggregates when RS available; full Doc 04 leadership suite deferred.
11. **Validate** with production/Baseline invariance and RE-002 behavior tests before any promotion path (promotion remains out of scope).

### Expected outcome

Operators can compare RE-002 leadership decisions to Baseline (and RE-001 if present), paper-trade with provenance under a long-lived experiment, and accumulate experiment evidence—while production advisory behavior remains unchanged when RE-002 is off or in lab mode.

---

## Summary (SpecKit)

| Item | Content |
| ---- | ------- |
| Primary requirement | Lab-isolated RE-002 engine producing BUY/WATCH/REJECT Decision Objects under a long-lived experiment |
| Technical approach | Mirror proven RE-001 multi-engine pattern: post-production isolated evaluate → persist by EngineID → Lab/UI/paper/analytics; Baseline untouched |
| Migration style | Additive, flag-gated, fail-open, shortlist-only, multi-engine store reuse |
| Clarifications locked | Same paper account + provenance; operator-initiated paper; long-lived experiment; always REJECT Decision Object on weak RS; MVP analytics scope |

---

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/React 18 (frontend)  
**Primary Dependencies**: FastAPI, SQLAlchemy, Pydantic Settings, PostgreSQL, APScheduler, existing FYERS/market-data stack, Vite React SPA, existing RE-001 multi-engine Lab patterns  
**Storage**: PostgreSQL — **reuse** multi-engine `recommendation_engine_decisions` (logical SoR already EngineID-namespaced); production `analysis_history` retained as production SoR; experiment tables/records via existing governance Experiment model  
**Testing**: pytest (backend unit/integration/regression), Vitest/Playwright patterns as existing for frontend  
**Target Platform**: Existing two-tier monolith (FastAPI + React SPA), singleton-worker scheduler pod  
**Project Type**: web application (backend + frontend)  
**Performance Goals**: RE-002 must not reduce production path success rate; evaluate shortlist only; per-symbol isolation timeout; SC-003 ≥95% RE-002 attempts without impacting production success  
**Constraints**: Brownfield; no scanner rewrite; no Baseline change; no live orders; advisory-only; REDS Decision Object shape; deterministic labels; `recommendation_lab` permission; stages `OFF|LAB_SHADOW|PAPER_LINKED`; experiment-first attribution  
**Scale/Scope**: Shortlist-sized evaluation set per scan; multi-user paper accounts; multi-engine Lab (Baseline + RE-001 + RE-002)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Project constitution file is a placeholder template; **operational gates** derived from REDS / feature spec / brownfield principles:

| Gate | Status | Notes |
| ---- | ------ | ----- |
| Brownfield safety / bounded delta | **PASS** | Additive RE-002 package + thin hooks; no redesign |
| Production/Baseline authority preserved | **PASS** | Lab mode never owns shortlist |
| Deterministic recommendation states | **PASS** | Labels not LLM-owned |
| Reuse shared services (no parallel stacks) | **PASS** | SCS mapped to existing modules; decisions store reused |
| Isolation / fail-open for production | **PASS** | Mirror RE-001 isolation envelope |
| Backward-compatible APIs | **PASS** | Optional fields / lab routes only |
| No live trading | **PASS** | Advisory + operator-initiated paper only |
| Multi-engine coexistence | **PASS** | EngineID namespacing; do not modify RE-001 rules |
| Clarifications complete for MVP | **PASS** | Session 2026-08-04 (5/5) |

**Post-Phase-1 re-check**: PASS — design artifacts remain additive contracts only; no gate violations requiring Complexity Tracking.

---

## Project Structure

### Documentation (this feature)

```text
specs/031-re002-rs-momentum/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1 validation guide
├── contracts/           # Phase 1 interface contracts
│   ├── re002-decision-object.md
│   ├── re002-lab-api.md
│   └── re002-ui-contract.md
├── spec.md              # Feature specification (complete)
├── checklists/
│   └── requirements.md
└── tasks.md             # NOT created by /speckit-plan
```

### Source Code (repository root — existing layout; planned touchpoints only)

```text
backend/app/
├── agents/
│   └── orchestrator_agent.py          # EXTEND: isolated RE-002 hook after production (parallel to RE-001)
├── config/
│   └── settings.py                    # EXTEND: re002_* flags/stage
├── models/
│   └── recommendation_engine.py       # REUSE (multi-engine decisions); optional experiment_id link EXTEND if missing
├── schemas/                           # EXTEND: RE-002 Decision Object + lab DTOs (parallel to re001 schemas)
├── services/
│   ├── recommendation_service.py      # KEEP production path
│   ├── paper_trading_service.py       # EXTEND: provenance accepts RE-002 (if not already engine-generic)
│   ├── re001/                         # KEEP — do not modify RE-001 business rules
│   └── re002/                         # NEW package (RS leadership engine + isolation helpers)
├── governance/
│   └── experiment*.py                 # REUSE / EXTEND: long-lived RE-002 experiment registration/attribution
├── routes/                            # EXTEND: lab read APIs / multi-engine compare already present → add RE-002
└── ...

frontend/src/
├── components/
│   ├── StockDetailPanel (or equivalent)  # EXTEND: RE-002 section
│   └── Lab comparison view               # EXTEND: multi-engine columns include RE-002
├── layout/navConfig                      # REUSE feature-gated Lab entry
├── api helpers                           # EXTEND: RE-002 lab fetch if needed
└── feature catalog                       # REUSE recommendation_lab permission

alembic/                                  # EXTEND only if experiment_id / indexes missing for multi-engine use
```

**Structure Decision**: Stay within the existing backend/frontend monolith. Introduce a bounded `re002` service package parallel to `re001`. **Reuse** the multi-engine decisions table and Lab surfaces. Do not create a microservice or redesign agent topology.

---

## Complexity Tracking

> No constitution/gate violations requiring justification. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

---

## 2. Architecture Review

### Current system (as-is)

```text
Scanner / Full Analysis
        → Market Data + TA bulk
        → News / Fund / Backtest (parallel)
        → Sector RS / Market permission (challenger/overlays)
        → RecommendationAgent + RecommendationService (BASELINE / PRODUCTION)
        → Final gate / shortlist classification
        → Persist AnalysisHistory
        → Rank / API / Dashboard
        → [if enabled] RE-001 isolated lab evaluate → recommendation_engine_decisions (engine_id=RE-001)
        → Experiment / governance services available for research lifecycle
```

### Target system (to-be, lab mode)

```text
... production Baseline path unchanged through shortlist classification ...
        → [if re001 active] existing RE-001 path (unchanged rules)
        → [if re002_enabled && stage in LAB_SHADOW|PAPER_LINKED && long-lived experiment active]
              Build immutable LabExecutionContext (shortlist symbol only)
              → RE-002 engine evaluate (isolated, timed)
              → Recommendation Decision Object (EngineID=RE-002)
                 including REJECT for weak RS / eligibility fails
              → Persist recommendation_engine_decisions (+ experiment_id attribution)
        → Return production response (+ optional multi-engine lab payload)
        → UI: production dashboard unchanged; detail/Lab multi-engine when permitted
        → Paper: operator-initiated prefill with RE-002 provenance on same account
        → Analytics: EngineID=RE-002 health + basic RS aggregates when available
```

### Design principles

1. **Production-first**: shortlist and retail UX remain Baseline-sourced.
2. **Engine purity**: RE-002 only decides/explains leadership; does not own market data, TA math, paper fills, or scheduler.
3. **REDS compliance**: standard pipeline order and Decision Object fields.
4. **Fail-open**: production success independent of RE-002.
5. **Multi-engine reuse**: same decisions store and Lab pattern as RE-001; namespaced by EngineID.
6. **Experiment-first**: long-lived experiment identity on all RE-002 artefacts.
7. **Additive only**: no rewrite of `analysis_history.recommendation` meaning.

---

## 3. Current System Review

| Capability | Existing home | Role today | RE-002 posture |
| ---------- | ------------- | ---------- | -------------- |
| Market data | market_data / FYERS / candle store | OHLCV authority | REUSE read-only |
| Scanner | screener / scan execution / orchestrator stages | Universe → shortlist | KEEP; consume shortlist only |
| Technical analysis | technical_analysis_service | Indicators + scores | REUSE |
| News / sentiment | news agent/service | Sentiment inputs | REUSE context only |
| Fundamentals | fundamental agent | Context scores | REUSE context only |
| Backtest | backtest_service / agent | Historical inputs | REUSE later validation |
| Baseline recommendation | recommendation_service + agent | Composite BUY/WATCH/REJECT + trade plans | **KEEP untouched** |
| RE-001 Lab engine | `services/re001/*` | Continuation lab engine | **KEEP**; coexist |
| Multi-engine decisions | `recommendation_engine_decisions` | Lab SoR by engine_id | **REUSE** for RE-002 rows |
| Experiment framework | governance ExperimentService / CLI | Lifecycle + metrics | REUSE / EXTEND attribution |
| Paper trading | paper_trading_service | Simulated execution | KEEP fills; EXTEND provenance |
| Analytics | analytics routes/services | Health / daily | EXTEND EngineID slice |
| Dashboard | Scanner, StockDetail, Lab compare, Paper | Operator UX | EXTEND RE-002 surfaces |
| Scheduler | APScheduler daily-scan | Triggers pipeline | KEEP; piggyback lab eval |
| Config / flags | settings + feature permissions | Runtime control | EXTEND `re002_*` |
| Logging / audit | logger / audit | Observability | REUSE / EXTEND events |
| Sector RS / regime / breadth | sector_rs, market_permission, breadth | Market context | **REUSE heavily** (RS is core to RE-002) |

---

## 4. RE-002 Integration Strategy

### Strategy statement

**Parallel lab engine with shared shortlist inputs, separate Decision Object outputs, long-lived experiment attribution, and zero production authority until a future explicit promotion feature.**

### Locked product decisions (from clarify + spec)

| Decision | Value |
| -------- | ----- |
| Persistence | Multi-engine first-class decisions store (reuse existing table pattern) |
| UI | Symbol detail RE-002 section + Lab multi-engine comparison |
| Visibility | Admin + Trader with `recommendation_lab` |
| Evaluation set | Production shortlist / full-analysis only (same shortlist as Baseline) |
| Missing market regime | REJECT + reason code; no default regime |
| Weak RS / eligibility fail | Always Decision Object REJECT (never silent skip) |
| Paper model | Same user account + mandatory provenance tags |
| Paper generation | Operator-initiated prefill only (no auto-orders) |
| Experiment binding | One long-lived RE-002 experiment until pause/complete |
| Analytics MVP | Health counts + RS evidence + basic aggregates; full Doc 04 suite deferred |
| Stages | `OFF` \| `LAB_SHADOW` \| `PAPER_LINKED` |

### Integration posture by concern

| Concern | Strategy |
| ------- | -------- |
| Scanner shortlist | **Do not change** ownership or stage-stopping |
| Baseline scores/gates | **Do not change** |
| RE-001 | **Do not change** business rules; run independently if both enabled |
| RE-002 placement | After production recommendation resolved per shortlist symbol (parallel hook to RE-001) |
| Shared inputs | Reuse already-fetched candles/TA/regime/sector/RS/breadth/portfolio snapshot |
| Persistence | Insert rows with `engine_id=RE-002` (+ experiment_id) |
| Experiment Manager | Register/activate long-lived RE-002 experiment; pause stops new side effects |
| Experiment Runner | Attribute each scan’s RE-002 decisions/metrics to the active long-lived experiment |
| API | Optional lab block on analysis responses and/or dedicated multi-engine lab reads |
| UI | Feature-gated; clearly labeled lab/experimental |
| Paper | Provenance + operator prefill; same account |
| Analytics | Segment by EngineID without redefining production aggregates |
| Scheduler | No new trading cron; piggyback existing scan path |

### Safest migration approach

1. Ship **OFF by default**.
2. Register long-lived experiment + enable **LAB_SHADOW** in controlled env.
3. Prove **production/Baseline invariance** (SC-001, SC-009).
4. Prove **N Decision Objects for N shortlist symbols** (SC-011).
5. Enable UI + operator paper prefill path.
6. Enable basic analytics aggregates.
7. Never auto-promote to production shortlist in this feature.

### Integration map (how RE-002 plugs in)

| Integration point | How |
| ----------------- | --- |
| **Recommendation Lab** | Register engine; show decisions; multi-engine compare includes RE-002 |
| **Experiment Manager** | Create/activate/pause/complete long-lived RE-002 experiment |
| **Experiment Runner** | Link scan evaluation outputs to active experiment_id |
| **Recommendation Pipeline** | Post-Baseline isolated evaluate; no production label rewrite |
| **Recommendation Orchestrator** | Thin hook after production decision (fail-open); collect Decision Object |
| **Recommendation Decision Object** | REDS fields + RS evidence + reason_codes + experiment linkage metadata |
| **Paper Trading** | Operator prefill from decision; same account; provenance tags |
| **Experiment Analytics** | Counts by state, run health, avg RS of BUYs when available |
| **Experiment Comparison** | Lab view: production vs RE-002 (and RE-001 if present) |
| **Recommendation History** | Query decisions store filtered by engine_id=RE-002 / experiment_id |
| **Dashboard** | Production cards unchanged; detail + Lab lab-labeled |
| **Configuration** | `re002_enabled`, `re002_stage`, version, timeout, persist, compare, UI flags |
| **Logging** | Structured RE-002 evaluate/persist/error/metrics events |

---

## 5. Module Classification

Legend: **KEEP** · **REUSE** · **EXTEND** · **MODIFY** · **NEW** · **DO NOT REMOVE**

| Module | Classification | Why |
| ------ | -------------- | --- |
| Market Data Pipeline | **KEEP** / **REUSE** | Canonical OHLCV; RE-002 must not own broker fetch |
| Scanner Engine | **KEEP** | Spec forbids modifying scanner output / shortlist ownership |
| Technical Analysis | **KEEP** / **REUSE** | Consume indicators/scores; no formula redesign |
| News Analysis | **KEEP** / **REUSE** | Context only; not RE-002 primary philosophy |
| Fundamental Analysis | **KEEP** / **REUSE** | Context only |
| Backtesting | **KEEP** / **REUSE** | Offline validation later; no private BT stack |
| Recommendation Orchestrator | **EXTEND** | Additive isolated RE-002 hook after production (and alongside RE-001) |
| Baseline Recommendation Engine | **KEEP** / **DO NOT REMOVE** | Production authority; scoring/gates unchanged |
| Recommendation Decision Object (REDS) | **REUSE** shape / **NEW** RE-002 population | Same REDS contract; RE-002 fills fields + RS evidence |
| Recommendation Lab | **EXTEND** | Multi-engine surfaces already exist; add RE-002 |
| Experiment Manager | **REUSE** / **EXTEND** | Long-lived experiment registration/lifecycle for RE-002 |
| Experiment Runner / attribution | **EXTEND** | Attach experiment_id to RE-002 decisions/metrics |
| Paper Trading Engine (fills) | **KEEP** | No fill/replay redesign |
| Paper prefill / provenance | **EXTEND** | Accept RE-002 engine + experiment provenance |
| Analytics Engine (production aggregates) | **KEEP** | Do not redefine Baseline metrics |
| Analytics surfaces | **EXTEND** | EngineID=RE-002 health + basic RS aggregate |
| Dashboard retail scanner | **KEEP** | Production-sourced cards |
| Dashboard Lab / detail | **EXTEND** | RE-002 section + multi-engine columns |
| Portfolio / Risk | **REUSE** | Portfolio-before-trade validation inputs |
| Scheduler | **KEEP** | Piggyback only; no new live-trade cron |
| Configuration | **EXTEND** | `re002_*` settings + existing feature permission |
| Logging / Audit | **REUSE** / **EXTEND** | Structured RE-002 events |
| Database production tables | **KEEP** | `analysis_history.recommendation` meaning unchanged |
| Database multi-engine decisions | **REUSE** | Existing table; RE-002 rows by engine_id |
| Database experiment models | **REUSE** / **EXTEND** if link fields needed | Long-lived experiment identity |
| AI Agents / LLM | **KEEP** | Explanation assist only; not labels |
| RE-001 package | **KEEP** | Independent; do not change continuation rules |
| Caching | **REUSE** | Avoid dual market-data load |
| Sector RS / Relative Strength services | **REUSE** | Core inputs for RE-002 philosophy |
| Regime / Breadth services | **REUSE** | Participation control + supporting evidence |

**REMOVE**: Nothing.  
**MODIFY** (true change of existing domain logic): **None planned.** Integration is EXTEND/NEW/REUSE only.

---

## 6. Reuse Strategy

| Existing capability | Why reuse instead of replace |
| ------------------- | ---------------------------- |
| Market Data Service / candle store | Single data truth; no dual broker stack |
| Scanner shortlist | Shared evaluation set with Baseline; bounds work |
| Technical Analysis Service | Structure/volume/MAs for RS+trend alignment support |
| News / Fundamentals | Optional context only |
| Backtest Service | Future offline validation of leadership rules |
| Sector RS / Relative Strength | **Primary evidence source** for RE-002 (SCS-04 mapping) |
| Market permission / regime | Bull/Sideways/Bear participation mapping |
| Market breadth | Supporting evidence |
| Baseline RecommendationService | Continues as production engine |
| RE-001 isolation/runner patterns | Proven fail-open envelope; copy pattern, not business rules |
| `recommendation_engine_decisions` | Multi-engine SoR already EngineID-namespaced |
| Lab query / comparison APIs | Extend filters/columns rather than second lab product |
| Paper Trading Service | Correct lifecycle; only provenance needed |
| Portfolio / risk snapshot loaders | Fail-closed portfolio validation (FR-026) |
| ExperimentService / CLI | Governance lifecycle without new framework |
| Analytics engine-health patterns | Dimensional extend by EngineID |
| Settings / feature permissions | Operational control model exists (`recommendation_lab`) |
| Logging / audit | Compliance trail |
| Scheduler + scan locks | Safe concurrent execution |
| Caching | Performance; integrity |

### REDS Shared Core Services → existing modules

| REDS SCS | Existing reuse target |
| -------- | --------------------- |
| SCS-01 Market Regime | market permission / FEAT-004 regime classification |
| SCS-02 Market Breadth | market_breadth |
| SCS-03 Sector Analysis | sector analysis services |
| SCS-04 Relative Strength | sector_rs / RS services (**critical for RE-002**) |
| SCS-05 Liquidity | TA/screener liquidity checks |
| SCS-06 Technical Indicators | technical_analysis_service |
| SCS-07 News & Event | news + event calendar (context only) |
| SCS-08 Risk | risk/gate settings (read-only validation) |
| SCS-09 Portfolio | paper/portfolio snapshot |
| SCS-10 Confidence | engine-local scorer using shared inputs |
| SCS-11 Explainability | structured evidence + optional LLM text assist |
| SCS-12 Audit | logging + decisions table + experiment metrics |

---

## 7. New Component Strategy

Only **new** components unique to RE-002 (logical). Prefer parallel package structure to RE-001 without forking shared stores.

### 7.1 RE-002 Engine Registry (settings-backed)

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Resolve RE-002 enablement, stage, version metadata |
| Responsibilities | `is_re002_active`; registration view for Decision Objects |
| Inputs | `re002_*` settings |
| Outputs | Engine registration DTO |
| Consumers | Orchestrator hook, Lab UI, analytics |
| Dependencies | settings |
| Lifecycle | Process config; hot-toggle if platform supports |

### 7.2 RE-002 Engine Module (core)

| Aspect | Definition |
| ------ | ---------- |
| Purpose | RS leadership / momentum orchestration and decisioning |
| Responsibilities | Context interpretation; Bull Stock + RS pre-filter; primary strategy families (RS Leadership, RS Momentum Continuation, Sector Leadership Alignment, Strong RS + Trend Alignment); supporting evidence; validation (incl. leadership quality); ranking by RS quality; confidence; Decision Object + explanation; always emit object for evaluation-set symbols |
| Inputs | LabExecutionContext (candles, TA, regime, RS features, sector, breadth, portfolio/risk, production snapshot for compare only) |
| Outputs | Recommendation Decision Object (EngineID=RE-002) |
| Consumers | Persistence, Lab API, paper prefill, analytics |
| Dependencies | Shared services read-only; no private market-data stack |
| Lifecycle | Per-symbol evaluation inside isolation timeout |

### 7.3 Lab Execution Context Builder (RE-002)

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Immutable shared-input snapshot + production comparison fields + experiment_id |
| Responsibilities | Assemble after production decision; freeze inputs; attach scan_run_id, user portfolio snapshot if available |
| Inputs | Orchestrator per-symbol artefacts |
| Outputs | LabExecutionContext |
| Consumers | RE-002 engine |
| Dependencies | Existing result schemas; portfolio loader patterns |
| Lifecycle | Per symbol per scan |

### 7.4 RE-002 Isolated Runner

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Fail-open, timed evaluation envelope |
| Responsibilities | Timeout, exception swallow for production, metrics incr, call engine + persist |
| Inputs | Context, settings timeout |
| Outputs | Decision Object or null on hard failure (still count error; prefer REJECT object when possible) |
| Consumers | Orchestrator |
| Dependencies | engine, persistence, metrics |
| Lifecycle | Per symbol |

### 7.5 Decision Persistence Adapter (RE-002)

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Write/query RE-002 rows in multi-engine decisions store |
| Responsibilities | Validate completeness; persist engine_id=RE-002 + experiment_id; idempotent behavior; query by scan/symbol/engine/experiment |
| Inputs | Decision Object + run identifiers |
| Outputs | Engine Decision Records |
| Consumers | Lab API, analytics, history |
| Dependencies | Existing RecommendationEngineDecision model/table |
| Lifecycle | Per evaluation |

### 7.6 Experiment Binding Service (RE-002)

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Resolve the single active long-lived RE-002 experiment for attribution |
| Responsibilities | Register/activate; resolve active experiment_id; pause/complete semantics; refuse new side effects when paused/OFF |
| Inputs | ExperimentService, config |
| Outputs | experiment_id for decisions/paper/metrics |
| Consumers | Runner, paper provenance, analytics |
| Dependencies | governance ExperimentService |
| Lifecycle | Ops-managed long-lived record |

### 7.7 Lab Query / Multi-engine Adapter extensions

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Read RE-002 decisions for detail + comparison |
| Responsibilities | Filter engine_id=RE-002; multi-engine join with production and RE-001 |
| Inputs | scan_run_id, symbol, window |
| Outputs | Lab DTOs |
| Consumers | Frontend Lab + detail |
| Dependencies | persistence, auth/feature guards |
| Lifecycle | Request-scoped |

### 7.8 Symbol Detail RE-002 Panel + Lab multi-engine column

| Aspect | Definition |
| ------ | ---------- |
| Purpose | Operator explainability and comparison |
| Responsibilities | State, strategy, RS evidence, reason codes, vs production; lab labeling |
| Inputs | Lab DTOs |
| Outputs | UI |
| Consumers | Admin/Trader with `recommendation_lab` |
| Dependencies | feature permission |
| Lifecycle | Session UI |

**Not new**: Scanner, TA engine, paper fill engine, Baseline recommendation math, scheduler framework, multi-engine decisions table product, Lab architecture redesign.

---

## 8. Dependency Analysis

### Internal dependency order

```text
Settings / feature flags (re002_*)
        → Engine registry
        → Long-lived experiment registration (Experiment Manager)
        → Lab context builder (needs production result + scan_run_id + portfolio snapshot)
        → RE-002 engine
        → Decision persistence (engine_id + experiment_id)
        → Lab API / optional response enrichment
        → Frontend detail + Lab multi-engine view
        → Paper provenance (operator path)
        → Analytics segmentation (health + basic RS aggregates)
```

### Shared service dependencies

- **Critical for quality**: market history, TA, **RS/sector RS**, regime.
- Missing regime → REJECT (FR-025).
- Missing RS features → REJECT with reason (clarified; never invent ranks).
- Missing portfolio → fail-closed for BUY (FR-026).

### Recommendation dependencies

- Production Baseline must complete first (for shared shortlist set and comparison metadata).
- RE-001 optional concurrent path; no ordering dependency beyond shared production completion.

### Paper trading dependencies

- Prefill/order create accepts engine + experiment provenance.
- Fill engine independent of RE-002.
- Same user paper account.

### Analytics dependencies

- Decisions table queryable by `engine_id`, `recommendation_state`, `scan_run_id`, time window, and experiment_id when present.
- RS score fields available on evidence for basic averages.

### Experiment framework dependencies

- ExperimentService start/pause/resume/complete/list/show/metric/report.
- Ability to store/tag engine_id=RE-002 on experiment metadata.

### Configuration dependencies

- `re002_enabled`, `re002_stage`, `re002_version`, `re002_persist_decisions`, `re002_compare_with_production`, `re002_timeout_ms`, `re002_ui_enabled` (or equivalent).
- Feature permission `recommendation_lab`.

### Database dependencies

- Multi-engine decisions table available (already from RE-001 work).
- Additive only if experiment_id column/index missing.
- No production recommendation column semantic change.

### Scheduler dependencies

- Existing scan jobs call pipeline; RE-002 rides that path when enabled + experiment active.
- No new promotion/live-trade cron.

---

## 9. Phased Implementation Roadmap

### Phase 1 — Engine Registration

| Field | Content |
| ----- | ------- |
| **Purpose** | Make RE-002 a first-class registered lab engine with safe defaults OFF |
| **Business Value** | Controlled enablement without code redeploy for every ops toggle |
| **Scope** | `re002_*` settings; registry module; engine metadata; feature flag wiring; docs for stages |
| **Dependencies** | Settings patterns (mirror RE-001) |
| **Architecture Impact** | Config-only EXTEND; no production path change |
| **Risk Level** | Low |
| **Validation** | OFF default; stage enum validation; registry returns RE-002 identity |
| **Rollback** | Leave flags OFF / remove env overrides |
| **Exit Criteria** | Registry reports RE-002; `is_re002_active` false by default; Baseline path unchanged |

### Phase 2 — Recommendation Pipeline Integration

| Field | Content |
| ----- | ------- |
| **Purpose** | Evaluate shortlist symbols with RE-002 orchestration after Baseline decision |
| **Business Value** | Core leadership decisions available for Lab review |
| **Scope** | Context builder; engine (filters, strategies, validation, confidence, explain); isolated runner; orchestrator hook; Decision Object builder; always-emit REJECT for eligibility/RS fails |
| **Dependencies** | Phase 1; shared RS/regime/TA inputs; RE-001 isolation pattern as template |
| **Architecture Impact** | EXTEND orchestrator; NEW `re002` package |
| **Risk Level** | Medium–High (latency/isolation) |
| **Validation** | Production invariance; SC-011 N objects; missing regime REJECT; weak RS REJECT; multi-engine coexistence with RE-001 |
| **Rollback** | Disable `re002_enabled` / stage OFF (hook no-ops) |
| **Exit Criteria** | Enabled lab run produces Decision Objects for all shortlist symbols without changing Baseline labels |

### Phase 3 — Experiment Execution

| Field | Content |
| ----- | ------- |
| **Purpose** | Bind RE-002 to one long-lived experiment for attribution |
| **Business Value** | Fair governed comparison and history for promotion review later |
| **Scope** | Experiment registration/activation; resolve active experiment_id; stamp decisions/metrics; pause stops new side effects; list/show/report visibility |
| **Dependencies** | Phase 2; ExperimentService |
| **Architecture Impact** | EXTEND governance attribution; optional persistence field for experiment_id |
| **Risk Level** | Medium |
| **Validation** | SC-010; pause/OFF zero new artefacts; all decisions share experiment_id while active |
| **Rollback** | Pause/complete experiment; stage OFF |
| **Exit Criteria** | Long-lived experiment owns RE-002 decision attribution across scans |

### Phase 4 — Paper Trading Integration

| Field | Content |
| ----- | ------- |
| **Purpose** | Operator-initiated paper prefill with RE-002 provenance on same account |
| **Business Value** | Evidence path toward Doc 04 paper validation without auto-trading risk |
| **Scope** | Prefill accepts RE-002 decision; trade guidance complete→else production plan; provenance tags; no auto-orders |
| **Dependencies** | Phase 2–3; paper service provenance path |
| **Architecture Impact** | EXTEND paper prefill only |
| **Risk Level** | Medium |
| **Validation** | SC-005; no auto-order under PAPER_LINKED; same account; filterable RE-002 trades |
| **Rollback** | Disable UI prefill / stage OFF |
| **Exit Criteria** | Operator can create RE-002-attributed paper ticket; fill engine unchanged |

### Phase 5 — Analytics Integration

| Field | Content |
| ----- | ------- |
| **Purpose** | Expose RE-002 health and basic leadership aggregates |
| **Business Value** | Operational visibility without full Doc 04 suite |
| **Scope** | Counts by state; run success/failure; optional mismatch; avg RS of BUYs when RS present; EngineID segmentation |
| **Dependencies** | Phase 2–3 persistence |
| **Architecture Impact** | EXTEND analytics queries |
| **Risk Level** | Low–Medium |
| **Validation** | SC-012; Baseline aggregates unchanged |
| **Rollback** | Hide RE-002 analytics cards/filters |
| **Exit Criteria** | Operators see RE-002 health without DB console |

### Phase 6 — Dashboard Integration

| Field | Content |
| ----- | ------- |
| **Purpose** | Operator UX for explainability and comparison |
| **Business Value** | Trust/challenge leadership decisions before paper |
| **Scope** | Symbol detail RE-002 section; Lab multi-engine rows/columns; lab labeling; feature permission |
| **Dependencies** | Lab API (Phase 2–3); frontend feature gates |
| **Architecture Impact** | EXTEND UI only |
| **Risk Level** | Medium (operator confusion) |
| **Validation** | SC-002, SC-004; production cards unchanged; SC-008 no forced lab gate |
| **Rollback** | `re002_ui_enabled` false / feature permission off |
| **Exit Criteria** | Admin+Trader with permission can review RE-002 vs production in under 2 minutes |

### Phase 7 — Validation and Regression

| Field | Content |
| ----- | ------- |
| **Purpose** | Prove safety and readiness for controlled enablement |
| **Business Value** | Risk reduction before broader lab use |
| **Scope** | Full regression (Baseline, scanner, paper, analytics, RE-001 if present); performance soak notes; documentation of SCS mapping and non-goals |
| **Dependencies** | Phases 1–6 |
| **Architecture Impact** | Test/docs only |
| **Risk Level** | Low (process) |
| **Validation** | SC-001–SC-012; acceptance criteria list; fail-open isolation tests |
| **Rollback** | Keep RE-002 OFF in production ops |
| **Exit Criteria** | Definition of Done checklist green; ready for ops enablement in LAB_SHADOW |

**Phase sequencing note**: Phases 5–6 may partially parallelize after Phase 2 APIs exist; Phase 3 should land before paper provenance relies on experiment_id; Phase 7 is continuous and final gate.

---

## 10. Migration Strategy

### Migration sequence

1. Deploy code with **defaults OFF** (no behavior change).
2. Apply any **additive** schema (only if experiment_id/index gaps).
3. Register long-lived RE-002 experiment in non-prod.
4. Enable **LAB_SHADOW** in non-prod; run invariance + SC-011 tests.
5. Enable Lab UI for permitted roles.
6. Enable operator paper prefill in `PAPER_LINKED` (still manual).
7. Enable basic analytics.
8. Controlled production **LAB_SHADOW** only after regression green.
9. Promotion to production shortlist authority: **out of scope**.

### Incremental rollout

- Flag-gated per environment.
- Engine stage independent of Baseline.
- RE-001 and RE-002 independently toggled.

### Feature flag strategy

| Flag (logical) | Default | Effect |
| -------------- | ------- | ------ |
| `re002_enabled` | false | Master switch |
| `re002_stage` | OFF | OFF / LAB_SHADOW / PAPER_LINKED |
| `re002_persist_decisions` | true when active | Persist Decision Objects |
| `re002_compare_with_production` | true when active | Store comparison meta |
| `re002_timeout_ms` | planning default (mirror RE-001 scale) | Isolation budget |
| `re002_ui_enabled` | false or tied to permission | Lab UI surfaces |
| Feature permission `recommendation_lab` | existing | Admin+Trader visibility |

### Experiment enable/disable strategy

- Active long-lived experiment + lab stage required for side effects.
- Pause experiment or stage OFF ⇒ no new Decision Objects / prefill side effects.
- Historical decisions remain readable.

### Backward compatibility

- Clients ignore unknown lab fields.
- Production BUY/WATCH lists remain Baseline-driven.
- No removal of existing fields.
- RE-001 contracts and rows unchanged.

### Rollback plan

1. Set `re002_stage=OFF` and/or `re002_enabled=false`.
2. Pause long-lived experiment.
3. Hide UI via permission/flag.
4. Leave persisted RE-002 rows for audit (do not mass-delete).
5. If schema additive, leave columns; unused is safe.

---

## 11. Validation Strategy

| Layer | What to prove |
| ----- | ------------- |
| **Architecture** | Additive hooks only; Baseline/scanner untouched; multi-engine store reuse; SCS mapping documented |
| **Business** | Long-only swing; NIFTY500 intent; advisory-only; regime participation direction (SC-006) |
| **Recommendation** | Decision Object completeness; always N objects; weak RS REJECT; missing regime REJECT; single primary strategy; RS evidence when computable |
| **Experiment** | Long-lived binding; pause stops side effects; history retained; SC-010 |
| **Paper Trading** | Operator-initiated only; same account; provenance 100% (SC-005); fill engine unchanged |
| **Analytics** | EngineID segmentation; SC-012; Baseline aggregates stable |
| **Regression** | Baseline recommendation suite; scanner smoke; paper smoke; analytics smoke; RE-001 coexistence if present |
| **Performance** | Isolation timeout respected; production success not tied to RE-002 failures |

See [quickstart.md](./quickstart.md) for runnable scenarios.

---

## 12. Risk Assessment

| Severity | Risk | Impact | Likelihood | Mitigation | Recovery |
| -------- | ---- | ------ | ---------- | ---------- | -------- |
| **Critical** | RE-002 overwrites production shortlist labels | Wrong retail advice | Low | Separate store; never write production recommendation authority; invariance tests | Stage OFF; redeploy if needed |
| **Critical** | Production scan fails due to RE-002 | Ops outage | Medium | Isolated try/except + timeout; fail-open | Stage OFF; fix runner |
| **Critical** | Baseline engine behavior changes | Systemic advisory risk | Low | KEEP Baseline; regression suite | Revert PR; flags |
| **High** | Operator confuses lab BUY with production BUY | Bad paper/live intent | Medium | UI labeling; production cards unchanged | Disable UI flag |
| **High** | Silent skip of shortlist symbols | Broken Lab compare / SC-011 fail | Medium | Always Decision Object rule; tests | Patch engine emission |
| **High** | RS service gaps invent ranks | False leaders | Medium | Never invent; REJECT with reason | Stage OFF; fix RS mapping |
| **High** | Experiment attribution missing/leaking | Unfair EEF evidence | Medium | Stamp experiment_id; one long-lived active experiment | Pause experiment; re-bind |
| **Medium** | Scan latency regression | Slow ops | Medium | Shortlist-only; timeout; parallel-safe isolation | Reduce timeout/disable |
| **Medium** | Multi-engine UI clutter | UX debt | Medium | Feature-gate; optional columns | Hide RE-002 UI |
| **Medium** | Parameter ambiguity (RS lookbacks) | Inconsistent decisions | Medium | Conservative documented defaults; version stamp | Config bump version |
| **Low** | Doc 05 absent | Ops runbook gaps | High | Assumptions + mirror RE-001 ops | Add Doc 05 later |
| **Low** | Full leadership analytics deferred | Incomplete research UX | High (accepted) | SC-012 MVP boundary | Phase later |

---

## 13. Constraints

- Brownfield only; maximize reuse; no parallel stacks.
- Baseline Recommendation Engine **must remain unchanged**.
- Scanner output **must not be modified** by RE-002.
- REDS v1.0 locked (pipeline, Decision Object, inheritance).
- No live broker orders; advisory + paper only.
- Operator-initiated paper only in MVP.
- No auto-promotion to production.
- No redesign of Market Data, Scanner, TA, News, Fundamentals, Backtesting, Paper fill engine, Scheduler, Analytics engine, Recommendation Lab architecture, or business rule frameworks.
- Do not modify RE-001 continuation business rules.

---

## 14. Assumptions

- Spec clarifications (2026-08-04) are binding for MVP.
- Multi-engine decisions table from RE-001 work is available and EngineID-namespaced.
- Existing RS/sector RS services can supply leadership features sufficient for conservative MVP defaults.
- Regime mapping table Bull/Sideways/Bear can be documented analogously to RE-001.
- ExperimentService can host a long-lived RE-002 experiment with metadata for engine_id.
- Exact RS formulas/lookbacks not frozen in Docs 01–04 → conservative defaults acceptable if versioned.
- Doc 05 not required to start implementation.
- Full Doc 04 leadership report suite is deferred from MVP DoD.

---

## 15. Out of Scope

- Redesign of listed production modules (Market Data, Scanner, TA, News, Fundamentals, Backtesting, Paper engine, Scheduler, Analytics engine, Lab architecture).
- Baseline recommendation scoring/gates changes.
- Auto-promotion / `ACTIVE` production ownership.
- Live trading.
- RE-003…RE-007 implementation (only ensure multi-engine extensibility).
- Separate RE-002 paper portfolio product.
- Automatic paper order placement.
- Per-scan auto experiments.
- Full Doc 04 leadership analytics product suite.
- Publishing RE-002 Document 05.
- New REDS layers or Decision Object redesign.

---

## 16. Definition of Ready

Before implementation coding begins:

1. Spec quality checklist complete (done).
2. Clarify session locked (done — 5/5).
3. This plan + research + data-model + contracts + quickstart accepted.
4. Agreement Baseline remains shortlist authority.
5. Multi-engine decisions store availability confirmed in target environments.
6. RE-001 coexistence regression path identified if RE-001 deployed.
7. `re002_*` flag names agreed (mirror RE-001 naming).
8. Regime mapping approach agreed (document in implementation research notes if needed).
9. Isolation timeout budget agreed (start from RE-001 scale).
10. Long-lived experiment registration ops procedure sketched.
11. Baseline + scanner + paper regression suites identified and runnable.
12. Conservative RS parameter defaults chosen and versioned under engine_version.

---

## 17. Definition of Done

RE-002 plan execution (implementation) is complete when:

1. Phases 1–7 exit criteria met.
2. FR-001–FR-034 satisfied for MVP (deferred items only those explicitly deferred: full leadership suite, ACTIVE promotion).
3. SC-001–SC-012 verified with evidence.
4. Production/Baseline invariance proven with RE-002 on vs off.
5. Every shortlist symbol yields a RE-002 Decision Object when enabled (including weak-RS REJECT).
6. Long-lived experiment attribution verified.
7. Operator-initiated paper provenance verified on same account; no auto-orders.
8. Lab detail + multi-engine comparison usable under `recommendation_lab`.
9. Analytics health segmentation for RE-002 works; Baseline aggregates stable.
10. RE-001 (if present) and Baseline regressions green.
11. Defaults remain safe (OFF) for uncontrolled environments.
12. Ready for `/speckit-tasks` completion and ops-controlled LAB_SHADOW enablement.

---

## Traceability

| Source | Plan consumption |
| ------ | ---------------- |
| REDS v1.0 | Pipeline, Decision Object, SCS mapping, orchestrator boundaries |
| RE-002 Docs 01–04 | Philosophy, strategies, modules, validation, metrics intent |
| Feature spec + clarify | Isolation, experiment binding, paper model, emission rules, analytics MVP |
| Existing RE-001 multi-engine implementation | Isolation, persistence, Lab UI, settings patterns (reuse infrastructure, not RE-001 rules) |

---

## Notes for `/speckit-tasks`

- Generate tasks phase-aligned (1–7) with explicit dependency edges.
- Prefer tasks that enforce **invariance tests first**, then engine behavior, then experiment, paper, analytics, UI.
- Keep Baseline/RE-001 non-touch explicit in task acceptance.
- Do not emit SQL DDL or application code in tasks descriptions beyond file-level intent.
