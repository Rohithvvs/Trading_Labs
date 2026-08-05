# Feature Specification: RE-002 Relative Strength Momentum Engine Integration

**Feature Branch**: `031-re002-rs-momentum`  
**Created**: 2026-08-04  
**Status**: Draft  
**Input**: Integrate RE-002 Relative Strength Momentum Engine as a new Recommendation Engine that executes as an Experiment inside the Recommendation Lab, without redesigning or replacing the existing Trading Application recommendation pipeline or the Baseline / production engine.

**Business source of truth**: RE-002 Specification Package Documents 01–04 (Relative Strength Momentum Engine) and REDS v1.0 (Trading Lab “ALL REs”).  
**Implementation source of truth**: Existing trading-system application (scanner, recommendation, Recommendation Lab, experiment/governance framework, paper trading, analytics, APIs, dashboard, scheduler).  
**RE-002 Document 05 status**: Not yet published in the RE corpus; deployment/ops details below are derived from REDS + Docs 01–04 + current application capabilities and are marked as assumptions where Doc 05 would otherwise govern.

## Clarifications

### Session 2026-08-04

- Q: How should “RE-002 owns independent paper trades” be realized in MVP? → A: Same user paper account with mandatory RE-002 provenance tags only (engine_id, recommendation_id, experiment_id); filterable RE-002 trade set — no separate paper portfolio/sub-account for MVP
- Q: When stage is PAPER_LINKED, how are RE-002 recommendations turned into paper trades in MVP? → A: Operator-initiated prefill only (manual create from decision); no automatic paper order placement in MVP; Doc 04 “all recommendations paper-traded” is a promotion/process gate, not silent auto-execution
- Q: How should RE-002 bind to the Experiment Framework for scan-time decisions in MVP? → A: One long-lived RE-002 experiment record; all scan decisions and paper provenance attach to it until pause/complete (not per-scan auto experiments; not stage-only without experiment entity)
- Q: When a shortlisted symbol fails the Relative Strength pre-filter (weak RS), what must RE-002 emit? → A: Always a Decision Object with RecommendationState = REJECT and explicit weak-RS reason code (e.g. weak_relative_strength); never silent skip for evaluation-set symbols
- Q: Which leadership-specific analytics are required for RE-002 MVP vs deferred? → A: MVP requires decision/run health metrics + RS evidence on Decision Objects; basic leadership aggregates when RS available; full Doc 04 leadership report suite deferred

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lab Engine Produces RS Leadership Decisions Without Touching Production (Priority: P1)

As a quant operator, I want RE-002 to evaluate **only the production shortlist / full-analysis symbols** for relative-strength leadership setups in the Recommendation Lab while the existing Baseline / production recommendation engine continues to publish BUY / WATCH / REJECT for the Scanner and Dashboard unchanged, so that we can validate a leadership engine without risking production advisory quality or scan latency.

**Why this priority**: Brownfield safety requires isolation first. Production and Baseline remain authoritative until explicit promotion. RE-002 must never modify Scanner output.

**Independent Test**: Run a full scan with RE-002 enabled in `LAB_SHADOW` mode; confirm production BUY/WATCH/REJECT lists and scores match a control run with RE-002 disabled, while RE-002 Decision Objects are still produced and stored for lab/experiment review.

**Acceptance Scenarios**:

1. **Given** RE-002 is registered and enabled in `LAB_SHADOW` (or `PAPER_LINKED`) mode, **When** a scanner or full-analysis run completes, **Then** production recommendations, shortlist ranking, and dashboard BUY/WATCH counts are identical to a run with RE-002 disabled.
2. **Given** a shortlisted symbol with sufficient market and relative-strength context, **When** RE-002 evaluates it, **Then** the system produces a standardized Recommendation Decision Object with EngineID = RE-002, RecommendationState ∈ {BUY, WATCH, REJECT}, strategy identity, confidence, RS-related evidence, and explanation.
3. **Given** RE-002 fails or times out for a symbol, **When** the pipeline continues, **Then** production analysis for that symbol still completes successfully and RE-002 failure is recorded without aborting the scan.

---

### User Story 2 - Operator Reviews RE-002 Leadership Decisions and Comparisons (Priority: P1)

As a trader or research operator, I want to inspect RE-002’s primary leadership strategy, relative-strength evidence, validation outcomes, and comparison to production (and other lab engines such as RE-001 when present) for the same symbol and scan, so that I can trust or challenge leadership recommendations before paper trading them.

**Why this priority**: REDS requires explainability and engine comparison before any promotion path. Operators cannot use RE-002 without transparent decision traces.

**Independent Test**: Open symbol detail or lab comparison after a scan and verify production and RE-002 outcomes, primary strategy, RS rank/score evidence, and reject reasons for at least one BUY and one REJECT from RE-002.

**Acceptance Scenarios**:

1. **Given** both production and RE-002 decisions exist for a symbol, **When** the operator opens the symbol’s analysis detail or Lab comparison surface, **Then** they can see both RecommendationStates, scores/confidence, and RE-002 primary strategy name plus RS-related evidence.
2. **Given** RE-002 selected Relative Strength Leadership as primary with volume and multi-timeframe RS as support, **When** the operator reads the explanation, **Then** primary vs supporting vs rejected strategies and validation results are distinguishable.
3. **Given** RE-002 issued REJECT due to weak relative strength, market-regime, leadership quality, risk, or portfolio validation, **When** the operator reviews the decision, **Then** the reject reason is explicit, not a silent empty result.

---

### User Story 3 - Experiment Registration, Execution, and Isolation (Priority: P1)

As a research operator, I want RE-002 to run as a first-class Experiment inside the Recommendation Lab / Experiment Framework with independent lifecycle (register, activate, execute, complete, store, compare, history), so that RE-002 outcomes are governed and comparable without contaminating Baseline results.

**Why this priority**: The feature’s intended operating model is experiment-first; independent experiment identity is required for fair evaluation and promotion review.

**Independent Test**: Register and activate a RE-002 experiment; run evaluations; confirm experiment metadata links to RE-002 decisions, paper trades, and metrics, and that Baseline experiment/production artefacts remain separate.

**Acceptance Scenarios**:

1. **Given** RE-002 is registered as an engine with one long-lived experiment subject, **When** operators list experiments, **Then** that RE-002 experiment appears with engine identity, version, stage, and lifecycle state (not a per-scan experiment flood).
2. **Given** an active long-lived RE-002 experiment, **When** scans produce RE-002 decisions, **Then** those decisions are attributable to **that same experiment** and EngineID RE-002.
3. **Given** RE-002 experiment is paused or engine stage is OFF, **When** scans run, **Then** no new RE-002 decision side effects are produced for that disabled period.

---

### User Story 4 - Independent Paper Trading and Analytics for RE-002 (Priority: P2)

As a research operator, I want to paper-trade RE-002 recommendations and view RE-002-owned analytics and portfolio outcomes independently from Baseline and other engines, so that promotion decisions rest on RE-002-specific evidence.

**Why this priority**: RE-002 business package requires paper trading and leadership-specific metrics; user business rules require independent paper trades and analytics ownership.

**Independent Test**: Prefill or tag a paper order from an RE-002 BUY on the **same user paper account**; confirm mandatory provenance tags, filterable RE-002 trade set, and analytics attribution to RE-002 without creating a separate portfolio product or rewriting Baseline paper portfolio authority.

**Acceptance Scenarios**:

1. **Given** an RE-002 BUY decision, **When** the operator creates a paper ticket from that decision (operator-initiated only), **Then** the ticket lands on the same user paper account as other paper activity, is attributable to RE-002 (`source_engine_id`, version, `recommendation_id`, experiment identity), and does not require a separate RE-002 sub-account or auto-order path.
2. **Given** multiple days of RE-002 lab/experiment runs, **When** analytics or experiment health views are queried for RE-002, **Then** decision counts by state, run success/failure, optional mismatch vs production, and basic leadership aggregates when RS is available (e.g. average RS of BUYs) are available for the configured window — without requiring the full Doc 04 leadership report suite.
3. **Given** RE-002 is not promoted, **When** daily scanner shortlist and production BUY lists are built, **Then** they continue to be driven solely by the existing Baseline / production recommendation engine.

---

### User Story 5 - Regime-Adaptive Leadership Behaviour (Priority: P2)

As a quant operator, I want RE-002 to participate more in bull regimes, restrict to exceptional leaders in sideways regimes, and mostly preserve capital in bear regimes, so that leadership recommendations remain consistent with RE-002 philosophy.

**Why this priority**: Market-before-stock and adaptive participation are core RE-002 invariants (Doc 01 §9, Doc 02 §12).

**Independent Test**: Feed or simulate three market-regime contexts (bull / sideways / bear) for equivalent RS setups and confirm participation aggressiveness shifts as specified without changing production engine labels.

**Acceptance Scenarios**:

1. **Given** market regime = Bull and a valid primary leadership setup, **When** RE-002 evaluates, **Then** participation is allowed under normal confidence rules with preference for strong RS + momentum leadership strategies.
2. **Given** market regime = Sideways, **When** RE-002 evaluates ordinary RS candidates, **Then** only top-tier leaders with higher confirmation proceed; many candidates become WATCH or REJECT.
3. **Given** market regime = Bear, **When** RE-002 evaluates ordinary candidates, **Then** most candidates become WATCH or REJECT except the strongest relative-strength survivors.

---

### User Story 6 - Register, Configure, and Disable RE-002 Safely (Priority: P3)

As a system administrator, I want feature flags and engine registration controls so that RE-002 can be enabled, disabled, versioned, and limited to `LAB_SHADOW` / `PAPER_LINKED` without code redeploy for every operational change.

**Why this priority**: Operational safety and REDS governance require explicit stage control.

**Independent Test**: Toggle RE-002 off; confirm no RE-002 decisions are produced and production path is unchanged; toggle `LAB_SHADOW` on and confirm decisions resume.

**Acceptance Scenarios**:

1. **Given** RE-002 master flag is OFF, **When** scans run, **Then** no RE-002 Decision Objects are generated and no lab UI sections depend on new RE-002 data for that period.
2. **Given** RE-002 is registered with version 1.0, **When** decisions are persisted, **Then** EngineID and EngineVersion are stored with every RE-002 Recommendation Decision Object.
3. **Given** an authenticated Trader or Admin with the lab feature permission enabled, **When** they open symbol detail or Lab comparison after a lab run, **Then** RE-002 decisions are visible when present.
4. **Given** an unauthorized or non-feature-permitted user, **When** they attempt lab-only RE-002 surfaces, **Then** access is denied per existing auth and feature-permission model.

---

### Edge Cases

- **Missing market regime / unusable market context**: RE-002 MUST emit RecommendationState **REJECT** with an explicit reason code (e.g. `missing_market_context`); never BUY; never silent skip without a Decision Object when the symbol was in the evaluation set. Production path unaffected.
- **Weak relative strength pre-filter fail**: For every shortlisted evaluation-set symbol, RE-002 MUST emit a Decision Object with RecommendationState = **REJECT** and explicit reason code (e.g. `weak_relative_strength`); never silent skip; never BUY.
- **Missing RS / sector RS features**: For evaluation-set symbols, emit Decision Object **REJECT** (or WATCH only if partial usable RS remains and hard eligibility still fails BUY rules) with explicit reason; never invent RS ranks; never silent skip.
- **Insufficient history for RS or eligibility filters**: For evaluation-set symbols, Decision Object **REJECT** with explicit reason (e.g. `insufficient_history`); not BUY; not silent skip.
- **Multiple primary strategies qualify**: Exactly one primary strategy owns the recommendation; others become supporting evidence (Doc 02 conflict resolution).
- **Validation fails after primary qualifies**: Result is WATCH or REJECT; never silent BUY.
- **Production BUY but RE-002 REJECT (or reverse)**: Both outcomes retained for comparison; production shortlist still uses production action until promotion.
- **RE-001 and RE-002 both enabled**: Both may produce independent Decision Objects for the same symbol/scan; neither overwrites the other; Lab comparison can show multi-engine rows.
- **RE-002 timeout / exception**: Isolated; production result retained; error logged and counted in experiment/lab health metrics.
- **Empty shortlist**: No RE-002 work beyond idle/no-op; no spurious decisions.
- **Non-shortlisted matched symbols**: Not evaluated by RE-002 in MVP.
- **Concurrent scans**: RE-002 execution must respect existing scan locking and must not corrupt production persistence.
- **Paper account risk limits**: Portfolio/risk validation may force REJECT even if RS leadership is strong (portfolio-before-trade).
- **No portfolio/risk snapshot** (scheduler or user without paper account): Fail-closed for BUY → WATCH or REJECT with reason `portfolio_context_unavailable`; never invent portfolio state.
- **RE-002 BUY without complete RE-002 trade guidance**: Paper prefill falls back to production trade_plans for same symbol/scan; provenance remains RE-002.
- **PAPER_LINKED without operator action**: Decisions are persisted and prefillable; no paper orders appear until an operator initiates create/prefill.
- **Mean reversion / news / earnings / pure breakout without RS**: Out of RE-002 scope; must not appear as RE-002 primary philosophy.
- **Experiment paused mid-day**: No new RE-002 side effects; existing historical decisions remain readable.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST register RE-002 as a distinct Recommendation Engine (EngineID = `RE-002`, name = Relative Strength Momentum Engine) inside the Recommendation Lab, without replacing the Baseline / production recommendation engine or RE-001.
- **FR-002**: System MUST keep the existing production recommendation pipeline (composite score → BUY/WATCH/REJECT, scanner shortlist, dashboard BUY/WATCH lists) behaviorally unchanged when RE-002 is disabled or running only in `LAB_SHADOW` / `PAPER_LINKED` mode.
- **FR-003**: RE-002 MUST emit only RecommendationStates BUY, WATCH, or REJECT (no additional states).
- **FR-004**: Every RE-002 evaluation MUST produce a standardized Recommendation Decision Object containing at minimum: RecommendationID, EngineID, EngineVersion, MarketRegime, TradingObjective, TradingStyle, StrategyFamily, StrategyName, RecommendationState, ConfidenceScore, RiskProfile, PortfolioDecision, Evidence (including RS-related evidence), Explanation, Timestamp.
- **FR-005**: RE-002 MUST follow the REDS standard recommendation pipeline order: Market Context → Universe Selection → Eligibility Filtering (Bull Stock Filter + Relative Strength Pre-Filter) → Strategy Selection → Technical Confirmation → Risk Validation → Portfolio Validation → Confidence Scoring → Recommendation Decision → Explanation → Decision Object.
- **FR-006**: RE-002 MUST NOT bypass Market Regime Detection or the Bull Stock Filter; it MAY apply stricter filters only (including early RS rejection).
- **FR-007**: RE-002 MUST orchestrate primary strategy families: Relative Strength Leadership, Relative Strength Momentum Continuation, Sector Leadership Alignment, Strong RS + Trend Alignment — with exactly one primary strategy owning each recommendation when a BUY or WATCH is issued.
- **FR-008**: Supporting strategies (Multi-timeframe Relative Strength, Volume confirmation of leadership, Sector Relative Strength, Market Breadth support, Price structure quality) MUST NOT independently generate recommendations; they only strengthen or weaken confidence.
- **FR-009**: Validation (market regime, liquidity, risk, portfolio, leadership quality, policy) MUST be able to reject or downgrade candidates and MUST never create a BUY by itself.
- **FR-010**: RE-002 MUST adapt strategy activation and participation by market regime per RE-002 Doc 01 §9 and Doc 02 §12 (Bull high / Sideways low–medium exceptional leaders / Bear very low strongest survivors).
- **FR-011**: RE-002 MUST reuse existing shared platform capabilities for market data, technical indicators, news/events, sector/relative strength, market regime/breadth, backtesting, paper trading, analytics, scheduling, portfolio/risk, logging, configuration, experiment governance, and caching — it MUST NOT re-implement these as private parallel stacks.
- **FR-012**: RE-002 execution MUST be isolatable (feature-flagged) and fail-open with respect to production: RE-002 errors MUST NOT fail the production analysis path.
- **FR-013**: System MUST persist RE-002 decisions (and comparison metadata vs production when both exist) in a first-class queryable decisions store (shared multi-engine decisions table pattern established for lab engines) without overwriting production recommendation fields that drive current scanner shortlists.
- **FR-014**: Operators MUST be able to compare production vs RE-002 outcomes for the same symbol and scan context via (1) an RE-002 section on the existing symbol/analysis detail surface and (2) the Recommendation Lab comparison surface for scan-level side-by-side review (multi-engine capable: production, RE-001 if present, RE-002).
- **FR-015**: Operators MUST be able to originate paper-trading workflow from an RE-002 decision with engine and experiment provenance retained. **MVP paper generation**: **operator-initiated prefill only** — system MUST NOT auto-create paper orders from RE-002 decisions even when stage is `PAPER_LINKED`. `PAPER_LINKED` signals intentional paper-validation mode (provenance and prefill availability), not automatic order placement. **Trade guidance rule**: use complete RE-002 trade guidance on the Decision Object when present; otherwise fall back to production `trade_plans` for the same symbol and scan; provenance fields MUST still identify RE-002.
- **FR-016**: Analytics / experiment surfaces MUST expose RE-002 health metrics for a rolling operational window, independently segmentable by EngineID. **MVP required**: decision counts by state (BUY/WATCH/REJECT), run success/failure (and optional mismatch rate vs production). **MVP required on Decision Objects**: RS-related evidence fields when computable (rank/score/persistence as available). **MVP basic aggregates when RS available**: e.g. average RS of BUY decisions in the window. **Deferred (not MVP DoD blockers)**: full Doc 04 leadership report suite (outperformance vs NIFTY500 time-series, leadership persistence after recommendation, top-rank retention dashboards, full regime-wise leadership quality product reports).
- **FR-017**: Scheduler-driven scans that already invoke the analysis pipeline MUST be able to include RE-002 lab evaluation when the engine is enabled, without requiring a separate manual batch as the only path. **MVP evaluation set**: RE-002 MUST evaluate only symbols on the production shortlist / full-analysis set for that run — the same shortlist analysed by production — not the full NIFTY500 and not the broader pre-shortlist matched set — unless a future feature expands the set.
- **FR-018**: RE-002 MUST be deterministic for a fixed version, fixed inputs, and fixed configuration (no live LLM-owned decision label; explanation text may reuse existing explainability services but MUST NOT solely determine BUY/WATCH/REJECT).
- **FR-019**: System MUST support configuration stages exactly: `OFF` | `LAB_SHADOW` | `PAPER_LINKED` (future `ACTIVE` reserved and out of scope for auto-promotion). Both `LAB_SHADOW` and `PAPER_LINKED` run evaluation+persist when RE-002 is enabled; `OFF` disables all RE-002 side effects. `PAPER_LINKED` is the operational signal that paper attribution / operator prefill is intentional validation mode — **not** automatic paper-order execution.
- **FR-020**: RE-002 MUST remain long-only swing, NIFTY500 universe, Indian equity cash market, advisory-only (no live broker order placement).
- **FR-021**: Mean reversion, event-driven, gap, news-primary, earnings-primary, fundamental-first, intraday, short-selling, and pure breakout-without-RS philosophies MUST remain out of RE-002 primary scope.
- **FR-022**: Access to lab comparison and RE-002 decision surfaces MUST respect existing authentication and feature-permission patterns. **MVP visibility**: both Admin and Trader roles MAY view RE-002 symbol-detail and Lab comparison when feature key **`recommendation_lab`** is enabled. Operational stage/flag controls remain admin-appropriate; unauthenticated access is forbidden.
- **FR-023**: Every RE-002 decision MUST record decision trace elements needed for audit: primary strategy, supporting strategies, rejected strategies, validation results, RS rank/score evidence where available, and final rationale.
- **FR-024**: Bull Stock Filter + Relative Strength Pre-Filter eligibility for RE-002 MUST apply shared REDS minimum intent plus early rejection of weak RS stocks using existing indicator/regime/RS services rather than inventing a second market-data pipeline. **MVP emission rule**: every shortlisted evaluation-set symbol that fails Bull Stock or RS pre-filter MUST still receive a persisted Decision Object with RecommendationState = **REJECT** and an explicit reason code (e.g. `weak_relative_strength`, `failed_bull_stock_filter`); silent omission of Decision Objects for evaluation-set symbols is forbidden.
- **FR-025**: When market regime (or equivalent required market context) is missing or unusable for a symbol in the evaluation set, RE-002 MUST produce a Decision Object with RecommendationState = **REJECT** and an explicit missing-context reason code; it MUST NOT emit BUY and MUST NOT default to an assumed regime.
- **FR-026**: Portfolio validation MUST prefer the authenticated requesting user’s paper/risk snapshot when present. When no usable portfolio/risk snapshot exists (including scheduler/system runs without a user portfolio), RE-002 MUST fail-closed for BUY (WATCH or REJECT) with reason code `portfolio_context_unavailable` and MUST NOT invent portfolio state.
- **FR-027**: Lab comparison and persistence MUST associate each decision with a `scan_run_id` (or equivalent) mapped to the platform’s existing completed-scan identity used by latest-scan / scan snapshot flows so Lab views can list one completed scan’s symbols.
- **FR-028**: System MUST support RE-002 as an Experiment entity within the existing Experiment Framework / Recommendation Lab: registration, activation, execution linkage, completion, storage, comparison, and history, without redesigning the governance CLI/API model. **MVP binding model**: exactly **one long-lived RE-002 experiment** is the attribution target while active; all scan Decision Objects and RE-002-originated paper provenance MUST attach to that experiment until it is paused or completed. MVP MUST NOT auto-create a new experiment per scan/day.
- **FR-029**: RE-002 paper trades and analytics MUST be independently attributable via **mandatory provenance tags** on the **same user paper account** (`source_engine_id` / EngineID = RE-002, engine version, `recommendation_id`, experiment identity) so operators can filter a RE-002 trade set and independent analytics slices. MVP MUST NOT require a separate RE-002 paper portfolio or sub-account. Baseline paper portfolio authority and production analytics aggregates MUST remain intact.
- **FR-030**: RE-002 MUST NOT modify Scanner shortlist generation, stage-stopping rules, matched-symbol lists, or production BUY/WATCH candidate ownership in lab modes.
- **FR-031**: RE-002 MUST NOT change Baseline Recommendation Engine scoring, thresholds, gates, or outputs.
- **FR-032**: Ranking of candidates within RE-002 MUST prioritize Relative Strength quality as the primary ranking dimension per Doc 02 §10–11, then regime alignment, sector leadership, persistence, supporting evidence, and confidence.
- **FR-033**: System MUST support concurrent presence of multiple lab engines (at minimum production Baseline + RE-001 + RE-002) without destructive interference; each engine’s Decision Objects remain namespaced by EngineID.
- **FR-034**: Experiment comparison surfaces MUST allow operators to compare RE-002 against production Baseline (and other registered lab engines when available) using shared decision and metric dimensions.

### Key Entities

- **Recommendation Engine (registered)**: Logical engine identity (Baseline / Production, RE-001, RE-002, …) with version, stage, and enablement.
- **Recommendation Decision Object**: Standardized RE/lab decision payload (REDS §9 fields) with EngineID = RE-002 and RS-related evidence.
- **Production / Baseline Recommendation**: Existing FinalRecommendation / shortlist-driving action for a symbol.
- **Primary Leadership Strategy**: One of Relative Strength Leadership, Relative Strength Momentum Continuation, Sector Leadership Alignment, Strong RS + Trend Alignment owning a decision.
- **Supporting Evidence**: Secondary confirmations that adjust confidence but do not own the decision.
- **Validation Result**: Pass/fail outcomes for regime, liquidity, risk, portfolio, leadership quality, and policy checks.
- **Market Context**: Regime, breadth, sector leadership, and related shared inputs consumed before stock-level strategy evaluation.
- **Relative Strength Features**: Stock-vs-market RS, stock-vs-sector RS, multi-timeframe RS, RS persistence/slope, leadership ranking features (consumed/derived via shared services, not private market-data stacks).
- **Lab Comparison Record**: Paired or multi-engine outcomes for the same symbol/scan.
- **Engine Decision Record**: Durable row for one RE-002 Recommendation Decision Object.
- **Engine Run Diagnostics**: Success/failure, duration, counts by RecommendationState for RE-002.
- **Experiment Record**: Long-lived governance artefact linking RE-002 decisions/paper/metrics to experiment lifecycle (register → activate → execute → pause/complete → compare → history); one active RE-002 experiment at a time for MVP attribution.
- **Experiment / Promotion Record**: Governance artefact for future promotion review (not auto-promote).
- **Paper Trade Provenance**: Link from paper ticket/position to RE-002 decision and experiment identity.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With RE-002 in `LAB_SHADOW` (or `PAPER_LINKED`) mode, production BUY/WATCH/REJECT labels and scanner shortlist membership match a disabled-RE-002 control on the same market snapshot for 100% of symbols in verification runs.
- **SC-002**: For every successfully completed RE-002 evaluation, operators can identify EngineID, primary strategy, RecommendationState, confidence, and at least one RS/leadership evidence rationale (or explicit reject reason for eligibility/RS failures) from the symbol/analysis detail surface without engineering database access.
- **SC-011**: For a completed lab run with N shortlisted evaluation-set symbols and RE-002 enabled, the system persists exactly N RE-002 Decision Objects (one per symbol), including REJECT objects for weak-RS and other eligibility failures — zero silent omissions.
- **SC-003**: Production path success MUST NOT decline due to RE-002 (engineering gate: fail-open isolation tests; RE-002 timeout/exception never fails production). Operational soak target after enablement: ≥95% of RE-002 evaluation attempts complete without RE-002-attributable production path failure (target: zero RE-002-caused production failures).
- **SC-004**: Operators can open the Recommendation Lab comparison view for a completed scan and review production vs RE-002 states for shortlisted symbols in under 2 minutes.
- **SC-005**: Paper tickets created from RE-002 decisions retain RE-002 provenance such that post-trade review can attribute ≥ 100% of those tickets to RE-002 (no silent untagged tickets).
- **SC-006**: On a controlled shared fixture set, bear-regime RE-002 BUY count MUST be ≤ 50% of bull-regime RE-002 BUY count for equivalent stock technical quality.
- **SC-007**: When RE-002 is toggled OFF, zero new RE-002 Decision Objects are created on subsequent scans.
- **SC-008**: Existing scanner, paper desk, analytics, and dashboard primary workflows remain usable without mandatory RE-002 UI steps (no forced lab gate for retail scanner use).
- **SC-009**: Baseline Recommendation Engine outputs on the same control fixture remain bitwise/behaviorally unchanged with RE-002 enabled vs disabled (beyond optional non-authoritative lab payload fields).
- **SC-010**: Experiment listing and report surfaces can identify RE-002 experiment identity and link to decision/metric history for at least one completed evaluation window.
- **SC-012**: For a rolling operational window with RE-002 enabled, operators can view RE-002 decision counts by state and run success/failure without engineering DB access; when RS scores exist on BUY decisions, a basic average-RS-of-BUYs aggregate is available. Full Doc 04 leadership report suite is not required for this criterion.

---

## Assumptions

- RE-002 Documents 01–04 plus REDS v1.0 are the business authority for philosophy, strategy orchestration, states, validation layers, and inheritance rules.
- RE-002 Document 05 (Deployment, Operations & Evolution) is not yet published; operational integration uses existing application patterns (feature flags, scheduler, logging, experiment framework) as technical source of truth.
- Exact RS calculation formulas, ranking algorithm mathematics, and lookback parameters are **not** frozen in Docs 01–04; implementation planning may adopt conservative, documented defaults using existing Relative Strength / sector RS services without inventing a parallel market-data stack. Parameter tightening later must not require architectural redesign.
- The existing production composite recommendation engine (Baseline) remains the production shortlist authority until a separate, explicit promotion decision.
- “Recommendation Lab” is the multi-engine evaluation surface. MVP UI: RE-002 section on symbol/analysis detail **plus** Lab comparison view extended for RE-002 (multi-engine capable).
- REDS Shared Core Services map onto existing modules; greenfield rewrites of those services are out of scope.
- Bull / Sideways / Bear for RE-002 orchestration maps from existing market regime / market permission outputs via a documented mapping table (assumption until Doc 05 freezes exact ops labels).
- Default entry stage is `LAB_SHADOW` when enabling (settings default remains `OFF` until ops enables); not production `ACTIVE`.
- Canonical stages: `OFF` | `LAB_SHADOW` | `PAPER_LINKED` (`ACTIVE` reserved/out of scope).
- Feature permission key is exactly `recommendation_lab`.
- Advisory-only constraint remains: no live order routing.
- LLM reasoning remains explainability assist only for RE-002 labels (consistent with platform “no live LLM decisions” constraint).
- **MVP persistence**: RE-002 Decision Objects and production-comparison metadata use the first-class multi-engine decisions store pattern; production `analysis_history.recommendation` remains production-only.
- **MVP evaluation set**: Production shortlist / full-analysis symbols only — same shortlist as production analysis; not full universe.
- **Missing market context**: REJECT with explicit reason code; never BUY; never assume a default regime.
- **Weak RS / eligibility fail (clarified)**: Always Decision Object REJECT with explicit reason for every shortlisted evaluation-set symbol; never silent skip.
- **Paper trade guidance**: RE-002 plan when complete → else production trade_plans; provenance always RE-002 when originated from lab decision.
- **Paper independence model (clarified)**: Same user paper account; independence = mandatory provenance tags + filterable RE-002 trade/analytics set. No separate RE-002 paper portfolio/sub-account in MVP.
- **Paper generation (clarified)**: Operator-initiated prefill only; no auto paper orders in MVP even under `PAPER_LINKED`.
- **Portfolio snapshot**: Requesting user paper/risk when available; else fail-closed for BUY with `portfolio_context_unavailable`.
- **scan_run_id**: Maps to existing completed-scan / latest-scan identity family.
- **Experiment ownership**: RE-002 executes as an Experiment inside Recommendation Lab; experiment framework/governance services are reused, not redesigned.
- **Experiment binding (clarified)**: One long-lived RE-002 experiment receives all scan decision and paper provenance attribution until pause/complete; no per-scan auto experiments.
- RE-001 (if present) remains independent; this feature does not modify RE-001 business rules.
- Minimum paper-trading duration for promotion readiness (3 months continuous per Doc 04) is a **business promotion gate**, not a blocker for MVP lab integration completion.
- Doc 04 “all recommendations paper-traded” is a **promotion/process coverage expectation**, not MVP automatic order placement (clarified: operator-initiated only).
- **Leadership analytics MVP (clarified)**: decision/run health + RS evidence on decisions + basic aggregates when RS available; full Doc 04 leadership report suite deferred from MVP DoD.

---

# Integration Specification (Brownfield)

The following sections define the complete implementation specification requested for planning and task generation. They describe **what must be implemented** against the current application, not greenfield redesign and not how to implement it.

---

## 1. Executive Summary

### Purpose

Integrate **RE-002 – Relative Strength Momentum Engine** into the existing Trading Application as a **new Recommendation Engine** that executes as an **Experiment** inside the **Recommendation Lab**, producing standardized BUY / WATCH / REJECT Recommendation Decision Objects focused on relative-strength leadership and momentum persistence.

### Business Value

| Value | Description |
| ----- | ----------- |
| Leadership focus | Pure relative-strength / leadership philosophy vs multi-factor composite Baseline noise |
| Fair comparison | Same shortlist, shared decision object, independent experiment metrics vs Baseline and other REs |
| Capital preservation | Regime-adaptive participation and portfolio/risk gates before BUY |
| Explainability | Primary strategy ownership, RS evidence, and validation trails for human review |
| Evolution | Second concrete multi-engine Lab member without redesigning the application |

### Expected Outcome

- RE-002 runs as an **additional** lab/experiment engine on scan/analysis pathways.
- Operators can explain, compare, paper-trade, and experiment-evaluate RE-002 decisions independently.
- Production scanner shortlists, dashboards, and Baseline Recommendation Engine remain unchanged until explicit promotion.
- The platform’s multi-engine registration and experiment pattern is reused/extended so RE-003+ can follow without redesign.

---

## 2. Business Context

### Why RE-002 exists

The Trading Lab defines REDS and a multi-engine roadmap (RE-001 → RE-007). **RE-001** focuses on trend continuation. **RE-002** focuses on a distinct philosophy: **market leaders tend to continue leading**, ranking by relative strength and leadership quality rather than simple absolute price-trend continuation.

RE-002 exists to answer:

> Which stocks are currently demonstrating the strongest and most persistent relative strength leadership under present market conditions?

### Problems it solves

- Composite Baseline mixes many factors; operators cannot isolate leadership quality.
- Need for philosophy-pure leadership recommendations under REDS governance.
- Need for fair experiment comparison using shared shortlist inputs and standardized Decision Objects.
- Need for regime-adaptive participation that preserves capital in weak markets while capturing leaders in strong markets.

### How it differs from the Baseline Engine

| Dimension | Baseline / Production Engine | RE-002 |
| --------- | ---------------------------- | ------ |
| Role | Production shortlist authority | Lab/experiment engine only (MVP) |
| Philosophy | Multi-factor composite scoring | Relative strength leadership & momentum persistence |
| Primary drivers | Technical, backtest, fundamental, news weights | RS ranking, leadership, sector leadership alignment |
| Output ownership | Scanner BUY/WATCH lists, dashboards | Independent Decision Objects + experiment artefacts |
| Paper / analytics | Production paper flows | Independently attributed RE-002 experiment ownership |
| Change surface | Must remain untouched | New additive engine + experiment registration |

### Business objectives

1. Identify strongest relative-strength leaders on the shared shortlist.
2. Participate more in Bull markets; be highly selective in Sideways/Bear.
3. Produce explainable, deterministic leadership recommendations.
4. Support paper trading and fair multi-engine comparison.
5. Preserve capital; profit alone is not success.
6. Enable promotion review only after validation lifecycle completion (not auto-promote).

---

## 3. Scope

### In Scope

- RE-002 engine registration, versioning, and stage control.
- Experiment registration and lifecycle linkage for RE-002 inside Recommendation Lab / Experiment Framework.
- Lab/shadow execution path integrated with existing analysis orchestration (shortlist / full-analysis symbols only — same shortlist as production).
- REDS Decision Object emission for RE-002 with RS-related evidence.
- Strategy orchestration for four primary leadership families + supporting + validation layers (business rules from Docs 01–02).
- Shared service consumption mapping (SCS → existing modules).
- Persistence of lab decisions and production comparison records.
- Operator-visible comparison and explanation (symbol detail RE-002 section + Lab comparison multi-engine rows).
- Paper-trade provenance and independent RE-002 attribution.
- Analytics counters and experiment metrics for RE-002 health and leadership quality (where measurable).
- Feature flags / stage configuration.
- Regression protection for production recommendation path, Baseline engine, RE-001 (if present), scanner, paper, analytics.
- Documentation of RS pre-filter and regime participation behaviour.

### Out of Scope

- Replacing or redesigning the Baseline / production composite recommendation engine.
- Modifying Scanner shortlist ownership, stage-stopping, or matched-symbol semantics.
- Auto-promotion of RE-002 to production shortlist authority.
- Live broker execution.
- RE-003…RE-007 implementation (only ensure architecture does not block them).
- Mean reversion / event / gap / news-primary / earnings / short / pure intraday / pure breakout-without-RS engines.
- Exact RS formula invention beyond mapping to existing Relative Strength services (parameter research is separate).
- Full Strategy Library product UI beyond what RE-002 needs to name/select strategies.
- Full multi-engine marketplace console redesign (extend existing Lab comparison pattern).
- New REDS architecture layers (REDS locked).
- Rewriting market data, scanner vectorization, or paper market engine.
- Publishing RE-002 Document 05 (external authoring); this spec only consumes available docs.
- Freezing numerical promotion thresholds (owned by EEF policy per Doc 04).

### Future Scope

- RE-002 Document 05 operational freeze (deployment runbooks, exact ops thresholds).
- Expanded evaluation universe beyond production shortlist.
- `ACTIVE` production stage after formal promotion.
- Adaptive evidence weighting refinements (parameter evolution without pipeline redesign).
- Deeper leadership persistence analytics productization and full Doc 04 leadership report suite (deferred from MVP).
- Cross-engine adaptive strategy portfolio (future).

### Must Not Change

- Production BUY/WATCH/REJECT classification ownership for scanner shortlists (until future promotion feature).
- Baseline Recommendation Engine scoring thresholds and gate semantics.
- Existing score thresholds and production gate semantics.
- Auth session model, advisory disclaimer, long-only constraint.
- Paper fill/replay engine behaviour unrelated to provenance metadata.
- REDS Decision Object field set (must not invent alternate state machines).
- Scanner output generation and shortlist membership rules in lab modes.

### Must Reuse

- Market data / candle infrastructure.
- Technical analysis indicators and scores.
- Screener shortlist generation (as shared input only).
- News/events, fundamentals (as shared context only; not RE-002 primary philosophy).
- Sector RS / breadth / regime services.
- Backtest and walk-forward infrastructure.
- Paper trading, portfolio/risk settings.
- Recommendation Lab multi-engine decision persistence pattern.
- Experiment / governance framework.
- Analytics, logging, audit, feature permissions, configuration, caching, scheduler locks.
- Shadow/experiment isolation patterns for non-production evaluation.

---

## 4. Current System Analysis

### Existing Recommendation Flow

Production path (as implemented):

1. Universe prioritization and screener stages.
2. Market data load.
3. Technical analysis bulk scoring.
4. Parallel news, fundamentals, backtest agents.
5. Sector RS / market permission challenger paths.
6. RecommendationAgent → reasoning assist + RecommendationService composite build.
7. Final gate / score classification → production FinalRecommendation.
8. Persist AnalysisHistory.
9. Rank and expose BUY/WATCH shortlists via analysis/scanner APIs and frontend.

### Recommendation Lab

- Multi-engine evaluation surface for non-production engines.
- Decision Object persistence and comparison against production.
- Symbol-detail engine sections and compact Lab comparison views.
- Feature permission `recommendation_lab`.

### Experiment Framework

- Governance experiment services (start/pause/resume/complete/list/show/metric/report/promote/kill).
- Experiment metrics logging and audit trails.
- Lifecycle intended for research → lab → paper → EEF → promotion review.

### Scanner

- Scan execution with locks, multi-universe stages, shortlist top-N, full analysis, latest-scan persistence.
- Production shortlist is the shared evaluation set for lab engines in MVP.

### Paper Trading

- Paper accounts, orders, positions, market engine fills, analytics.
- Prefill from recommendation context with provenance support (engine identity).

### Analytics

- Engine health, daily analytics, experiment metrics, optional per-engine segmentation.

### Recommendation Pipeline Integration Point for RE-002

| Layer | Integration posture |
| ----- | ------------------- |
| After production recommendation is resolved per symbol | Run RE-002 in isolated envelope (lab/experiment), fail-open for production |
| Shared inputs | Consume already-fetched candles, technical results, regime/breadth/sector RS, portfolio/risk snapshots — **same shortlist** as production |
| Persistence | First-class multi-engine decisions store for RE-002 Decision Objects + comparison metadata — never overwrite production recommendation field |
| Experiment | Register/attribute RE-002 runs under Experiment Framework |
| UI | Symbol detail RE-002 section + Lab comparison multi-engine rows; retail scanner remains production-driven |
| Paper / EEF | Downstream consumers of Decision Objects via orchestrator/lab APIs with independent provenance |
| Scheduler | Piggyback enabled lab evaluation on existing scan jobs |

RE-002 does **not** replace Baseline `RecommendationService` scoring as the production engine in this feature.

---

## 5. Functional Requirements

(See also mandatory FR-001–FR-034 above. This section restates capability groups for implementability review.)

### Engine Registration

- Register EngineID `RE-002`, display name “Relative Strength Momentum Engine”, version, stage, enabled flag.
- Coexist with Baseline and other lab engines (e.g., RE-001).

### Experiment Registration

- Create/activate RE-002 experiment records in Experiment Framework.
- Link decisions, paper trades, and metrics to experiment identity.
- Support pause/resume/complete/history without deleting historical artefacts.

### Recommendation Generation

- Evaluate shortlist symbols using RE-002 orchestration when enabled.
- Produce complete Decision Objects with RS evidence.

### Recommendation Decision

- States limited to BUY / WATCH / REJECT.
- Single primary strategy ownership for BUY/WATCH.
- Validation may only downgrade/reject.

### Recommendation Explanation

- Human-readable and machine-readable explanation focused on leadership/RS rationale.
- Trace: primary, supporting, rejected strategies, validations, regime.

### Experiment Execution

- Enabled stages run evaluation + persistence on scan/analysis path.
- Failures isolated from production success.

### Experiment Comparison

- Compare RE-002 vs production (and other engines) by symbol and by scan.
- Expose mismatch counts and metric comparisons via Lab/analytics/experiment reports.

### Recommendation Persistence & History

- Persist every Decision Object with engine, version, scan identity, timestamps.
- Retain history for audit, experiment review, and replay.

### Analytics

- Per-engine decision counts by state, run success/failure; basic RS aggregates when available.
- Independent RE-002 slices that do not corrupt Baseline aggregates.
- Full Doc 04 leadership report suite deferred from MVP DoD.

### Paper Trading Integration

- Prefill/order provenance from RE-002 decisions.
- Independent attribution of RE-002-originated paper activity.

---

## 6. Non-Functional Requirements

| Area | Requirement |
| ---- | ----------- |
| **Performance** | RE-002 evaluation of shortlist symbols must complete within an isolation timeout budget; production scan success must not wait unboundedly on RE-002. Designed for end-of-day batch-style scan participation. |
| **Scalability** | Architecture must support multiple lab engines evaluating the same shortlist without redesign. |
| **Determinism** | Same inputs + version + configuration → same RecommendationState and core decision fields. |
| **Explainability** | Every decision includes strategy ownership, RS evidence, validation outcomes, and final rationale. |
| **Maintainability** | Engine module is bounded; no forked copies of shared services. |
| **Auditability** | Decision logs replayable; experiment history retained; nothing discarded for experiments. |
| **Extensibility** | Registration/persistence/Lab patterns reusable for RE-003+. |
| **Reliability** | Fail-open to production; prefer capital preservation (WATCH/REJECT) under ambiguity. |
| **Security** | Lab surfaces require authentication + `recommendation_lab` permission; stage controls admin-appropriate; no unauthenticated access. |

---

## 7. Business Rules

1. **RE-002 never modifies Scanner output** (shortlist membership, stage results, matched lists, production candidate ownership).
2. **RE-002 analyses the same shortlist** as production full-analysis for that run (MVP).
3. **RE-002 generates independent recommendations** (own Decision Objects; does not overwrite Baseline labels).
4. **RE-002 owns independent paper trades** via mandatory provenance on the **same user paper account** (filterable RE-002 set); does not create a separate RE-002 portfolio and does not rewrite Baseline paper portfolio authority.
5. **RE-002 owns independent analytics** (EngineID/experiment segmentation over shared stores; Baseline aggregates remain valid).
6. **RE-002 never changes the Baseline Engine** (scoring, gates, trade plans for production path).
7. **Market before stock**: regime/context before stock-level leadership evaluation.
8. **Relative strength before absolute price** as primary decision emphasis.
9. **Portfolio before trade**: portfolio/risk validation can reject strong leaders.
10. **Evidence before opinion**: no subjective or LLM-owned labels.
11. **One primary strategy** owns each BUY/WATCH recommendation.
12. **Supporting strategies never independently BUY**.
13. **Validation never creates BUY**.
14. **Missing/unusable market regime → REJECT** with explicit reason; never default regime; never BUY.
15. **Weak RS stocks rejected early** via RS pre-filter, always as persisted REJECT Decision Objects with explicit reason codes for evaluation-set symbols (never silent skip).
16. **Long-only swing, NIFTY500, advisory-only**.
17. **Profit alone is not success**; leadership quality and capital preservation matter.
18. **Promotion is not automatic**.
19. **No bypass** of shared REDS filters/services.
20. **Multi-engine coexistence**: RE-002 must not clobber RE-001 or Baseline artefacts.

---

## 8. Integration Requirements

### Scanner

- Consume production shortlist / full-analysis set only.
- Never write scanner shortlist or stage-stop decisions.
- Respect scan locks.

### Recommendation Orchestrator

- Invoke RE-002 after production recommendation resolution when enabled.
- Collect RE-002 Decision Objects for persistence and optional response payload.
- Engines never communicate directly with production shortlist writers.

### Experiment Manager

- Register RE-002 engine/experiment identity.
- Track lifecycle state and metadata (version, stage, window).

### Experiment Runner

- Attribute run outputs (decisions, metrics) to RE-002 experiment.
- Support pause/complete without data loss of historical runs.

### Paper Trading

- Accept RE-002 Decision Objects / provenance on prefill and journal metadata.
- Risk/position lifecycle stays in existing paper trading services.
- Independent interpretation of RE-002-originated trades for experiment review.

### Analytics

- Segment health and metrics by EngineID = RE-002.
- Preserve existing production aggregates.
- MVP: decision counts by state, run success/failure, optional mismatch vs production, basic average RS of BUYs when RS available.
- Deferred: full Doc 04 leadership report suite.

### Dashboard

- Retail scanner dashboard remains production recommendations.
- Symbol detail shows RE-002 decision, strategy, RS evidence when present.
- Lab comparison provides scan-level multi-engine tables including RE-002.
- Clear experimental/lab labeling to avoid operator confusion.

### Scheduler

- Existing scan-related jobs may invoke lab evaluation when flags enabled.
- No new mandatory cron that places live trades.
- RE-002 failures must not fail scheduled production scan job outcome.

### Logging

- Structured logs for RE-002 context, pre-filter, strategies, validations, ranking path, confidence, errors.
- Deterministic and replayable decision audit trail.

### Configuration

- Master enable, stage, version, persist, compare, timeout, UI enable settings for RE-002.
- Defaults safe: disabled/OFF until operators enable.

### Recommendation History

- Historical Decision Objects queryable by engine, symbol, scan, time, state.
- Experiment history retains metrics and decisions.

---

## 9. Data Requirements

### Inputs

- Symbol, mode (swing), OHLCV, technical results.
- Market regime / permission, breadth, sector RS/leadership.
- Stock relative strength features (via shared RS services).
- Liquidity and quality flags.
- Portfolio / risk snapshot (paper or configured risk policy).
- Strategy eligibility metadata for leadership families.
- Production recommendation snapshot (for comparison only; not required as RE-002 logic input).
- Experiment identity / stage / version configuration.

### Outputs

- REDS Recommendation Decision Object (EngineID = RE-002).
- Optional comparison record vs production (and other engines).
- Run diagnostics (success/failure, duration, state counts).
- Experiment metric observations.
- Optional paper prefill payload with provenance.

### Shared Inputs

- Same shortlist/full-analysis symbols and already-assembled shared context used by production analysis for the scan.

### Recommendation Decision Object

Must include REDS §9 fields (FR-004). Evidence MUST include RS-related elements (rank/score/persistence/sector RS as available). RecommendationState limited to BUY/WATCH/REJECT.

### Experiment Metadata

- Experiment ID, engine ID, engine version, stage, status, time window, decision/metric links, operator notes.

### Recommendation Metadata

- scan_run_id, symbol, timestamps, primary strategy, supporting/rejected strategies, validation results, confidence components, reason codes.

### Required Persistence

- First-class multi-engine decisions store for RE-002 Decision Objects + comparison metadata.
- Experiment lifecycle and metrics stores (reuse existing governance patterns).
- Paper provenance linkage for RE-002-originated tickets.
- Production recommendation fields remain production-only.

---

## 10. User Experience Requirements

### What users should see

| Surface | Requirement |
| ------- | ----------- |
| **Recommendation List** | Production lists remain production-driven; optional lab indicators non-breaking |
| **Recommendation Detail** | RE-002 section: state, confidence, primary strategy, RS evidence, explanation, vs production |
| **Experiment Dashboard** | RE-002 experiment status, stage, recent run health |
| **Experiment Comparison** | Side-by-side production vs RE-002 (and other engines) for scan/symbol |
| **Experiment Analytics** | Decision counts, optional leadership metrics, regime breakdowns when available |
| **Paper Portfolio** | Same paper account; RE-002-originated tickets/positions show provenance and are filterable; Baseline-attributed views remain valid |
| **Recommendation History** | Filterable history of RE-002 decisions by scan/symbol/time/state |

### UX constraints

- Lab/experiment content clearly labeled experimental.
- No forced RE-002 steps in retail scanner primary workflow.
- Feature-gated by `recommendation_lab` for Admin + Trader.
- Navigation must not remove Markets / Scanner / Paper / Performance primary items.

---

## 11. Recommendation Behaviour

### BUY

Emitted only when all hold:

- Passed Bull Stock + Relative Strength pre-filter.
- At least one primary leadership strategy qualifies.
- Supporting evidence sufficient.
- Validation passes (regime, liquidity, risk, portfolio, leadership quality).
- Risk and portfolio policies approve.
- Market context present and usable.

### WATCH

Emitted when leadership interest exists but confirmation, regime selectivity, confidence, or soft validation is insufficient for BUY; or when fail-closed policies require downgrade.

### REJECT

Emitted when:

- Missing/unusable market context.
- Failed Bull Stock or weak RS pre-filter (**always as a persisted Decision Object** with explicit reason code for every evaluation-set symbol — never silent skip).
- No primary strategy qualifies.
- Hard validation fails.
- Portfolio/risk context unavailable when required for BUY (fail-closed path).
- Engine prefers capital preservation under conflicting/insufficient evidence.
- Missing RS features or insufficient history for evaluation-set symbols (explicit reason; never silent skip).

### Confidence

Computed from relative strength strength, leadership quality, supporting evidence, regime alignment, and validation results (Doc 03). Confidence must not override hard validation failures into BUY.

### Evidence

Must include RS-related evidence (rank/score/persistence/sector alignment as available), supporting confirmations, and validation outcomes.

### Explanation

Human- and machine-readable rationale focused on why the stock is (or is not) a leader.

### Validation

Validation layer can only reject or downgrade; never create BUY. Includes Leadership Quality Validation specific to RE-002.

### Decision Lifecycle

1. Context load  
2. Eligibility (Bull Stock + RS pre-filter) — on fail: build REJECT Decision Object with reason → jump to persist  
3. Strategy activation by regime  
4. Feature generation (RS focused)  
5. Primary evaluation  
6. Supporting evidence  
7. Validation  
8. Rank by RS quality + conflict resolve  
9. Confidence  
10. Decision Builder → BUY/WATCH/REJECT  
11. Explanation  
12. Persist Decision Object + experiment attribution (required for **every** evaluation-set symbol evaluated, including early REJECT)  

---

## 12. Experiment Behaviour

### Registration

- RE-002 registered as engine and as **one long-lived experiment subject** with version and configuration snapshot reference.
- MVP does not auto-spawn a new experiment identity per scan or per calendar day.

### Activation

- Stage transitions to `LAB_SHADOW` or `PAPER_LINKED` with master enable true, with the long-lived experiment in an active state for attribution.
- Activation does not grant production shortlist authority.

### Execution

- On each eligible scan/analysis run, evaluate shortlist symbols, persist decisions, record diagnostics and metrics.
- Every new Decision Object and RE-002-originated paper provenance links to the **same active long-lived experiment** until pause/complete.

### Completion

- Operators can pause or complete the long-lived experiment; history and reports are retained.
- After complete, a new long-lived experiment may be registered for a subsequent validation window (manual ops), not auto per scan.
- Completion does not auto-promote.

### Storage

- Decisions, metrics, logs, and comparison artefacts retained; nothing discarded.

### Comparison

- Compare RE-002 vs Baseline production and other lab engines on shared symbols/scans and standardized metrics under the experiment identity.

### History

- Full historical query of experiment decisions and reports for audit and research repository intent, keyed by the long-lived experiment id(s) over time.

---

## 13. Paper Trading Behaviour

### Trade Generation

- **MVP**: paper tickets are **operator-initiated only** (prefill from RE-002 decision → operator confirms/create). System MUST NOT auto-place paper orders for RE-002 BUY/WATCH/REJECT.
- Both `LAB_SHADOW` and `PAPER_LINKED` may expose prefill from decisions; `PAPER_LINKED` marks intentional paper-validation ops mode without auto-execution.
- Trade guidance: complete RE-002 guidance if present; else production trade_plans for same symbol/scan.
- Tickets are created on the **same user paper account** used for other paper activity (no RE-002-only account required in MVP).
- Doc 04 requirement that recommendations be paper-traded is a **promotion/process coverage gate** (operators ensure sufficient paper history), not an MVP auto-trade feature.

### Position Ownership

- Positions created from RE-002 remain attributable to RE-002 engine + experiment via **mandatory provenance tags**.
- Baseline-originated paper positions remain Baseline-attributable on the same account.
- “Independent ownership” means **filterable attribution and analytics**, not a separate portfolio ledger product in MVP.

### Experiment Isolation

- RE-002 paper activity must be separable for experiment review by EngineID / experiment_id filters.
- Enabling RE-002 must not create parallel accounts or silently reassign unrelated positions’ provenance.

### Portfolio Behaviour

- Portfolio validation reads shared portfolio/risk capabilities (same account snapshot).
- Fail-closed when portfolio context unavailable for BUY.
- Paper risk/fill engines unchanged in semantics.

### Trade History

- Every RE-002-originated paper trade retains: decision id, engine, version, strategy, RS evidence snapshot, confidence, regime, explanation link, experiment id, outcomes.
- Operators MUST be able to list only RE-002-attributed trades for experiment review without a separate portfolio product.

---

## 14. Analytics Behaviour

### Experiment Metrics

- **MVP required**: run success/failure, duration, symbols evaluated, error counts, stage, version.

### Recommendation Metrics

- **MVP required**: counts of BUY / WATCH / REJECT; optional mismatch vs production; reason-code distributions when recorded.
- **MVP basic leadership aggregate when RS available**: average RS of BUY decisions in the window.

### Trade Metrics

- For RE-002-attributed paper trades: P&L, holding period, win rate, expectancy (as platform supports). Not a blocker for lab decision MVP if paper volume is low.

### Portfolio Metrics

- Heat, concurrent positions, sector concentration, correlation of recommended stocks (per Doc 04 intent, via existing analytics capabilities where available). Full suite may be incremental.

### Performance Metrics

- Return, drawdown, risk-adjusted measures for experiment windows (paper/backtest as available). Full performance suite supports promotion gates; not all required for first lab enablement DoD.

### Comparison Metrics

- **MVP**: production vs RE-002 state comparison; optional mismatch rate; RS evidence visible on decisions.
- **Deferred from MVP DoD**: full Doc 04 leadership suite (market outperformance time-series, leadership persistence after recommendation, % remaining in top RS ranks dashboards, complete regime-wise leadership quality product reports).
- Engine ranking inputs for EEF comparison remain the long-term target using identical metric definitions across engines.

---

## 15. Validation Requirements

### Business Validation

- Long-only, swing, NIFTY500, advisory-only.
- States ∈ {BUY, WATCH, REJECT}.
- Primary strategy required for BUY/WATCH.
- Portfolio-before-trade and risk-before-recommend enforced.
- Regime participation rules applied.
- Missing/unusable market regime → REJECT with explicit reason code.
- Excluded philosophies not implemented as primary paths.
- RS pre-filter rejects weak RS early via persisted REJECT Decision Objects (no silent skips for evaluation-set symbols).

### Recommendation Validation

- Decision Object completeness (FR-004).
- RS-related evidence present for human review when evaluation proceeds past pre-filter.
- Conflict resolution yields single primary strategy.
- Confidence consistent with supporting/validation outcomes (no BUY with failed hard validation).

### Experiment Validation

- Experiment registration/activation/execution attribution correctness.
- Pause/OFF stops new side effects.
- History retained after completion.

### Integration Validation

- Production shortlist invariance tests (SC-001, SC-009).
- Flag OFF ⇒ no RE-002 artefacts (SC-007).
- Paper provenance tests (SC-005).
- Analytics segmentation tests.
- Permission tests for lab surfaces.
- Missing market regime ⇒ REJECT tests (FR-025).
- Evaluation-set tests: non-shortlisted symbols not evaluated.
- Multi-engine coexistence with RE-001/Baseline.

### Regression Validation

- Baseline recommendation classification suite remains green.
- Scanner, paper, analytics, dashboard primary workflows remain green.
- RE-001 (if present) behaviour unchanged by RE-002 enablement.

---

## 16. Acceptance Criteria

1. RE-002 can be enabled in `LAB_SHADOW` and produces Decision Objects for shortlisted symbols without changing production shortlists or Baseline outputs.
2. Decision Objects include all mandatory REDS fields, EngineID = RE-002, valid states only, and RS-related evidence.
3. Missing/unusable market regime yields REJECT with explicit reason code (never BUY; no default regime).
4. Missing portfolio context yields no BUY with reason `portfolio_context_unavailable`.
5. Paper prefill uses RE-002 trade guidance when complete else production trade_plans with RE-002 provenance; paper orders are operator-initiated only (no auto-orders under `PAPER_LINKED`).
6. Strategy orchestration records primary vs supporting vs validation outcomes for leadership families.
7. Bull/Sideways/Bear participation differences are demonstrable in verification scenarios (SC-006).
8. Operators can compare production vs RE-002 for the same symbol/scan via symbol detail + Lab view.
9. Analytics can report RE-002 decision counts by state for a rolling window, independently of Baseline.
10. Experiment surfaces can register, show, and report the long-lived RE-002 experiment history with decisions attributed to that experiment across scans.
11. Feature flag OFF removes RE-002 execution side effects.
12. Existing regression suite for production recommendation classification remains green.
13. No live order placement path introduced.
14. Failures in RE-002 are logged and countable without aborting production scan success.
15. RE-002 evaluates only shortlist/full-analysis symbols in MVP, and every such symbol receives a Decision Object (including REJECT for weak-RS / eligibility failures — no silent skips).
16. RE-002 does not modify Scanner output or Baseline engine behaviour.
17. Multi-engine coexistence: RE-002 Decision Objects do not overwrite RE-001 or production fields.

---

## 17. Constraints

### Technical Constraints

- Brownfield only: reuse existing services; no parallel market-data/paper/analytics stacks.
- Additive persistence only; no destructive schema renames of production fields.
- Prefer zero new third-party dependencies.
- Isolation timeout and fail-open production path required.
- Deterministic decisions; no live LLM-owned labels.

### Business Constraints

- Advisory-only; no live broker orders.
- Long-only swing; NIFTY500; Indian equity cash.
- Promotion not automatic; minimum paper duration and EEF criteria are promotion gates (Doc 04).
- Profit alone insufficient for success.

### Architecture Constraints

- REDS v1.0 locked: no new pipeline stages, Decision Object shape, inheritance model, or shared service layer without REDS v2.0.
- Recommendation Engines do not write production shortlists directly.
- Orchestrator owns collection, paper, backtest, EEF, promotion forwarding.
- Multi-engine Lab pattern must remain extensible for RE-003+.

---

## 18. Assumptions

(See mandatory Assumptions section above; repeated key points for planning readiness.)

- Docs 01–04 + REDS are business authority; Doc 05 absent → ops defaults from platform patterns.
- Exact RS formulas/parameters not frozen → conservative documented defaults via existing RS services.
- Baseline remains production authority.
- Same shortlist evaluation set for MVP.
- Stages `OFF` | `LAB_SHADOW` | `PAPER_LINKED`.
- Feature permission `recommendation_lab` for Admin + Trader.
- First-class multi-engine decisions store is system of record for lab Decision Objects.
- RE-001 remains independent and unmodified by this feature’s business scope.

---

## 19. Risks

| Severity | Risk | Mitigation |
| -------- | ---- | ---------- |
| **Critical** | RE-002 accidentally overwrites production shortlist labels | Hard separation of stores/fields; lab mode cannot write production authority; invariance tests |
| **Critical** | Production scan fails due to RE-002 exception/timeout | Isolated try/except + timeout; fail-open for production |
| **Critical** | Baseline engine behaviour changes | Explicit non-touch constraint + regression suite |
| **High** | Operator confuses lab BUY with production BUY | Clear UI labeling; production cards unchanged; provenance badges |
| **High** | Incomplete Decision Object breaks EEF/compare | Schema validation before persist; reject incomplete objects |
| **High** | Regime mapping wrong → overtrading in bear | Explicit mapping table + bear-regime verification (SC-006); missing regime → REJECT |
| **High** | RS service gaps produce silent bad leaders | Fail closed to REJECT/WATCH when RS features missing; never invent ranks |
| **Medium** | Performance regression on scan latency | Shortlist-only MVP; isolation timeout; fail-open production |
| **Medium** | Experiment attribution leakage across engines | Enforce EngineID + experiment_id on decisions/paper/metrics |
| **Medium** | Multi-engine UI clutter | Feature-gate Lab surfaces; optional columns; non-breaking production UX |
| **Low** | Doc 05 absent causes ops ambiguity | Assumptions + conservative defaults; refine without redesign |
| **Low** | Parameter churn for RS lookbacks | Config/versioned parameters; deterministic version stamps |

---

## 20. Future Expansion

This specification MUST support the following without requiring redesign of REDS pipeline, Decision Object, orchestrator boundaries, or Lab multi-engine storage model:

- **RE-003, RE-004, … RE-007**: additional engines registered with EngineID, independent Decision Objects, same shortlist consumption pattern, Lab comparison rows, experiment attribution.
- **Adaptive Strategy**: regime-based activation tables versioned per engine without changing pipeline stages.
- **Adaptive Evidence Weighting**: confidence/supporting weight policies as engine-local configuration, not new architecture layers.
- **Future Recommendation Engines**: shared engine evaluate contract, shared persistence, shared paper provenance, shared analytics segmentation by EngineID.
- **Future ACTIVE production stage**: reserved; requires separate promotion feature and governance approval.

---

## 21. Definition of Ready

Everything required before implementation begins:

1. Agreement that Baseline / production engine remains shortlist authority for this feature (no silent promotion).
2. RE-002 Docs 01–04 + REDS v1.0 accepted as business authority.
3. Documented mapping: existing regime labels → Bull/Sideways/Bear for orchestration (missing regime → REJECT).
4. Confirmation of multi-engine decisions store pattern as system of record for RE-002 Decision Objects.
5. Confirmation of Lab UI approach: symbol detail RE-002 section + Lab comparison multi-engine support.
6. MVP evaluation set confirmed: production shortlist / full-analysis only.
7. Feature flag names and default stage confirmed (`re002_*` settings; default OFF).
8. Paper provenance field strategy confirmed: same user paper account + mandatory RE-002 provenance tags (no separate RE-002 portfolio in MVP).
9. Timeout/isolation budget for RE-002 per symbol/scan agreed.
10. Test fixtures for bull/sideways/bear leadership scenarios prepared or planned.
11. Analytics contract for per-engine counts (and basic RS aggregate when available) identified; full leadership suite deferred from MVP.
12. Experiment Framework registration fields for RE-002 identified (reuse existing experiment model); long-lived single experiment attribution model confirmed.
13. Access control confirmed: Admin + Trader with `recommendation_lab`.
14. Baseline production recommendation regression suite identified and runnable.
15. RE-001 coexistence regression (if RE-001 deployed) identified.
16. Scan locking behaviour understood (no second full unlocked universe scan for RE-002).
17. Conservative defaults accepted for unfrozen RS parameters pending research/Doc 05.
18. Spec quality checklist complete and passing.

---

## 22. Definition of Done

RE-002 implementation is considered complete when:

1. All P1 user stories pass acceptance scenarios.
2. Functional requirements FR-001–FR-034 are satisfied or explicitly deferred with stakeholder sign-off (none deferred for P1 isolation/decision object/compare/experiment attribution).
3. Success criteria SC-001–SC-012 verified with recorded evidence (full Doc 04 leadership report suite not required for MVP DoD).
4. Production invariance demonstrated (RE-002 on vs off) and Baseline invariance demonstrated.
5. Lab Decision Objects persisted and reviewable via symbol detail + Lab comparison.
6. Experiment registration/execution/history path verified for RE-002.
7. Paper provenance path verified with independent RE-002 attribution.
8. Analytics can segment RE-002 decision health independently (counts by state, run success/failure; basic RS aggregate when available).
9. Feature flags control execution (OFF stops side effects).
10. Regression suites for recommendation, scanner, paper, analytics, and (if present) RE-001 remain green.
11. No production redesign residual (no replaced composite engine, no scanner rewrite, no live trading).
12. Spec quality checklist complete; feature ready for `/speckit-plan` and subsequent tasks.
13. Operators can answer: “What did RE-002 decide, why (RS/leadership evidence), how does it differ from production, and which experiment owns it?” without DB consoles.
14. Governance path for future promotion is documented as **manual / future feature**, not auto-enabled.
15. Architecture remains open for RE-003+ without redesign.

---

## Traceability

| Source | Consumption in this spec |
| ------ | ------------------------ |
| REDS v1.0 | Pipeline, Decision Object, SCS, states, orchestrator boundaries, validation lifecycle, EEF |
| RE-002 Doc 01 | Mission, philosophy, scope, invariants, regime participation, success criteria, boundaries |
| RE-002 Doc 02 | Strategy layers, orchestration, activation, priority, conflict resolution, adaptive behaviour, explainability |
| RE-002 Doc 03 | Module responsibilities, data flow, SCS interfaces, Decision Object population, logging, errors, determinism |
| RE-002 Doc 04 | Validation layers, paper duration intent, mandatory metrics, EEF integration, promotion/rejection criteria, experiment tracking |
| Existing app | Integration points, reuse inventory, regression surface, brownfield constraints, Lab/experiment patterns |
| User integration brief | Experiment-first operating model; independent paper/analytics; same shortlist; never modify Scanner/Baseline |

---

## Notes for Planning (`/speckit-plan`)

- Prefer adapter + RE-002 engine module over invasive rewrite of Baseline `RecommendationService`.
- Mirror proven lab/shadow isolation patterns used for multi-engine evaluation.
- Keep retail UX production-first; lab clearly labeled.
- Treat unfrozen RS parameters as conservative defaults to be tightened later without changing architecture.
- Reuse multi-engine decisions store and Lab comparison patterns; extend for EngineID RE-002 rather than inventing a second lab stack.
- Experiment Framework integration is additive attribution, not a new governance product.
- Document 05 absence must not block MVP; ops runbooks can follow.
- Do not generate implementation code or tasks in the specify phase (already complete here).
