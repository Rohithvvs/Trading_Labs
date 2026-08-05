# RE-002 Relative Strength Momentum Engine

Lab/experiment recommendation engine focused on **relative strength leadership**.

## Scope

- EngineID: `RE-002`
- Stages: `OFF` | `LAB_SHADOW` | `PAPER_LINKED` (defaults OFF)
- Evaluates **production shortlist / full-analysis symbols only**
- Emits a Decision Object for **every** evaluation-set symbol (including REJECT for weak/missing RS)
- Persists to multi-engine table `recommendation_engine_decisions` with `engine_id=RE-002`
- **Requires** long-lived experiment attribution via `RE002_EXPERIMENT_ID` for any side effects (FR-028)

## Non-goals

- Does **not** change Baseline/production recommendation labels or scanner shortlists
- Does **not** modify RE-001 business rules
- Does **not** auto-create paper orders (operator-initiated prefill only)
- Does **not** invent RS ranks when inputs are missing
- Trade guidance on Decision Objects falls back to production `trade_plans` when RE-002 does not produce a native plan (FR-015 intentional MVP)
- Full Doc 04 leadership report suite is **deferred** from MVP DoD

## Isolation

- Fail-open relative to production (timeout/exception never fails the scan)
- Feature flags: `RE002_ENABLED`, `RE002_STAGE`, `RE002_TIMEOUT_MS`, etc.
- Side-effect gate (single): enabled + stage ∈ {LAB_SHADOW, PAPER_LINKED} + experiment configured + not paused
- Lab UI visibility: feature permission `recommendation_lab` (Admin + Trader) + `RE002_UI_ENABLED`
- RE-001 and RE-002 share one portfolio snapshot and run in parallel on the analysis path

## Ops: env aliases

| Env | Meaning | Default |
| --- | ------- | ------- |
| `RE002_ENABLED` | Master switch | false |
| `RE002_STAGE` | `OFF` \| `LAB_SHADOW` \| `PAPER_LINKED` | OFF |
| `RE002_VERSION` | Engine version stamped on decisions | 1.0 |
| `RE002_TIMEOUT_MS` | Per-symbol isolation timeout | 3000 |
| `RE002_PERSIST_DECISIONS` | Write decisions table | true |
| `RE002_UI_ENABLED` | Lab API UI kill-switch | true |
| `RE002_EXPERIMENT_ID` | Long-lived experiment id (optional; default `re002-long-lived` when lab stage active) | none |
| `RE002_EXPERIMENT_PAUSED` | Pause new side effects while keeping id | false |

## Ops: long-lived experiment

1. Set `RE002_ENABLED=true` and `RE002_STAGE=LAB_SHADOW`.
2. Optionally set `RE002_EXPERIMENT_ID=<uuid-or-id>` for governance linkage; if omitted, decisions use stable default id `re002-long-lived`.
3. When the experiment is paused (`RE002_EXPERIMENT_PAUSED=true`) or stage is OFF, **no new** RE-002 side effects are produced.
4. Historical decisions remain readable via lab APIs (`/re002/history`, comparison, symbol latest).
5. **After enabling**, run a **new** Scanner/full-analysis scan — old RE-001-only `scan_run_id`s will not retroactively gain RE-002 rows.

## Paper provenance (FR-029)

Operator-initiated paper prefill/create stores structured tags on paper orders and positions:

- `source_engine_id` (e.g. `RE-002`)
- `source_engine_version`
- `source_recommendation_id`
- `experiment_id`

These are filterable independently of free-text notes. No auto-orders under `PAPER_LINKED`.

## Observability

- Structured logs under logger `app.re002` (start / complete / error / timeout)
- DB-backed health: `GET /api/v1/recommendation-lab/re002/health` (SQL aggregates)
- In-process runtime counters are **non-authoritative** (`runtime_counters_authoritative=false`) — multi-worker/restart lose them

## Performance notes

- Per-symbol isolation timeout (`RE002_TIMEOUT_MS`, default 3s)
- Shortlist-only evaluation set
- Lab engines parallelized; portfolio snapshot loaded once

## SCS mapping (high level)

| REDS SCS | Reuse |
| -------- | ----- |
| Regime | market permission / FEAT-004 |
| RS / Sector | sector_rs_service / overlay |
| TA | technical_analysis_service |
| Portfolio | paper account snapshot |
