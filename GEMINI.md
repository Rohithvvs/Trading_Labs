# Antigravity Operating Constitution — Trading Labs

This document defines the binding, non-negotiable operational constitution for Antigravity when working on the **Trading Labs** codebase.

---

## 🚫 The "DO NOT" Rules (Strict Prohibitions)

### 1. NEVER Push to Git By Yourself (ABSOLUTE RULE)
- **NEVER** run `git push` or any command that pushes commits or tags to remote repositories (`git push origin ...`, `git push --force`, etc.).
- **ALWAYS** prepare the changes, run tests, ensure the build passes, and create local commits if requested.
- **ALWAYS** stop and explicitly ask the user to push to git, providing the recommended push command (e.g. `git push origin <branch>`).
- Under no circumstance should a subagent, background task, or script automatically trigger a remote git push without explicit user consent in that turn.

### 2. Never Overwrite Credentials or Active Configs
- **NEVER** overwrite, wipe, or hardcode fake/sample keys into `.env` or sensitive secret files.
- **NEVER** log API keys, access tokens (Fyers, Neon, Turso, OpenAI, etc.), or user passwords to console logs or git history.

### 3. Never Make Unsolicited Destructive Changes
- **NEVER** delete existing tests, drop database tables, or remove active features unless specifically instructed by the user.
- **NEVER** bypass error handling by silently catching and swallowing exceptions without actionable logs.

### 4. Never Make Blind Assumptions
- **NEVER** assume database schemas, indicator definitions, or API response shapes without inspecting the relevant schema files or test fixtures first.
- **NEVER** introduce new heavy third-party dependencies without clear necessity and user alignment.

---

## ✅ The "DO" Rules (Mandatory Operating Principles)

### 1. Verification and Testing Discipline
- **DO** run automated tests (`vitest run`, `pytest`) and production builds (`npm run build`) before considering a task complete.
- **DO** verify that new or modified UI components render correctly, maintain dark/light theme integrity, and don't break existing layouts.
- **DO** ensure zero lint or TypeScript compiler errors are introduced.

### 2. User Collaboration & Explicit Approval
- **DO** ask the user for clarification whenever requirements are ambiguous, have conflicting interpretations, or require significant architectural trade-offs.
- **DO** present git status and give the user the exact command to run when changes are ready to push.

### 3. Preservation and Backward Compatibility
- **DO** preserve existing code conventions, comments, docstrings, and established architecture (FastAPI backend + Vite/React frontend).
- **DO** ensure Pine Script indicators and strategy definitions adhere strictly to the supported language subset specifications.

### 4. Precision & Scope Control
- **DO** keep changes scoped precisely to what the user requested.
- **DO** explain rationale clearly and link modified files using clickable markdown links.

---

**Version**: 1.0.0 | **Ratified**: 2026-09-21 | **Scope**: Workspace (Trading Labs)
