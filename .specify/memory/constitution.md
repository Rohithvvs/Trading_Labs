<!-- Sync Impact Report
Version change: 0.0.0-template -> 1.0.0
Modified principles:
  - PRINCIPLE_1: Library-First & Modular Architecture
  - PRINCIPLE_2: Git Safety & Remote Push Sovereignty (NON-NEGOTIABLE)
  - PRINCIPLE_3: Test-First & Build Verification
  - PRINCIPLE_4: Credential & Secret Protection
  - PRINCIPLE_5: Precision Scope & Minimal Disruption
Added sections:
  - Do Not Rules (Strict Prohibitions)
  - Do Rules (Mandatory Operating Principles)
Templates requiring updates:
  - ✅ .specify/memory/constitution.md updated
-->

# Trading Labs Constitution

This constitution establishes the governing principles, mandatory rules, and prohibited actions for all autonomous agents, developer tools, and contributors working on the **Trading Labs** platform.

## Core Principles

### I. Git Safety & Push Sovereignty (NON-NEGOTIABLE)
Remote repository write operations (`git push`) belong exclusively to the human user. The agent must never push to a remote repository automatically. Every remote synchronization requires explicit user invocation or authorization.

### II. Test-First & Build Verification
No change is complete until it has passed automated tests and a production build verification. Regressions in strategy backtesting, indicator calculations, or trading desk interfaces are unacceptable.

### III. Library-First & Modular Architecture
Every feature begins as a clean, self-contained, and independently testable module. Backend services (FastAPI/Python) and frontend components (React/Vite) must maintain clear interface contracts and type definitions.

### IV. Credential & Environment Protection
API keys, database connection strings (Neon, Turso/libsql), broker credentials (Fyers), and authentication secrets must remain strictly confined to environment variables. They must never be logged, committed, or exposed in client bundles.

### V. Minimal Disruption & Code Integrity
Preserve existing working functionality, docstrings, and comments. Changes must be scoped precisely to the user's intent without unsolicited sprawling refactors.

---

## 🚫 The "DO NOT" Rules (Strict Prohibitions)

1. **NEVER Push to Git By Yourself**:
   - The agent is strictly forbidden from running `git push`, `git push origin <branch>`, or any command that uploads commits or tags to remote repositories.
   - When changes are committed or ready, the agent must inform the user and provide the exact command for the user to run.
2. **NEVER Overwrite Sensitive Configuration**:
   - Do not replace real environment credentials with mocks or placeholders in `.env`.
   - Do not commit secrets, tokens, or credential keys.
3. **NEVER Execute Destructive Database Operations Without Approval**:
   - Dropping database tables, wiping paper trading balances, or altering operational schemas without a verified migration plan is prohibited.
4. **NEVER Bypass Verification**:
   - Do not mark a task complete without running relevant test suites and ensuring the build passes.
5. **NEVER Swallow Exceptions Silently**:
   - Never use bare `except:` blocks that mask system failures. Proper structured logging and error reporting are required.

---

## ✅ The "DO" Rules (Mandatory Operating Principles)

1. **DO Run Verification Before Completion**:
   - Execute `npm test` or `vitest run` for frontend changes.
   - Execute `npm run build` to confirm production bundles build cleanly.
   - Execute `pytest` for backend alterations.
2. **DO Ask Before Making Ambiguous Decisions**:
   - Clarify underspecified requirements rather than making architectural assumptions that might contradict the user's goals.
3. **DO Present Clean Git Status & Push Recommendations**:
   - Clearly state files staged/committed and provide the exact push command for the user to execute manually.
4. **DO Maintain High Visual & Code Standards**:
   - Ensure UI components support responsive layouts and dark/light themes cleanly.
   - Ensure Pine Script compatibility rules are upheld for all indicator presets.

---

## Governance

- This Constitution supersedes any default agent behavior or automated workflow scripts.
- Amendments to this constitution require documentation, semantic version bumps, and user review.
- All tasks, plans, and specifications must align with these principles.

**Version**: 1.0.0 | **Ratified**: 2026-09-21 | **Last Amended**: 2026-09-21
