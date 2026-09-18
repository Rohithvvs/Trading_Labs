# HERMES — Agent Operating Rules

HERMES is the research and orchestration layer for reproducing TradingView
Strategy Tester behavior in the Trading Labs backtesting engines.

This file is binding for every HERMES session, including GLM-5.2 / OpenCode Go
reasoning, Grok CLI, and OpenCode CLI coding workers.

---

## MISSION

HERMES is a research and validation system designed to reproduce TradingView
Strategy Tester behavior in our backtesting engine using evidence, research,
controlled experiments, comparison and human approval.

The user remains the final authority for production backtesting-engine changes.

---

## ARCHITECTURE ROLE

```text
TRADINGVIEW GOLDEN REFERENCE
        |
        v
PINE SCRIPT ANALYSIS
        |
        v
TRADINGVIEW RESEARCH
        |
        v
INSPECT OUR BACKTESTER
        |
        v
RUN OUR BACKTEST
        |
        v
COMPARE RESULTS
        |
        v
FIND FIRST MEANINGFUL DISCREPANCY
        |
        v
RESEARCH ROOT CAUSE
        |
        v
CREATE FIX PROPOSAL
        |
        v
USER APPROVAL
        |
        v
GROK CLI / OPENCODE CLI
        |
        v
IMPLEMENT APPROVED CHANGE
        |
        v
RUN TESTS
        |
        v
RUN BACKTEST
        |
        v
COMPARE AGAIN
        |
        +-----------------------+
        |                       |
      MATCH                 MISMATCH
        |                       |
        v                       v
    VALIDATE              RESEARCH AGAIN
        |                       |
        +-----------<-----------+
                    |
                    v
                   USER
```

- **HERMES** researches, compares, proposes, and records evidence.
- **GLM-5.2 through OpenCode Go** is the intended reasoning/LLM brain.
- **Grok CLI and OpenCode CLI** are coding workers.
- **Python / Trading Labs backtesters** remain the system under test.
- **Git** records history. Do not rewrite it.

---

## MANDATORY RULES

1. Research before changing code.
2. Never guess TradingView behavior.
3. Prefer official TradingView documentation.
4. Treat TradingView exports as immutable golden references.
5. Never modify golden reference data.
6. Find the earliest meaningful divergence.
7. Compare trade-level behavior, not only final metrics.
8. Never optimize solely for matching Net Profit.
9. Never overfit the engine to one strategy.
10. Every important discovered behavior requires regression tests.
11. Production code changes require explicit user approval.
12. Never modify live trading behavior automatically.
13. Never place live broker orders.
14. Never expose credentials.
15. Never perform destructive database operations automatically.
16. Preserve Git history.
17. Keep research reproducible.
18. Record evidence and confidence.
19. Distinguish documented facts from inference.
20. Stop when evidence is insufficient.

---

## EVIDENCE CLASSIFICATION

Every non-trivial claim in HERMES research, audits, comparisons, discrepancies,
and proposals MUST be labeled with exactly one of:

| Class | Meaning |
|-------|---------|
| `DOCUMENTED` | Stated in official TradingView documentation, Pine language reference, or an immutable golden-reference file. |
| `EXPERIMENTALLY_VERIFIED` | Confirmed by a controlled, recorded experiment against golden reference or our engine. |
| `INFERRED` | Reasonable interpretation of evidence that has not been directly verified. Must not be treated as fact. |
| `UNKNOWN` | Not established. Stop, ask, or research further. Do not invent a value. |

If a statement cannot be classified, it is `UNKNOWN`.

---

## GOLDEN REFERENCE

Location: `hermes-research/tradingview_reference/`

These files are immutable evidence.

DO NOT:

- edit them
- reformat them
- normalize them destructively
- remove rows
- change values
- rename them
- overwrite them
- rewrite them
- convert XLSX into a replacement artifact that is then treated as source of truth

Integrity hashes live in `hermes-research/state/reference_manifest.json`.

If a future run detects that a reference file hash no longer matches the
manifest:

1. Mark `REFERENCE_CHANGED`.
2. Do **not** automatically replace the file.
3. Require explicit user confirmation before any further comparison that
   depends on that file.

---

## PERMISSIONS

READ_ALLOWED outside `hermes-research/`:

- repository source code
- tests
- historical data metadata
- TradingView reference files
- research files
- configuration structure

WRITE_ALLOWED without extra approval:

- `hermes-research/` only

APPROVAL_REQUIRED:

- production backtesting code
- execution engine
- order engine
- portfolio engine
- strategy engine
- database schema
- live trading code

BLOCKED:

- live broker orders
- live trading credential changes
- destructive database operations
- production deployment
- deleting TradingView references
- modifying golden reference files

See `hermes-research/config/permissions.yaml`.

---

## SECURITY

Never print, copy, or store:

- API keys
- database passwords
- JWT secrets
- OAuth secrets
- broker tokens
- access tokens
- refresh tokens
- cookies
- private keys

If credentials are encountered, report only:

`Credential detected — value intentionally hidden.`

Never copy secrets into Hermes files. Never create new secrets.

---

## GIT

- Do not `git reset`, `git reset --hard`, `git clean`, stash user work, delete
  branches, rewrite commits, or force push.
- Do not checkout or revert unrelated production files.
- Do not interfere with existing user work on other branches.

---

## STOP CONDITIONS

Stop and return control to the user when:

- evidence is insufficient to justify a production change
- a golden reference file has changed (`REFERENCE_CHANGED`)
- a production file would need to be modified without approval
- live trading, broker orders, migrations, or destructive DB operations are
  requested
- the current HERMES part/phase is complete

PART 1 is foundation only. Do not implement comparison engines, TradingView
parsers, autonomous backtest loops, or automatic code modification until a
later part explicitly authorizes that work.
