# Contract: RE-002 Recommendation Decision Object

**Feature**: `031-re002-rs-momentum`  
**Status**: Planning contract (not implementation)  
**Alignment**: REDS v1.0 §9 + spec FR-004 / FR-024 / FR-025 + clarify session 2026-08-04

---

## Purpose

Canonical output of RE-002 evaluation. All consumers (persistence, lab API, UI, paper provenance, analytics, experiment attribution) MUST accept this shape.

---

## Recommendation states

Allowed values only:

- `BUY`
- `WATCH`
- `REJECT`

No other states.

---

## Required fields

| Field | Type (logical) | Rules |
| ----- | -------------- | ----- |
| recommendation_id | string | Unique per evaluation |
| engine_id | string | Constant `RE-002` |
| engine_version | string | Non-empty (e.g. `1.0`) |
| experiment_id | string \| null | Required when long-lived experiment is active |
| market_regime | string | `Bull` \| `Sideways` \| `Bear` \| `UNKNOWN` |
| trading_objective | string | Non-empty |
| trading_style | string | Long-only swing intent |
| strategy_family | string \| null | Required when state is BUY or WATCH |
| strategy_name | string \| null | Required when state is BUY or WATCH; one of leadership families |
| recommendation_state | string | BUY \| WATCH \| REJECT |
| confidence_score | number | Finite |
| risk_profile | object \| string | Present |
| portfolio_decision | object \| string | Present |
| evidence | object | Structured; include RS-related fields when computable |
| explanation | object \| string | Human-readable leadership rationale |
| timestamp | datetime | UTC |
| reason_codes | string[] | Includes applicable codes (see below) |
| trade_guidance | object \| null | Optional entry/SL/target for paper prefill |
| scan_run_id | string \| null | Completed-scan identity when available |
| symbol | string | Evaluation symbol |
| production_action | string \| null | Comparison only |
| production_score | number \| null | Comparison only |
| evaluation_status | string | `success` \| `rejected_by_rules` \| `error` \| `timeout` |

---

## Primary strategy families (when BUY/WATCH)

Exactly one primary owner:

- Relative Strength Leadership
- Relative Strength Momentum Continuation
- Sector Leadership Alignment
- Strong RS + Trend Alignment

Supporting strategies never own the recommendation.

---

## Trade guidance (optional but preferred for BUY)

| Field | Type | Rules |
| ----- | ---- | ----- |
| entry_low / entry_high | number | > 0 and ordered when present |
| stop_loss | number | > 0 when present |
| target_1 | number | > 0 when present |
| risk_reward_ratio | number | optional |
| complete | boolean | true only when entry, SL, and target_1 usable |

**Paper prefill rule (FR-015)**: If `trade_guidance.complete` is true, paper prefill uses it; otherwise fall back to production `trade_plans` for the same symbol/scan. Provenance always identifies RE-002 when the operator originated from a lab decision.

**MVP paper generation**: Operator-initiated only — consumers MUST NOT auto-create paper orders from this object.

---

## Strategy trace (required under evidence or sibling object)

| Field | Description |
| ----- | ----------- |
| primary_strategy | Selected owner (or null on early eligibility REJECT) |
| supporting_strategies | Confirmations |
| rejected_strategies | List with reasons |
| validation_results | Regime, liquidity, risk, portfolio, leadership quality, policy, bull_stock_filter, rs_prefilter |

---

## Evidence RS fields (preferred when computable)

| Field | Notes |
| ----- | ----- |
| rs_vs_market | score/rank |
| rs_vs_sector | score/rank |
| multi_timeframe_rs | optional |
| rs_persistence | optional |
| leadership_rank | optional |
| eligibility | bull_stock_pass, rs_prefilter_pass |

Never invent RS ranks when inputs missing.

---

## Standard reason codes (non-exhaustive)

| Code | When |
| ---- | ---- |
| `missing_market_context` | Regime missing/unusable → REJECT, never BUY |
| `weak_relative_strength` | RS pre-filter fail → REJECT Decision Object |
| `failed_bull_stock_filter` | Bull stock eligibility fail → REJECT |
| `insufficient_history` | Not enough data for RS/eligibility → REJECT |
| `portfolio_context_unavailable` | No portfolio snapshot → no BUY |
| `leadership_quality_failed` | Leadership validation fail |
| `timeout` / `evaluation_error` | Isolation envelope outcomes |

---

## Invariants

1. Missing/unusable market regime ⇒ `recommendation_state = REJECT`, `market_regime = UNKNOWN`, reason `missing_market_context`.
2. Weak RS / eligibility failure for evaluation-set symbol ⇒ persisted REJECT Decision Object (never silent skip).
3. Hard validation failure ⇒ never BUY.
4. Exactly one primary strategy owns BUY/WATCH.
5. LLM must not solely determine `recommendation_state`.
6. `engine_id` is always `RE-002`.
7. When long-lived experiment is active, `experiment_id` is set for successful persistence paths.
