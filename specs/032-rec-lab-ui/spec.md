# Feature Specification: Recommendation Lab UI Modernization

**Feature Branch**: `032-rec-lab-ui`  
**Created**: 2026-08-05  
**Status**: Draft  
**Input**: User description: "Transform Recommendation Lab into a professional institutional Trading Research Dashboard (UI modernization only). Reference design RE.png. Preserve all existing Recommendation Lab capabilities (engine status, cohort selection, multi-engine comparison, recommendation results). No backend, algorithm, schema, scanner, authentication, or experiment-logic changes."

## Clarifications

### Session 2026-08-05

- Q: How should users open symbol-level recommendation detail? → A: Side drawer only (row click or “view” opens drawer; no in-table expand).
- Q: After auto-selecting a multi-symbol cohort on first open, should comparison load automatically? → A: Yes — auto-select best multi-symbol cohort and auto-load comparison on first open.
- Q: Should future engine columns (RE-003 / Adaptive Strategy / Adaptive Weighting) show as empty placeholders now? → A: No — hide future-engine columns until the engine is registered in the product.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open Institutional Research Dashboard (Priority: P1)

A research or trading user with access to Recommendation Lab opens the Recommendation Lab surface and immediately sees a professional research dashboard: page identity, live context (date / market posture where available), KPI summary cards, engine health cards, and clear entry points to compare engines and act—without first decoding a developer-style status dump.

**Why this priority**: First impression and orientation determine whether the Lab is treated as production research tooling or as an internal debug page. This story delivers the core modernization value alone.

**Independent Test**: Open Recommendation Lab with existing engine registration data available; verify header, KPI row, engine cards, and primary layout render using existing data; no new backend required.

**Acceptance Scenarios**:

1. **Given** an authorized user opens Recommendation Lab, **When** the page finishes initial load, **Then** they see the title “Recommendation Lab”, a research-oriented subtitle, current date, and market/research status indicators when data is available.
2. **Given** Production, RE-001, and/or RE-002 engines are registered in the existing system, **When** the dashboard loads, **Then** each registered engine appears as a status card (not only plain text lines) showing name, version, and operational status.
3. **Given** recent lab scan cohorts exist, **When** the dashboard loads, **Then** KPI cards summarize experiment/engine counts, recommendation volume, and signal mix using existing data (or explicit empty/unavailable states when a metric is not available).
4. **Given** multi-symbol recent cohorts exist and the user has not yet interacted, **When** they land on the page, **Then** the Lab auto-selects a preferred multi-decision cohort and auto-loads comparison so research data appears without an extra click; engine health remains visible even if load yields empty rows.

---

### User Story 2 - Compare Engines on a Selected Cohort (Priority: P1)

A user selects a recent scan cohort (or pastes a scan run identifier), loads multi-engine comparison, and reviews Production vs RE-001 vs RE-002 in a modern comparison table that supports filtering and scanning; future engines appear as columns only once registered. Symbol detail opens in a side drawer only—preserving today’s comparison semantics.

**Why this priority**: Comparison is the core research job of Recommendation Lab; modernization must not reduce capability.

**Independent Test**: Select a multi-symbol cohort, load comparison, verify table shows production and lab engine columns, filter works, empty and error states match existing business messages.

**Acceptance Scenarios**:

1. **Given** recent multi-symbol scan cohorts are listed on first open, **When** the dashboard initializes, **Then** a preferred multi-decision cohort is auto-selected and comparison is auto-loaded so the table populates with one row per symbol and columns for Production, RE-001, and RE-002 (when data exists); the user may still change cohort and reload.
2. **Given** a comparison is loaded, **When** the user filters by symbol or signal/state text, **Then** only matching rows remain visible and the remaining-count is clear.
3. **Given** a comparison is loaded, **When** the user selects a symbol row or chooses “view details”, **Then** a side drawer opens (not an in-table expand) showing available confidence, strategy, production score, mismatch flags, and experiment identity without leaving the Lab.
4. **Given** a scan has no lab rows, **When** load completes, **Then** the user sees the same class of informative empty guidance as today (no lab decisions for this scan / need active lab engines), presented in dashboard-appropriate messaging—not a blank broken page.

---

### User Story 3 - Decide Using Analytics Widgets (Priority: P2)

A user uses charts and analytics widgets (signal mix, strategy mix, confidence comparison, recommendation trend, top recommendations) derived only from already-available Lab data to decide which engine and which symbols deserve attention.

**Why this priority**: Shifts the Lab from “raw table” to “decision support” while remaining testable with existing data.

**Independent Test**: With a loaded comparison and/or health summary, verify donuts/bars/lists reflect counts and rankings consistent with the comparison and health data; missing metrics show unavailable—not fabricated performance.

**Acceptance Scenarios**:

1. **Given** comparison rows are loaded, **When** analytics widgets render, **Then** signal distribution (BUY / WATCH / REJECT or equivalent lab states) and strategy distribution match the loaded set.
2. **Given** multi-engine confidence values exist, **When** the confidence comparison widget renders, **Then** each engine with data shows an average confidence the user can compare at a glance.
3. **Given** recent scan cohorts exist, **When** the trend widget renders, **Then** it shows recommendation/decision volume over recent cohorts (or empty state if none).
4. **Given** a metric (e.g., market regime %, paper PnL) is not available from existing Lab data, **When** the corresponding KPI or chart would appear, **Then** the UI shows an honest empty/unavailable state rather than inventing values.

---

### User Story 4 - Act Quickly From the Lab (Priority: P2)

A user launches common next steps from Quick Actions without hunting through global navigation: run/continue scanner workflow, reload comparison, open paper trading, open portfolio analytics, and export the currently loaded comparison for offline review.

**Why this priority**: Completes the research loop from insight to action while reusing existing destinations and flows.

**Independent Test**: Click each quick action; verify navigation or export uses existing capabilities and does not require new backend endpoints.

**Acceptance Scenarios**:

1. **Given** the dashboard is visible, **When** the user chooses “Run Scanner” (or equivalent), **Then** they are taken to the existing scanner entry point.
2. **Given** a scan run is selected, **When** the user chooses “Compare Engines”, **Then** the existing comparison load behavior runs for that selection.
3. **Given** comparison rows are loaded, **When** the user exports results, **Then** they receive a downloadable artifact of the currently loaded comparison set.
4. **Given** the user chooses Paper Trading or Portfolio Analytics, **When** navigation completes, **Then** existing destinations open with no change to paper-trading or analytics business rules.

---

### User Story 5 - Monitor Activity and Alerts (Priority: P3)

A user scans Recent Activity and Alerts panels for engine inactivity, high-confidence signals on the loaded set, health summaries, and mismatch warnings—without leaving the dashboard.

**Why this priority**: Improves situational awareness; lower than core comparison but part of the institutional reference experience.

**Independent Test**: With inactive engines and/or mismatch rows, verify alert/activity copy surfaces those conditions; with quiet data, verify non-alarming empty or calm status messaging.

**Acceptance Scenarios**:

1. **Given** RE-001 or RE-002 is inactive, **When** the dashboard loads, **Then** an alert or status item clearly states inactivity and guidance to enable lab shadow mode (same operational intent as today’s messaging).
2. **Given** loaded comparison contains production-vs-lab mismatches, **When** activity/alerts render, **Then** at least one item highlights mismatch presence.
3. **Given** RE-002 health summary is available, **When** activity/alerts render, **Then** BUY/WATCH/REJECT health counts can appear as informational items.

---

### Edge Cases

- No engine registrations available (permission failure or service unavailable): show error banner; do not crash layout; allow retry of load paths when registration recovers.
- Only one engine registered: KPI and engine cards adapt; comparison columns for missing engines show empty cells.
- Only single-symbol “scans” exist (not multi-symbol cohorts): keep current guidance that user should pick a multi-symbol cohort or run a full scanner.
- Very large comparison sets (hundreds of symbols): table remains usable via filter, pagination or progressive disclosure; page remains responsive enough for research work.
- Partial engine failure (one comparison source fails): show rows/columns for successful source; do not discard the other engine’s data.
- Future engines (RE-003, Adaptive Strategy, Adaptive Weighting): comparison columns remain hidden until the engine is registered; no empty placeholder columns in the current product.
- Theme/light mode: dark institutional theme is primary; light theme remains readable if the product already supports theme toggle.
- Unauthorized user: existing access control continues to block the Lab; no new permission model.

## Requirements *(mandatory)*

### Functional Requirements

#### Scope & Non-Goals

- **FR-001**: The product MUST modernize only the Recommendation Lab **presentation and information architecture**. Existing Recommendation Lab capabilities MUST remain available.
- **FR-002**: The product MUST NOT change recommendation algorithms, scanner behavior, authentication, experiment business rules, data storage schemas, or server-side contracts as part of this feature.
- **FR-003**: The product MUST NOT invent metrics (PnL, win rate, market regime percentages, latency, success rate) when underlying Lab data does not provide them; such fields MUST use empty, “unavailable”, or omitted states.

#### Header & Context

- **FR-004**: Users MUST see a primary page title “Recommendation Lab” and a subtitle communicating AI-powered / multi-engine / experiment-driven research.
- **FR-005**: Users MUST see current date context on the dashboard header region.
- **FR-006**: Users MUST see research/market status context when available (e.g., research mode, market open/closed if already available elsewhere); when market data is not available, the UI MUST still show a coherent research status (e.g., Research / Lab).
- **FR-007**: Users MUST see indicators of the current active experiment or selected scan cohort when one is selected (scan identifier and decision count when known).
- **FR-008**: Header region MUST provide access to primary quick actions (at least: load/compare, navigate to scanner, navigate to paper trading).

#### KPI Cards

- **FR-009**: The dashboard MUST present a responsive KPI strip including, at minimum when data allows: total registered lab engines/experiments, count of active engines, total recommendations (from recent cohorts and/or loaded set—definition fixed in Assumptions), BUY count, WATCH count, REJECT count, average confidence (from loaded comparison when present), best-performing engine (by highest average confidence when present), current active experiment/cohort identity, and market-regime field only if available from existing Lab data (else unavailable).
- **FR-010**: Each KPI card MUST show a large primary value, supporting label, optional secondary line, and optional trend/context line without requiring interaction.
- **FR-011**: KPI cards MUST update when registration, health, recent cohorts, or loaded comparison data changes.

#### Engine Status Cards

- **FR-012**: Each registered engine (Production baseline context when shown, RE-001, RE-002, and future engines when registered) MUST be representable as a card showing: engine name, version, status (active/inactive/draft/production-linked), experiment identity when present, and health summary fields when available.
- **FR-013**: Engine cards MUST surface BUY / WATCH / REJECT (or equivalent) counts when health or loaded comparison provides them; missing fields show unavailable.
- **FR-014**: Engine cards MUST surface average confidence when derivable from loaded comparison; otherwise unavailable.
- **FR-015**: Success rate, latency, and last scan MUST appear only when existing Lab data supports them; otherwise show unavailable—not zeros that imply measurement.
- **FR-016**: Existing registration status text (enabled, stage, experiment id) MUST remain accessible for operators (may appear on cards and/or a secondary detail strip) so operational diagnostics are not lost.

#### Cohort Selection & Load

- **FR-017**: Users MUST be able to select a recent scan cohort from a list populated by existing Lab recent-scan data.
- **FR-018**: Users MUST be able to enter or paste a scan run identifier manually.
- **FR-019**: Users MUST be able to load multi-engine comparison for the selected identifier using the same load semantics as today (both lab engines attempted; partial success allowed).
- **FR-020**: On first open of Recommendation Lab in a session, when recent multi-decision (multi-symbol) cohorts exist, the product MUST auto-select a preferred multi-decision cohort **and automatically load** multi-engine comparison for that cohort without requiring a separate Load click. Users MUST still be able to change selection and re-load manually. Single-symbol-only catalogs keep current guidance and MUST NOT force a misleading auto-load success narrative.
- **FR-020a**: Auto-load MUST use the same partial-success semantics as manual load (one engine may fail without discarding the other). Loading indicators MUST appear on the comparison region during auto-load.
- **FR-021**: Informative empty and inactive-engine guidance MUST remain available with equal operational meaning to current messages (including after auto-load completes with no rows).

#### Recommendation Comparison Table

- **FR-022**: The comparison table MUST show symbols with Production recommendation/score, RE-001 state/confidence, RE-002 state/confidence/strategy/experiment id when present.
- **FR-023**: Comparison columns MUST include only engines that are currently registered (or Production baseline when shown). Future engines (RE-003, Adaptive Strategy, Adaptive Weighting) MUST NOT appear as empty placeholder columns. When a new engine becomes registered, its column(s) MAY appear without a schema change for this UI feature; no backend work is required by this feature alone to “reserve” empty columns.
- **FR-024**: Columns SHOULD include recommendation/signal, confidence, score, strategy, evidence count, market regime, and actions **when data exists**; missing attributes show empty cells rather than blocking the row.
- **FR-025**: Users MUST be able to filter the comparison set by text (symbol, state, strategy, experiment id).
- **FR-026**: Users MUST be able to page or otherwise progressive-display long result sets.
- **FR-027**: Comparison table rows MUST remain non-expanding (flat). Selecting a row or choosing a “view details” action MUST open symbol detail exclusively via the side drawer (see FR-029). In-table expand/collapse is out of scope.
- **FR-028**: Status signals MUST use consistent visual badges (BUY green, WATCH amber, SELL/REJECT red, inactive/draft amber, active/production green).

#### Recommendation Details Drawer / Panel

- **FR-029**: Selecting a symbol (row click / keyboard activation) or a “view details” control MUST open a side panel/drawer without full page navigation. This is the sole detail pattern for comparison and top-recommendations lists.
- **FR-030**: The drawer MUST display all available decision fields for that symbol from currently loaded Lab data (engine states, confidences, production score/action, strategies, experiment id, mismatch flags, recommendation identifiers).
- **FR-031**: The drawer MUST show unavailable placeholders for technical analysis, indicators, evidence, risk, and narrative “reason” sections when those are not present in current Lab comparison payloads—without inventing content.
- **FR-032**: Users MUST be able to close the drawer via explicit control and Escape key (keyboard accessible).

#### Charts & Analytics Widgets

- **FR-033**: The dashboard MUST include visual widgets for: signal distribution (BUY/WATCH/REJECT or lab-state equivalent), strategy distribution, engine confidence comparison, recommendation/decision volume trend across recent cohorts, and top recommendations list ranked by confidence (or production score when confidence missing).
- **FR-034**: Optional widgets for market regime distribution, sector distribution, and daily recommendation count MUST render only when corresponding data is available; otherwise omit or show empty state.
- **FR-035**: Charts MUST be readable on dark institutional theme and support empty states.

#### Experiment Analytics Summary

- **FR-036**: An analytics summary region MUST show totals for symbols in the loaded comparison, counts of accepted/rejected/pending-like states mapped from available lab states, average score, average confidence, and execution/runtime fields only if available—else unavailable.

#### Recent Activity & Alerts

- **FR-037**: Recent Activity MUST list time-contextual events derived from existing Lab data (recent cohorts, registration status changes as static “live” items, mismatch detection on load).
- **FR-038**: Alerts MUST highlight operational risks (inactive engines, errors, high-confidence signals on loaded set, health summaries) without requiring a new alerting backend.

#### Quick Actions

- **FR-039**: Quick Actions MUST include at least: Run/open Scanner, Compare/reload engines, Open Paper Trading, Open Portfolio/Performance Analytics, Export loaded comparison.
- **FR-040**: Quick Actions MUST reuse existing navigation destinations and existing load/export behaviors.

#### Layout, Navigation, Accessibility, Responsiveness

- **FR-041**: Layout MUST follow institutional dashboard hierarchy similar to the reference design philosophy: header → KPI strip → primary grid (overview/comparison + analytics side panel) → charts → bottom activity/actions/alerts → footer status.
- **FR-042**: Global application navigation remains the product shell navigation; Recommendation Lab MUST work within the existing shell without requiring a second global app rewrite. Optional in-page section anchors (Overview, Comparison, Analytics) MAY be provided.
- **FR-043**: UI MUST be keyboard navigable for primary controls (cohort select, load, filter, pagination, drawer close, quick actions) with visible focus indicators.
- **FR-044**: Interactive elements MUST have accessible names (labels/ARIA) for screen-reader users for primary controls and status badges where meaning is not text-visible.
- **FR-045**: Layout MUST adapt for desktop, laptop, tablet, and mobile widths: KPIs wrap; side analytics stack under main; tables scroll horizontally when needed; touch targets remain usable.
- **FR-046**: Loading states MUST use skeleton or non-blocking placeholders so the page structure appears before all secondary widgets finish.

#### Preservation & Safety

- **FR-047**: Existing automation hooks and test identifiers for Recommendation Lab page, scan selection, scan id input, registration status, and RE-002 health MUST continue to identify the same capabilities (may remain on modernized elements).
- **FR-048**: Feature access control for Recommendation Lab MUST remain enforced as today.
- **FR-049**: Export MUST only include currently loaded comparison data the user already can see (no expanded secret fields).

### Key Entities *(presentation model — not new storage)*

- **Lab Engine Registration**: Identity of a recommendation engine available in the Lab (name, version, stage, enabled/active, optional experiment identity).
- **Scan Cohort**: A scan run used as a comparison unit (identifier, decision count, recency timestamp when available).
- **Comparison Row**: Per-symbol multi-engine decision snapshot (production action/score; RE-001 state/confidence/strategy; RE-002 state/confidence/strategy/experiment; mismatch flags; recommendation identifiers).
- **Health Summary**: Time-windowed signal counts for an engine when provided by existing Lab health capabilities (BUY/WATCH/REJECT/total and optional secondary stats).
- **KPI Snapshot**: Aggregated display values derived from registrations, cohorts, health, and loaded comparison.
- **Dashboard Widget**: Chart or list presentation unit (signal donut, strategy donut, confidence bars, trend, top recommendations, activity, alerts).
- **Detail Drawer Context**: Selected symbol’s available decision attributes for deep inspection.
- **Quick Action**: Navigation or command entry that reuses existing product flows.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Authorized users can open Recommendation Lab and identify engine operational status (active vs inactive) within 10 seconds without reading raw registration prose alone.
- **SC-002**: On first open with multi-symbol lab cohorts available, comparison data for a preferred cohort appears without an extra Load click (auto-select + auto-load). Users can still change cohort and reload manually, with the same success/empty outcomes as today’s Lab when data exists or does not.
- **SC-003**: For a loaded comparison of at least 10 symbols, users can filter to a single symbol in under 5 seconds using on-page filter controls.
- **SC-004**: At least 90% of primary research tasks in moderated walkthroughs (check engine status, load comparison, find a high-confidence BUY, open paper trading) complete without facilitator assistance on first attempt.
- **SC-005**: Visual audit against the reference design philosophy scores “aligned” on layout hierarchy, card density, dark institutional palette, and widget variety (not pixel-perfect matching).
- **SC-006**: No previously available Recommendation Lab capability is removed: registration visibility, recent cohort selection, manual scan id entry, multi-engine comparison, inactive-engine guidance, and health summary visibility remain available.
- **SC-007**: On tablet-width viewports, users can complete cohort selection and comparison load without horizontal dead-ends (controls remain reachable; tables scroll within containers).
- **SC-008**: When metrics are unavailable, zero users in UAT report fabricated performance numbers (PnL/win rate) presented as real Lab results—unavailable states are used instead.
- **SC-009**: Existing automated checks that rely on Recommendation Lab page and control identifiers continue to locate those capabilities after modernization.
- **SC-010**: Research users rate the modernized Lab as “more professional / institutional” than the prior layout in at least 80% of feedback responses in a short internal survey (n ≥ 5).

## Assumptions

- Target users are authenticated Trading Labs users with Recommendation Lab feature access (researchers, operators, admins).
- Existing multi-engine Lab data sources already supply registration, recent scans, comparison rows, and RE-002 health; this feature only reshapes presentation and client-side aggregation for display.
- “Total Recommendations” defaults to the sum of decision counts across recent scan cohorts shown in the Lab, with secondary display of currently loaded comparison row count when a comparison is loaded.
- “Best Performing Engine” defaults to the engine with highest average confidence on the **currently loaded** comparison; if no comparison is loaded, fall back to active engine presence / health BUY volume when available, else “unavailable”.
- Market regime, sector distribution, success rate, latency, paper PnL, and win rate are **out of fabricated scope**; they appear only if already present in existing Lab-facing data.
- Future engines (RE-003, Adaptive Strategy, Adaptive Weighting) do not appear as empty table placeholders; columns appear only after registration.
- Global application shell (sidebar, theme toggle, profile, notifications) remains owned by the existing application chrome; Lab modernization focuses on the Lab page content hierarchy inspired by the reference.
- Dark institutional theme is the primary visual target matching RE.png design philosophy.
- Export format may be structured data of the loaded comparison (e.g., JSON file) sufficient for offline review; pixel-perfect PDF report generation is out of scope unless already available.
- No new server-side experiment CRUD is required for this feature; “New Experiment” mapping defaults to starting/continuing research via Scanner when experiment-create UI does not already exist.
- Accessibility target is WCAG 2.1 AA for contrast of text/badges on dark theme and keyboard operation of primary controls.

## Dependencies

- Existing Recommendation Lab access control / feature gating.
- Existing Lab capabilities for engine registration visibility, recent scan listing, multi-engine comparison load, and optional health summary.
- Existing product destinations: Scanner, Paper Trading, Portfolio/Performance analytics.
- Existing design reference asset: `RE.png` (institutional dashboard visual language).
- Existing application shell for navigation and theming.

## Out of Scope

- Changes to recommendation generation, scoring, or engine algorithms.
- New backend services, database tables, or breaking API changes.
- Full multi-page Lab IA rewrite of the entire application (Markets, Scanner, Admin).
- Building real engine runtimes for RE-003 / Adaptive Strategy / Adaptive Weighting.
- Showing empty “future engine” comparison columns before those engines exist.
- Fabricating experiment PnL, win rate, or market regime analytics without data sources.
- Replacing authentication, paper trading, or scanner pipelines.
- Pixel-perfect recreation of every decorative element in the reference image.

---

## Presentation Specification *(product design — for SDD planning)*

### 1. Complete UI Specification Summary

Recommendation Lab becomes an **institutional research dashboard**: dense but scannable, dark-themed, card-based, analytics-forward. Users should perceive Bloomberg/console-grade research tooling while every prior Lab capability remains reachable in clearer locations.

### 2. Dashboard Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ HEADER: Title · Subtitle · Date · Market/Research status · Quick actions │
├──────────────────────────────────────────────────────────────────────────┤
│ ENGINE STRIP: Registration/health chips (operational fidelity)           │
├──────────────────────────────────────────────────────────────────────────┤
│ KPI ROW (responsive wrap): 6–10 metric cards                             │
├────────────────────────────────────┬─────────────────────────────────────┤
│ PRIMARY LEFT                       │ PRIMARY RIGHT                       │
│  · Engine Status Cards             │  · Signal distribution chart        │
│  · Experiments / Engines overview  │  · Strategy distribution chart      │
│  · Cohort controls + Load          │                                     │
│  · Comparison table (+ filter/page)│                                     │
├────────────────────────────────────┴─────────────────────────────────────┤
│ CHARTS ROW: Performance trend · Confidence compare · Top recommendations │
├───────────────┬──────────────┬────────────────┬──────────────────────────┤
│ Activity      │ Status chart │ Quick Actions  │ Alerts                   │
├──────────────────────────────────────────────────────────────────────────┤
│ FOOTER STATUS: platform readiness · engine health summary · lab version  │
└──────────────────────────────────────────────────────────────────────────┘
│ DETAIL DRAWER (overlay from right when symbol selected)                  │
```

### 3. Widget Specifications

| Widget | Purpose | Data source (existing Lab data only) | Empty behavior |
|--------|---------|--------------------------------------|----------------|
| KPI: Lab Engines | Count registered engines | Registrations | Show 0 / loading |
| KPI: Active Engines | Count active engines | Active/stage flags | Show 0 |
| KPI: Total Recommendations | Volume of lab decisions | Recent cohort decision counts | Show 0 + guidance |
| KPI: BUY/WATCH/REJECT | Signal mix | Health summary or loaded states | Unavailable if none |
| KPI: Avg Confidence | Quality signal | Loaded comparison confidences | “—” until load |
| KPI: Best Engine | Comparative winner | Max avg confidence | “—” until load |
| KPI: Active Experiment/Cohort | Context | Selected scan id + count | “None selected” |
| KPI: Market Regime | Regime context | Only if present in data | Unavailable |
| Engine Cards | Per-engine health | Registration + health + loaded avgs | Partial fields ok |
| Comparison Table | Multi-engine decisions | Loaded comparison merge | “No lab rows” |
| Detail Drawer | Deep inspect one symbol | Selected row fields | N/A sections empty |
| Signal Donut | Mix visualization | Health or loaded states | Empty chart message |
| Strategy Donut | Strategy mix | Strategy names on rows | Empty chart message |
| Confidence Bars | Engine quality compare | Avg confidences | Empty until load |
| Trend Chart | Cohort volume over time | Recent scans series | Empty until scans |
| Top Recommendations | Attention list | Ranked loaded rows | Empty until load |
| Activity | Situational timeline | Scans + status + mismatches | Calm empty |
| Alerts | Risks & highlights | Inactive engines, errors, mismatches, high-conf | Calm empty |
| Quick Actions | Next steps | Navigation + load + export | Always visible |
| Footer | Trust/status | Engine active flags | Always visible |

### 4. Component Hierarchy (logical presentation components)

```
RecommendationLabDashboard (page)
├── LabPageHeader
├── LabEngineStrip
├── LabKpiRow
│   └── LabMetricCard (×N)
├── LabMainGrid
│   ├── LabEngineCardsPanel
│   │   └── LabEngineCard (× engines)
│   ├── LabExperimentsOverview (optional table/list of engines)
│   ├── LabCohortControls
│   ├── LabComparisonTable
│   │   ├── LabStatusBadge
│   │   └── LabComparisonRow (flat; opens drawer)
│   └── LabSideAnalytics
│       ├── LabDonutChart (signals)
│       └── LabDonutChart (strategies)
├── LabChartsRow
│   ├── LabTrendChart
│   ├── LabConfidenceChart
│   └── LabTopRecommendationsTable (row opens drawer)
├── LabBottomRow
│   ├── LabActivityFeed
│   ├── LabStatusSummaryChart
│   ├── LabQuickActions
│   └── LabAlertsPanel
├── LabFooterStatus
└── LabDetailDrawer (sole symbol-detail surface)
```

Reuse existing product shell, badges/buttons patterns, and toast/navigation patterns where they already exist; introduce Lab-specific presentation components only where hierarchy requires them.

### 5. Page Wireframe (textual)

1. **Top**: Large title left; chips right (date, market/research).  
2. **Below title**: Compact engine pills with badges (ACTIVE/INACTIVE) retaining operational detail.  
3. **KPI strip**: 5–8 equal-height cards with icon tiles.  
4. **Main**: ~60–65% width comparison/engines; ~35–40% charts.  
5. **Mid**: Three-up charts/list.  
6. **Bottom**: Four-up activity/status/actions/alerts.  
7. **Drawer**: 360–420px right overlay, dimmed backdrop optional, sticky header with symbol + close.

### 6. UX Flow

```
Enter Lab
  → See status + KPIs
  → Auto-select preferred multi-symbol cohort (when available)
  → Auto-load comparison for that cohort (loading indicator on table/charts)
  → KPIs/charts update from loaded set
  → (Optional) Change cohort / paste scan id → Load again
  → Filter / page table
  → Open symbol detail drawer
  → Decide: export, paper trade, re-run scanner, compare again
```

Error path: banner at top; controls remain usable.  
Inactive engines path: amber alerts + registration detail remain visible.

### 7. Navigation Changes

- **In-app route**: remains Recommendation Lab entry under existing feature gate (label may stay “Rec Lab” in shell or expand to “Recommendation Lab” for clarity—either acceptable if test identifiers remain stable).
- **No mandatory new global nav items** for this feature.
- **Optional in-page anchors**: Overview · Comparison · Analytics (scroll), not new routes.
- Quick Actions map to existing routes/actions only.

### 8. Responsive Rules

| Breakpoint intent | Behavior |
|-------------------|----------|
| Ultra-wide / desktop | Full multi-column grids as in layout |
| Laptop | KPI wrap to 3–4 per row; main 2-column retained if space |
| Tablet | Main stacks (comparison then analytics); charts 2-column then 1 |
| Mobile | Single column; sticky load action near cohort controls; tables horizontal scroll; drawer becomes full-height sheet |

Minimum touch target ~40px for primary buttons. Reduce non-critical chrome before removing functionality.

### 9. Design Tokens (visual language aligned to RE.png)

#### Color (Dark Institutional Primary)

| Token | Value | Usage |
|-------|-------|-------|
| Background | `#0B1220` | Page canvas |
| Surface / Card | `#111827` | Cards, panels |
| Surface elevated | `#0F172A` | Table headers, nested |
| Border | `#1F2937` | Card and table borders |
| Text primary | `#F3F4F6` | Titles, values |
| Text muted | `#9CA3AF` | Labels |
| Text dim | `#6B7280` | Meta |
| Primary blue | `#2563EB` | Primary actions, accents |
| Success green | `#22C55E` | BUY, active, positive |
| Warning amber | `#FACC15` | WATCH, draft, caution |
| Danger red | `#EF4444` | SELL/REJECT, errors |
| Purple | `#7C3AED` | Secondary accent / engine variety |
| Cyan | `#06B6D4` | KPI accent variety |

#### Typography

| Role | Size | Weight |
|------|------|--------|
| Page title | ~32px (clamp ~26–32) | 750 |
| Section title | ~18–22px | 650 |
| Card value | ~22–28px | 750 |
| Body / table | ~13–14px | 400–500 |
| Labels / meta | ~12–13px | 500 |

Font stack: Inter, Segoe UI, system-ui, sans-serif.

#### Spacing & Shape

- Card padding: 14–16px  
- Grid gap: 12–16px  
- Page vertical rhythm: 16–20px between major bands  
- Radius: 12–14px cards; 999px badges/chips  
- Elevation: soft dark shadow under cards; hover lift 1–2px  

#### Motion

- Card hover lift + border accent  
- Fade-in page entrance  
- Chart draw/transition moderate (not distracting)  
- Skeleton shimmer for loading KPIs/tables  

#### Icons

Research metaphors: flask/beaker, chart, brain, trending, layers, target, activity, wallet, scale, history. Style: outline, 1.75 stroke, consistent 18–20px.

#### Badges

Pill shape; uppercase micro-labels; color-coded as above; high contrast text on tinted backgrounds.

#### Buttons

- Primary: solid blue, white text  
- Ghost: border + muted text  
- Icon buttons: 28–32px square, subtle hover fill  

#### Drawer

Right overlay; dark surface; sectioned content; sticky title bar; focus trap while open; Escape closes.

#### Tables

Sticky header; zebra optional; row hover highlight blue-tint; numeric tabular figures; horizontal scroll container.

#### Charts

Donut with legend percentages; bar for engine confidence; line for decision volume trend; tooltip legible on dark surfaces.

### 10. Migration Plan (presentation rollout)

| Phase | Outcome | Risk control |
|-------|---------|--------------|
| **M0 — Spec freeze** | This specification approved | No code yet |
| **M1 — Shell layout** | Header, KPI skeletons, grid structure on Lab page; existing load controls still work | Feature-flag or branch only |
| **M2 — Engine & comparison restyle** | Cards + modern table; preserve all load/filter/compare behaviors and identifiers | Visual QA + regression of comparison |
| **M3 — Analytics widgets** | Charts/lists from existing data only; empty states for missing metrics | Data honesty review |
| **M4 — Drawer + actions + activity** | Detail drawer, quick actions, alerts polish | Keyboard/a11y pass |
| **M5 — Responsive & polish** | Breakpoints, skeletons, motion, light-theme check | Device matrix |
| **M6 — Validation** | SC-001…SC-010, automated identifier checks, stakeholder sign-off vs RE.png philosophy | Go/no-go |

**Rollback**: Revert Lab page presentation branch; backend untouched.

**Training**: Short internal note: where status moved (cards), how to load comparison (same actions, clearer placement), how empty metrics work.

### UX Principles (from reference philosophy)

1. **Dashboard first, table second** — tables remain essential but sit inside a research narrative.  
2. **Honest analytics** — never fake institutional metrics.  
3. **Operational fidelity** — operators still see stage/enabled/experiment identity.  
4. **Density with hierarchy** — many widgets, clear priority order.  
5. **Actionable** — every insight near a next step (compare, scanner, paper, export).  
6. **Brownfield reuse** — existing data and destinations only.

### Traceability: Requested Sections → Requirements

| Requested section | Covered by |
|-------------------|------------|
| Header | FR-004…FR-008 |
| KPI Cards | FR-009…FR-011 |
| Engine Status Cards | FR-012…FR-016 |
| Recommendation Comparison | FR-017…FR-028 |
| Details Drawer | FR-029…FR-032 |
| Charts | FR-033…FR-035 |
| Experiment Analytics | FR-036 |
| Recent Activity | FR-037 |
| Quick Actions | FR-039…FR-040 |
| Alerts | FR-038 |
| Layout / responsive / a11y | FR-041…FR-046 |
| Preserve functionality | FR-001…FR-003, FR-047…FR-049, SC-006 |
