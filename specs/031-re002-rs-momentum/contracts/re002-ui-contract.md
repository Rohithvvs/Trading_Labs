# Contract: RE-002 UI / UX Surfaces

**Feature**: `031-re002-rs-momentum`  
**Status**: Planning contract (not implementation)  
**Alignment**: Spec §10 UX, FR-014, FR-022, SC-002, SC-004, SC-008 + clarify session

---

## Purpose

Define what operators must see and be able to do for RE-002 without prescribing React component trees or CSS.

---

## Visibility

| Audience | Access |
| -------- | ------ |
| Admin + Trader | Lab RE-002 surfaces when feature permission `recommendation_lab` is enabled and UI flag allows |
| Unauthenticated | No access |
| Retail scanner primary workflow | **Unchanged**; no forced lab steps (SC-008) |

All RE-002 content MUST be clearly labeled **Lab / Experimental** so it is not confused with production Baseline recommendations.

---

## Surfaces

### S1 — Symbol / analysis detail (required)

**Show when**: RE-002 Decision Object exists for symbol/scan (or explicit empty state when expected but missing).

**Must display**:
- EngineID RE-002 + version
- RecommendationState (BUY / WATCH / REJECT)
- Confidence
- Primary strategy name (when present)
- At least one RS/leadership evidence item **or** explicit reject reason code
- Comparison to production Baseline state when available
- Experiment identity (name/id) when attributed

**Must not**:
- Override production BUY/WATCH cards for the symbol’s production action
- Imply live order placement

### S2 — Recommendation Lab comparison (required)

**Show**: Scan-level table/list for a completed scan.

**Columns (logical)**:
- Symbol
- Production state
- RE-002 state (+ confidence/strategy optional)
- RE-001 state optional if present
- Mismatch indicator optional

**Performance expectation**: Operator can review shortlist production vs RE-002 in under 2 minutes (SC-004).

### S3 — Experiment dashboard (required for SC-010)

**Show**:
- Long-lived RE-002 experiment status (active/paused/completed)
- Stage/enablement summary
- Link/entry to recent decision counts or history

### S4 — Paper desk provenance (required when ticket originated from RE-002)

**Show on ticket/order**:
- Source engine RE-002
- Recommendation id
- Experiment id when present

**Behavior**:
- Prefill is operator-initiated from a decision
- Same paper account as other paper trades
- No automatic order creation banner implying auto-execution

### S5 — Analytics (MVP)

**Show**:
- Decision counts by state for RE-002 window
- Run success/failure
- Optional avg RS of BUYs when available

**Not required for MVP**: full Doc 04 leadership persistence/outperformance dashboards.

### S6 — Retail scanner dashboard (must not change meaning)

- BUY/WATCH summary cards remain **production Baseline–sourced**
- Optional subtle lab indicator only if non-breaking

---

## Empty / error / loading states

| State | UX requirement |
| ----- | -------------- |
| RE-002 OFF | No RE-002 sections that imply live evaluation; hide or show disabled empty state |
| Loading lab data | Non-blocking spinner/skeleton; production content remains usable |
| Missing decision for shortlist symbol when engine ON | Surface explicit gap/error (should be rare given SC-011) |
| REJECT with reason | Show reason code/text prominently |
| RE-002 timeout/error | Do not break production detail; show lab error badge if useful |

---

## Navigation

- Reuse feature-gated Recommendation Lab entry.
- Do not remove Markets / Scanner / Paper / Performance primary items.
- Do not force RE-002 into default retail path.

---

## Non-goals

- Full multi-engine marketplace console redesign.
- Pixel-perfect mockups.
- Separate RE-002 paper portfolio UI product.
