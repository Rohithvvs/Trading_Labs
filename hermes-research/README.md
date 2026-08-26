# HERMES

Research and validation system for reproducing TradingView Strategy Tester
behavior in the Trading Labs backtesting engines.

HERMES is **not** a trading engine. It does not place orders, mutate production
code, or replace Git as the source of history. It is the research /
orchestration layer that sits above the existing Python system.

---

## Why HERMES exists

Trading Labs already has scanners, paper trading, live-trading models, and more
than one backtest path. TradingView Strategy Tester remains the golden
reference for how a published Pine strategy actually filled, sized, and
accounted for trades.

Without a dedicated research layer it is easy to:

- match Net Profit while the trade list is wrong
- overfit the engine to one symbol
- confuse scanner-indicator Pine with Strategy Tester Pine
- change production execution without evidence or approval

HERMES exists so that every compatibility claim is backed by immutable
reference files, classified evidence, comparison artifacts, and an explicit
user decision.

---

## TradingView Golden Reference

Immutable evidence lives under:

```text
hermes-research/tradingview_reference/
```

Expected layout per strategy:

```text
hermes-research/
└── tradingview_reference/
    └── Strategy_001/
        ├── strategy.pine
        ├── strategy_report.xlsx
        ├── trades.csv
        └── test_config.yaml
```

These files are **GOLDEN REFERENCE DATA**.

- Do not edit, reformat, rename, overwrite, or convert them in place.
- Integrity hashes are stored in `state/reference_manifest.json`.
- A hash mismatch is `REFERENCE_CHANGED` and requires user confirmation.
- Missing files must be reported. Missing information must not be invented.

---

## System architecture

```text
                    USER
                      |
                      v
                  HERMES
                      |
                      v
                GLM-5.2
              OpenCode Go
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
       Research    Analysis    Planning
          |           |           |
          +-----------+-----------+
                      |
                      v
              Grok CLI / OpenCode
                      |
                      v
               Trading Engine
                      |
                      v
                  Backtest
                      |
                      v
                 Comparator
                      |
                      v
                    USER
```

### Role of the user

Final authority. Approves or rejects production backtesting-engine changes.
Remains in the loop after every comparison cycle.

### Role of HERMES

Research and orchestration: inspect evidence, classify confidence, find the
first meaningful divergence, write proposals, record iterations, and refuse
work that lacks evidence or approval.

### Role of GLM-5.2

Intended reasoning / LLM brain, reached through OpenCode Go. Used for
research, analysis, and planning — not for silent production edits.

### Role of Grok CLI / OpenCode CLI

Coding workers. They implement **approved** changes, add regression tests, and
keep Git history intact.

### Role of Python / the backtester

System under test. Trading Labs engines (including `BacktestService` and
strategy book replay such as `breakout52w`) produce candidate results that
HERMES will later compare to TradingView.

### Role of Git

History, review, and rollback. HERMES must not rewrite commits, force-push, or
discard unrelated user work.

---

## Research workflow

1. Read the golden reference (`strategy.pine`, `test_config.yaml`, trades,
   Strategy Tester report) without modifying it.
2. Prefer official TradingView documentation over folklore.
3. Inspect our engine. Do not change it in this step.
4. Record documented facts, experiments, inferences, and unknowns separately.
5. Stop if evidence is insufficient.

Research notes belong in:

```text
hermes-research/research/
  tradingview/   Pine, Strategy Tester, broker emulator
  execution/     signal vs order vs fill
  orders/        order types, delays, fills
  portfolio/     cash, equity, sizing, pyramiding
  data/          calendars, splits, symbols, timeframes
  metrics/       tester statistics definitions
```

---

## Comparison workflow

Configuration only in PART 1: `config/comparison.yaml`.

Later parts will compare:

- summary metrics (net profit, drawdown, trade count, …)
- trade-level rows (time, price, qty, PnL, commission, slippage)
- order-level events
- portfolio-level cash / equity / position
- **first meaningful divergence**, not only the final score

Never optimize solely for Net Profit.

---

## Approval workflow

1. HERMES writes a proposal under `proposals/`.
2. The proposal cites evidence classes and the first divergence.
3. The user approves, rejects, or asks for more research.
4. Only after approval may Grok CLI / OpenCode CLI touch production code.
5. Live trading changes are never auto-approved. Live broker orders are blocked.

See `config/permissions.yaml` and `config/agent.yaml`.

---

## Iteration workflow

```text
approved change → tests → backtest → compare
        |                               |
      MATCH                          MISMATCH
        |                               |
     validate                      research again
        |                               |
        +-------------- USER -----------+
```

Each loop is recorded under `iterations/` and `comparisons/`. Discrepancies
go in `discrepancies/`. Reports go in `reports/`. Machine state (manifests,
run pointers) goes in `state/`. Experiments that do not touch production go
in `experiments/`.

---

## PART 1 scope

Foundation only:

- directory layout
- operating rules
- safe configuration
- golden-reference integrity manifest
- initial repository audit

PART 1 does **not** implement:

- trade matcher
- discrepancy engine
- TradingView parser
- automatic code modification
- research loop
- autonomous backtesting loop
- approval automation

Next authorized phase: **PART 2 — TRADINGVIEW RESEARCH ENGINE**.

---

## Security

No API keys, passwords, tokens, cookies, or private keys belong in this tree.
If a credential is encountered while inspecting the host repository, report
only: `Credential detected — value intentionally hidden.`
