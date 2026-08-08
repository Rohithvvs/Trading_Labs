# Tasks: RE-002 Relative Strength Momentum Engine Integration

**Input**: Design documents from `/specs/031-re002-rs-momentum/`  
**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included for production-safety gates (SC-001, SC-009, SC-011, FR-012, FR-024, FR-025, shortlist-only, multi-engine coexistence). Spec independent tests and quickstart scenarios require verifiable checks; keep tests additive and non-destructive to existing suites. Do not modify RE-001 business rules or Baseline recommendation math.

**Organization**: Tasks grouped by user story for independent implementation and validation.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: User story label (`[US1]`…`[US6]`) — required only in story phases
- Every task includes an exact repository file path

## Path Conventions

- Backend: `backend/app/`
- Backend tests: `backend/tests/`
- Frontend: `frontend/src/`
- Migrations: `backend/alembic/versions/`
- Feature docs: `specs/031-re002-rs-momentum/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold RE-002 package and document wiring points without enabling runtime behavior.

- [x] T001 Create RE-002 service package skeleton (`__init__.py` and module placeholders) under `backend/app/services/re002/`
- [x] T002 [P] Add RE-002 package README notes (scope, non-goals, Baseline isolation, multi-engine coexistence with RE-001, long-lived experiment) in `backend/app/services/re002/README.md`
- [x] T003 [P] Record regime-mapping table (platform labels → Bull/Sideways/Bear/UNKNOWN) in `backend/app/services/re002/regime_mapping.md`
- [x] T004 [P] Document conservative RS feature defaults / lookback notes (versioned under engine_version) in `backend/app/services/re002/rs_defaults.md`
- [x] T005 [P] Document `scan_run_id` mapping reuse (same completed-scan identity family as RE-001) in `backend/app/services/re002/scan_identity.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration, schemas, optional experiment_id persistence, registry, and validators required before any user story can run end-to-end. **Reuse** multi-engine `recommendation_engine_decisions` table.

**⚠️ CRITICAL**: No user-story phase starts until this phase is complete.

- [x] T006 Add RE-002 settings fields (`re002_enabled`, `re002_stage` enum `OFF|LAB_SHADOW|PAPER_LINKED`, `re002_version`, `re002_persist_decisions`, `re002_compare_with_production`, `re002_timeout_ms`, `re002_ui_enabled`) with safe defaults OFF/false in `backend/app/config/settings.py`
- [x] T007 Add `is_re002_active` helper (enabled + stage ∈ {LAB_SHADOW, PAPER_LINKED}) in `backend/app/config/settings.py`
- [x] T008 [P] Define RE-002 Recommendation Decision Object + Lab DTOs including optional `trade_guidance`, `experiment_id`, RS evidence fields (Pydantic) in `backend/app/schemas/re002.py` per `specs/031-re002-rs-momentum/contracts/re002-decision-object.md`
- [x] T009 [P] Export new RE-002 schemas from `backend/app/schemas/__init__.py`
- [x] T010 Add optional `experiment_id` column (nullable, indexed) to multi-engine decisions model in `backend/app/models/recommendation_engine.py` (do not break RE-001 rows)
- [x] T011 Create additive Alembic migration for `experiment_id` on `recommendation_engine_decisions` (+ index) in `backend/alembic/versions/`
- [x] T012 Implement engine registry helper (RE-002 identity, stage, enabled resolution from settings) in `backend/app/services/re002/registry.py`
- [x] T013 Implement Decision Object completeness validator (FR-004/FR-024/FR-025/FR-026; always REJECT emission rules for weak RS) in `backend/app/services/re002/decision_validator.py`
- [x] T014 [P] Define portfolio/risk snapshot resolver contract (requesting user paper/risk; unavailable → `portfolio_context_unavailable`) in `backend/app/services/re002/portfolio_context.py`
- [x] T015 [P] Confirm feature permission key `recommendation_lab` remains Admin+Trader (reuse existing seed; no second feature key) — document RE-002 visibility in `backend/app/services/re002/README.md` and verify catalog in `frontend/src/utils/featureCatalogDefaults.ts`
- [x] T016 Implement long-lived experiment binding helper (resolve/create active RE-002 experiment metadata; pause/complete semantics) in `backend/app/services/re002/experiment_binding.py` using `backend/app/governance/experiment.py`

**Checkpoint**: App boots with migration applied, flags OFF, no RE-002 runtime side effects; RE-001 and Baseline paths unchanged.

---

## Phase 3: User Story 1 — Lab Engine Without Touching Production (Priority: P1) 🎯 MVP

**Goal**: RE-002 evaluates shortlist/full-analysis symbols after Baseline recommendation, always emits Decision Objects (including weak-RS REJECT), persists under EngineID RE-002, fails open, never changes production shortlist/labels or Baseline engine.

**US1 engine scope (vs US5)**: Deliver complete Decision Objects with primary/supporting/validation and fail-closed rules. Baseline regime bucket applied; full Doc 02 regime priority polish is **US5**.

**Independent Test**: Run analysis/scan with RE-002 OFF vs `LAB_SHADOW`; production BUY/WATCH/REJECT and shortlist membership identical; RE-002 rows exist for **every** shortlisted symbol (SC-011); RE-002 exception does not fail production path.

### Tests for User Story 1

- [x] T017 [P] [US1] Unit tests for missing market context → REJECT + `missing_market_context` in `backend/tests/unit/test_re002_missing_regime.py`
- [x] T018 [P] [US1] Unit tests for Decision Object validator and state constraints in `backend/tests/unit/test_re002_decision_validator.py`
- [x] T019 [P] [US1] Unit tests for shortlist-only evaluation filter in `backend/tests/unit/test_re002_evaluation_set.py`
- [x] T020 [P] [US1] Unit tests for weak RS / eligibility fail → REJECT Decision Object (never silent skip) in `backend/tests/unit/test_re002_weak_rs_emission.py`
- [x] T021 [P] [US1] Unit tests: portfolio snapshot unavailable → no BUY + `portfolio_context_unavailable` in `backend/tests/unit/test_re002_portfolio_context.py`
- [x] T022 [P] [US1] Unit tests: RecommendationState set only by deterministic engine path (LLM cannot override) in `backend/tests/unit/test_re002_determinism.py`
- [x] T023 [US1] Integration/regression: production/Baseline invariance with RE-002 on/off in `backend/tests/regression/test_re002_production_invariance.py`
- [x] T024 [US1] Integration: RE-002 timeout/exception fail-open preserves production result in `backend/tests/integration/test_re002_isolation.py`
- [x] T025 [US1] Integration: SC-011 one Decision Object per shortlist symbol including REJECT paths in `backend/tests/integration/test_re002_shortlist_coverage.py`
- [x] T026 [P] [US1] Integration: multi-engine coexistence RE-001 + RE-002 neither clobber in `backend/tests/integration/test_re002_multi_engine_coexistence.py`

### Implementation for User Story 1

- [x] T027 [P] [US1] Implement LabExecutionContext builder (immutable snapshot of shared inputs + production recommendation + production trade_plans + scan_run_id + experiment_id) in `backend/app/services/re002/context.py`
- [x] T028 [P] [US1] Implement regime mapper (platform → Bull/Sideways/Bear/UNKNOWN; unusable → fail closed) in `backend/app/services/re002/regime.py`
- [x] T029 [US1] Implement Bull Stock Filter + Relative Strength pre-filter eligibility using existing TA/RS services (no new market-data client); always build REJECT object on fail in `backend/app/services/re002/eligibility.py`
- [x] T030 [P] [US1] Implement RS feature assembly (stock vs market/sector, multi-TF, persistence) consuming shared RS/sector services in `backend/app/services/re002/rs_features.py`
- [x] T031 [US1] Implement primary strategy orchestration (RS Leadership, RS Momentum Continuation, Sector Leadership Alignment, Strong RS + Trend Alignment) + supporting strategies + validation layer (incl. leadership quality) in `backend/app/services/re002/engine.py`
- [x] T032 [US1] Wire portfolio/risk snapshot via `portfolio_context.py` into validation (fail-closed BUY when unavailable) in `backend/app/services/re002/engine.py`
- [x] T033 [US1] Implement ranking by RS quality + single-primary conflict resolution in `backend/app/services/re002/ranking.py`
- [x] T034 [US1] Implement confidence scorer (RS strength, leadership, support, regime, validation) in `backend/app/services/re002/confidence.py`
- [x] T035 [US1] Implement Decision Object builder (REDS fields + strategy trace + reason_codes + RS evidence + optional trade_guidance) in `backend/app/services/re002/decision_builder.py`
- [x] T036 [US1] Implement decision persistence service (write/query multi-engine table with `engine_id=RE-002`, experiment_id, comparison metadata, scan_run_id) in `backend/app/services/re002/persistence.py`
- [x] T037 [US1] Implement metrics counters (evaluate/persist/error/timeout/state counts) in `backend/app/services/re002/metrics.py`
- [x] T038 [US1] Implement isolated RE-002 runner (`re002_enabled` + stage ∈ {LAB_SHADOW,PAPER_LINKED}, timeout, fail-open logging, always-emit Decision Object for evaluation set) in `backend/app/services/re002/runner.py`
- [x] T039 [US1] Export `run_re002_isolated_async` (or equivalent) from `backend/app/services/re002/__init__.py`
- [x] T040 [US1] Wire runner after production recommendation (parallel to RE-001, independent try/except) in `backend/app/agents/orchestrator_agent.py` shortlist analysis path only
- [x] T041 [US1] Ensure evaluation set restricted to production shortlist/full-analysis symbols in orchestrator hook in `backend/app/agents/orchestrator_agent.py`
- [x] T042 [US1] Attach optional `lab_engines["RE-002"]` summary on analysis response assembly without overwriting production fields in `backend/app/agents/orchestrator_agent.py`
- [x] T043 [US1] Add structured logs for RE-002 start/complete/error/timeout under logger `app.re002` via `backend/app/services/re002/runner.py`
- [x] T044 [US1] Confirm production `RecommendationService` remains untouched for labels in `backend/app/services/recommendation_service.py` (code review guardrails only — no production authority changes)
- [x] T045 [US1] Confirm RE-001 package business rules not modified (review-only) under `backend/app/services/re001/`
- [x] T046 [US1] Verify scheduler/daily-scan entrypoint still invokes RE-002 when enabled in `backend/tests/integration/test_re002_scheduler_path.py`

**Checkpoint**: US1 MVP — RE-002 lab decisions persist for all shortlist symbols; production invariance holds; flags OFF produces zero new decisions.

---

## Phase 4: User Story 2 — Side-by-Side Operator Review (Priority: P1)

**Goal**: Operators (Admin + Trader with `recommendation_lab`) review RE-002 vs production (and RE-001 if present) on symbol detail and Lab comparison surfaces.

**Independent Test**: After a lab run, open symbol detail and Lab comparison; see RE-002 state, strategy, RS evidence or reject reason, production comparison without DB access; permission-denied without feature key.

### Tests for User Story 2

- [x] T047 [P] [US2] API tests for RE-002 lab decision list/detail + multi-engine comparison + permission enforcement in `backend/tests/integration/test_re002_lab_api.py`
- [x] T048 [P] [US2] Frontend unit/component tests for RE-002 detail section empty/permission/data states in `frontend/src/components/__tests__/Re002DetailSection.test.tsx`

### Implementation for User Story 2

- [x] T049 [P] [US2] Implement lab query service (by scan_run_id / symbol / recommendation_id / engine_id=RE-002) in `backend/app/services/re002/lab_query.py`
- [x] T050 [US2] Extend multi-engine Lab read routes to include RE-002 registration, symbol latest, scan comparison rows (engine_id filter/columns) without breaking RE-001 clients in `backend/app/routes/re001_lab.py` **or** additive `backend/app/routes/re002_lab.py` registered alongside (prefer extending shared recommendation-lab router if already multi-engine capable)
- [x] T051 [US2] Register any new router exports in `backend/app/routes/__init__.py`
- [x] T052 [P] [US2] Extend lab comparison DTOs for multi-engine rows (production + RE-001 optional + RE-002) in `backend/app/schemas/re002.py` and/or shared lab schemas
- [x] T053 [P] [US2] Add frontend API helpers for RE-002 lab list/detail/comparison in `frontend/src/api.ts`
- [x] T054 [US2] Implement RE-002 section component (state, strategy, RS evidence, reason codes, vs production, Lab label, experiment id) in `frontend/src/components/Re002DetailSection.tsx`
- [x] T055 [US2] Embed RE-002 section into symbol/analysis detail in `frontend/src/components/StockDetailPanel.tsx`
- [x] T056 [US2] Extend Lab comparison page for multi-engine columns including RE-002 in `frontend/src/pages/RecommendationLabPage.tsx`
- [x] T057 [US2] Ensure Lab nav remains feature-gated with `recommendation_lab` + respect `re002_ui_enabled` in `frontend/src/layout/navConfig.tsx` and `frontend/src/components/FeatureGuard.tsx`
- [x] T058 [US2] Clear experimental/lab labeling on all RE-002 UI surfaces in `frontend/src/components/Re002DetailSection.tsx` and `frontend/src/pages/RecommendationLabPage.tsx`

**Checkpoint**: US2 — operators complete side-by-side review under SC-002/SC-004; retail scanner cards remain production-sourced (SC-008).

---

## Phase 5: User Story 3 — Experiment Registration, Execution, Isolation (Priority: P1)

**Goal**: RE-002 binds to one long-lived experiment; decisions/metrics attributed until pause/complete; pause/OFF stops new side effects.

**Independent Test**: Register/activate long-lived RE-002 experiment; run two scans; decisions share same experiment_id; pause experiment → no new RE-002 decisions; history remains readable.

### Tests for User Story 3

- [x] T059 [P] [US3] Unit tests for experiment binding resolve/active/pause semantics in `backend/tests/unit/test_re002_experiment_binding.py`
- [x] T060 [US3] Integration: long-lived experiment attribution across two scan_run_ids in `backend/tests/integration/test_re002_experiment_attribution.py`
- [x] T061 [US3] Integration: pause or stage OFF produces zero new RE-002 Decision Objects in `backend/tests/integration/test_re002_experiment_pause.py`

### Implementation for User Story 3

- [x] T062 [US3] Wire experiment binding into context builder + runner (require active long-lived experiment for side effects when policy requires it) in `backend/app/services/re002/runner.py` and `backend/app/services/re002/context.py`
- [x] T063 [US3] Stamp `experiment_id` on every persisted RE-002 Decision Object when active in `backend/app/services/re002/persistence.py`
- [x] T064 [US3] Add ops helper/CLI notes or thin governance integration for registering RE-002 long-lived experiment (engine metadata tags) using `backend/app/governance/experiment_cli.py` and document procedure in `backend/app/services/re002/README.md`
- [x] T065 [US3] Expose experiment identity on lab registration/health read models in `backend/app/services/re002/lab_query.py` and lab routes
- [x] T066 [P] [US3] Show experiment identity on Lab UI surfaces in `frontend/src/pages/RecommendationLabPage.tsx` and `frontend/src/components/Re002DetailSection.tsx`
- [x] T067 [US3] Ensure stage OFF and experiment pause both disable new side effects (single gate function) in `backend/app/services/re002/registry.py` and `backend/app/services/re002/experiment_binding.py`

**Checkpoint**: US3 — SC-010 long-lived experiment history works; SC-007 zero new artefacts when disabled.

---

## Phase 6: User Story 4 — Independent Paper Trading and Analytics (Priority: P2)

**Goal**: Operator-initiated paper prefill from RE-002 on same account with mandatory provenance; analytics expose RE-002 health + basic RS aggregates (MVP scope).

**Independent Test**: Create paper ticket from RE-002 BUY (manual only); provenance tags present; no auto-orders under PAPER_LINKED; analytics show counts by state and optional avg RS of BUYs; Baseline paper fills and production aggregates unchanged.

### Tests for User Story 4

- [x] T068 [P] [US4] Integration test paper prefill provenance from RE-002 decision (same account, no auto-order) in `backend/tests/integration/test_re002_paper_provenance.py`
- [x] T069 [P] [US4] Integration/API test RE-002 health counts + avg RS of BUYs without breaking production engine-health in `backend/tests/integration/test_re002_analytics.py`
- [x] T070 [P] [US4] Unit/integration: PAPER_LINKED does not auto-create paper orders in `backend/tests/unit/test_re002_no_auto_paper.py`

### Implementation for User Story 4

- [x] T071 [P] [US4] Ensure paper prefill schemas accept RE-002 provenance fields (`source_engine_id`, `source_engine_version`, `source_recommendation_id`, `experiment_id`) in `backend/app/schemas/paper_trading.py` (reuse/extend existing engine-generic fields)
- [x] T072 [US4] Accept RE-002 provenance and apply trade guidance rule (RE-002 complete plan else production trade_plans) in `backend/app/services/paper_trading_service.py` (no fill-engine changes; no auto-order path)
- [x] T073 [US4] Wire provenance + guidance through `POST /paper-trading/from-recommendation` (or equivalent) in `backend/app/routes/paper_trading.py`
- [x] T074 [P] [US4] Extend frontend paper prefill/order types and display RE-002 provenance badge in `frontend/src/types.ts` and `frontend/src/components/OrderDrawer.tsx`
- [x] T075 [US4] Implement RE-002 analytics query (counts by state, errors/timeouts, optional mismatch, avg_rs_of_buys when RS present) in `backend/app/services/re002/analytics.py`
- [x] T076 [US4] Expose RE-002 health segment on lab health/analytics route in `backend/app/routes/re001_lab.py` or `backend/app/routes/analytics.py` and schemas in `backend/app/schemas/re002.py`
- [x] T077 [P] [US4] Optional frontend metrics strip for RE-002 on Lab page in `frontend/src/pages/RecommendationLabPage.tsx`
- [x] T078 [US4] Document deferred Doc 04 full leadership suite explicitly as non-MVP in `backend/app/services/re002/README.md`

**Checkpoint**: US4 — paper attribution (SC-005) and analytics MVP (SC-012) work; no auto-orders; paper fills unchanged.

---

## Phase 7: User Story 5 — Regime-Adaptive Leadership Behaviour (Priority: P2)

**Goal**: Participation and strategy priority shift by Bull / Sideways / Bear per RE-002 Docs 01–02; bear BUY count ≤ 50% bull BUY count on shared fixtures (SC-006).

**Independent Test**: Feed bull/sideways/bear fixtures with equivalent stock quality; confirm participation aggressiveness and strategy priority shifts without changing production labels.

### Tests for User Story 5

- [x] T079 [P] [US5] Unit tests for regime strategy activation tables in `backend/tests/unit/test_re002_regime_activation.py`
- [x] T080 [US5] Fixture-based test SC-006 bear BUY ≤ 50% bull BUY in `backend/tests/unit/test_re002_regime_participation.py`

### Implementation for User Story 5

- [x] T081 [P] [US5] Encode regime strategy priority / participation tables (config or code) in `backend/app/services/re002/strategy_config.py`
- [x] T082 [US5] Apply adaptive activation and ranking biases by regime in `backend/app/services/re002/engine.py` and `backend/app/services/re002/ranking.py`
- [x] T083 [US5] Ensure Sideways/Bear selectivity increases REJECT/WATCH rates without inventing default regime in `backend/app/services/re002/eligibility.py` and `backend/app/services/re002/engine.py`
- [x] T084 [P] [US5] Add regime-wise decision count diagnostics to metrics/analytics in `backend/app/services/re002/metrics.py` and `backend/app/services/re002/analytics.py`

**Checkpoint**: US5 — regime-adaptive philosophy demonstrable; production path still invariant.

---

## Phase 8: User Story 6 — Register, Configure, and Disable Safely (Priority: P3)

**Goal**: Operators can enable/disable/version RE-002 via settings/stage without redeploy; unauthorized users cannot access lab surfaces.

**Independent Test**: Toggle OFF → zero new decisions; toggle LAB_SHADOW → decisions resume; unauthorized user denied lab surfaces; Decision Objects store EngineID + version.

### Tests for User Story 6

- [x] T085 [P] [US6] Unit tests for registry stage/enabled matrix in `backend/tests/unit/test_re002_registry.py`
- [x] T086 [US6] Integration: flag OFF zero artefacts after prior enable in `backend/tests/integration/test_re002_flag_off.py`
- [x] T087 [P] [US6] API permission tests for lab routes without `recommendation_lab` in `backend/tests/integration/test_re002_lab_permissions.py`

### Implementation for User Story 6

- [x] T088 [US6] Ensure every persisted Decision Object stores `engine_id=RE-002` and `engine_version` from settings in `backend/app/services/re002/decision_builder.py` and `backend/app/services/re002/persistence.py`
- [x] T089 [US6] Expose registration read endpoint for RE-002 stage/version/enabled in lab routes (`backend/app/routes/re001_lab.py` multi-engine registration or `backend/app/routes/re002_lab.py`)
- [x] T090 [P] [US6] Document env aliases (`RE002_*`) and safe defaults in `backend/app/services/re002/README.md` and optional note in `docs/` if project keeps ops notes there
- [x] T091 [US6] Verify `re002_ui_enabled` gates frontend RE-002 sections without removing production UX in `frontend/src/components/Re002DetailSection.tsx` and `frontend/src/pages/RecommendationLabPage.tsx`

**Checkpoint**: US6 — safe operational control (SC-007) and permission model (FR-022).

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Regression pack, quickstart validation, docs, and multi-engine hygiene.

- [x] T092 [P] Run and extend Baseline recommendation regression suite remains green (document command + any RE-002-specific guard) in `backend/tests/regression/` 
- [x] T093 [P] Scanner smoke remains green with RE-002 enabled OFF and ON (LAB_SHADOW) in `backend/tests/` (existing scanner smoke path)
- [x] T094 [P] Paper fill/replay smoke unchanged in existing paper tests under `backend/tests/`
- [x] T095 Verify RE-001 regression/invariance still green when RE-002 present in `backend/tests/regression/` and/or `backend/tests/integration/test_re002_multi_engine_coexistence.py`
- [x] T096 Execute quickstart scenarios A–L checklist against local/dev and record results in `specs/031-re002-rs-momentum/quickstart.md` (notes section) or feature checklist
- [x] T097 [P] Align contracts vs implementation field names (decision object, lab API, UI) in `specs/031-re002-rs-momentum/contracts/`
- [x] T098 [P] Update feature package completion notes (SCS mapping, non-goals, deferred Doc 04 suite) in `backend/app/services/re002/README.md`
- [x] T099 Performance sanity: isolation timeout respected under shortlist load; log p95 notes in `backend/app/services/re002/README.md`
- [x] T100 Confirm no live order placement path introduced (code review of paper + orchestrator) in `backend/app/services/paper_trading_service.py` and `backend/app/agents/orchestrator_agent.py`

**Checkpoint**: Definition of Done ready for controlled LAB_SHADOW enablement.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies
- **Phase 2 Foundational**: Depends on Setup — **BLOCKS all user stories**
- **Phase 3 US1**: Depends on Foundational — **MVP**
- **Phase 4 US2**: Depends on Foundational + US1 persistence/runner (needs Decision Objects to display)
- **Phase 5 US3**: Depends on Foundational + US1 (attribution on persist/runner); can partially parallel with US2 after T036/T038
- **Phase 6 US4**: Depends on US1 Decision Objects; experiment_id preferred from US3
- **Phase 7 US5**: Depends on US1 engine core; polish of activation tables
- **Phase 8 US6**: Mostly Foundational + polish; permission tests after US2 routes exist
- **Phase 9 Polish**: Depends on all desired stories

### User Story Dependencies

| Story | Depends on | Independently testable after |
| ----- | ---------- | ---------------------------- |
| US1 | Foundational | Phase 3 complete |
| US2 | US1 decisions exist | Phase 4 complete |
| US3 | US1 runner/persist | Phase 5 complete |
| US4 | US1 (+ US3 preferred) | Phase 6 complete |
| US5 | US1 engine | Phase 7 complete |
| US6 | Foundational (+ US2 for permission UI) | Phase 8 complete |

### Within Each User Story

- Tests preferably written first and failing before implementation
- Context/eligibility before engine
- Engine before persistence/runner
- Runner before orchestrator wire
- API before frontend
- Story complete before next priority when sequential

### Parallel Opportunities

- Phase 1: T002–T005 parallel
- Phase 2: T008–T009, T014–T015 parallel after settings
- US1 tests T017–T022 parallel; T027–T028, T030 parallel after foundations
- US2: T047–T048, T049, T053 parallel
- US3 tests T059 parallel with implementation prep
- US4: T068–T070, T071, T074, T077 parallel where file-safe
- US5: T079, T081 parallel
- Polish: T092–T094, T097–T098 parallel

---

## Parallel Example: User Story 1

```text
# Tests in parallel:
T017 test_re002_missing_regime.py
T018 test_re002_decision_validator.py
T019 test_re002_evaluation_set.py
T020 test_re002_weak_rs_emission.py
T021 test_re002_portfolio_context.py
T022 test_re002_determinism.py

# Then core modules (after tests scaffolded):
T027 context.py  ||  T028 regime.py  ||  T030 rs_features.py
# Then sequential engine pipeline:
T029 eligibility → T031 engine → T033 ranking → T034 confidence → T035 decision_builder → T036 persistence → T038 runner → T040 orchestrator wire
```

---

## Parallel Example: User Story 2

```text
T047 lab API tests  ||  T048 Re002DetailSection tests
T049 lab_query.py   ||  T053 frontend api.ts helpers
T050–T052 routes/schemas → T054–T058 UI wiring
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 Setup  
2. Complete Phase 2 Foundational  
3. Complete Phase 3 US1  
4. **STOP and VALIDATE**: production invariance + SC-011 shortlist coverage + fail-open  
5. Demo lab decisions via DB/API before full UI if needed  

### Incremental Delivery

1. Setup + Foundational → safe OFF deploy  
2. US1 → lab decisions exist (MVP)  
3. US2 → operator review  
4. US3 → experiment attribution  
5. US4 → paper + analytics  
6. US5 → regime polish  
7. US6 → ops hardening  
8. Polish → full quickstart + regressions  

### Suggested MVP Scope

**US1 only** (Phases 1–3): isolated RE-002 engine on shortlist, Decision Objects persisted, Baseline untouched.  
**Recommended first production LAB_SHADOW enablement**: US1 + US2 + US3 (review + experiment attribution).  
**Paper/analytics**: US4 before promotion-oriented ops.  

---

## Notes

- [P] = different files, no incomplete dependencies  
- Do **not** modify Baseline `recommendation_service.py` scoring  
- Do **not** modify RE-001 strategy rules under `backend/app/services/re001/`  
- Do **not** invent a second decisions table — reuse multi-engine store  
- Do **not** auto-create paper orders  
- Do **not** silently skip shortlist symbols  
- Commit after each task or logical group  
- Stop at checkpoints to validate independently  
- Full Doc 04 leadership analytics suite is explicitly out of MVP task scope (T078)

## Audit remediation (2026-08-04)

Production audit High/Medium findings closed in code:

- FR-028: side effects require `RE002_EXPERIMENT_ID` (no unattributed decisions)
- FR-024: no invented RS ranks; `missing_relative_strength` REJECT
- FR-029: structured paper provenance columns + migration `20260804_paper_lab_provenance`
- Lab C6 history + RE-002 recent scans APIs; Lab UI multi-engine scan list
- Health SQL aggregates; unified active gate; parallel lab engines; shared portfolio snapshot
- Tests present under `tests/unit|integration|regression/test_re002_*` (51 passing with `--noconftest`)

---

## Task Count Summary

| Phase | Story | Task IDs | Approx count |
| ----- | ----- | -------- | ------------ |
| 1 Setup | — | T001–T005 | 5 |
| 2 Foundational | — | T006–T016 | 11 |
| 3 US1 | US1 | T017–T046 | 30 |
| 4 US2 | US2 | T047–T058 | 12 |
| 5 US3 | US3 | T059–T067 | 9 |
| 6 US4 | US4 | T068–T078 | 11 |
| 7 US5 | US5 | T079–T084 | 6 |
| 8 US6 | US6 | T085–T091 | 7 |
| 9 Polish | — | T092–T100 | 9 |
| **Total** | | **T001–T100** | **100** |
