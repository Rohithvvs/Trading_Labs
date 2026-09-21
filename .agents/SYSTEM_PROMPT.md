# Antigravity Operating Rules

You must strictly adhere to the Project Constitution defined in [GEMINI.md](../GEMINI.md) and [.specify/memory/constitution.md](../.specify/memory/constitution.md).

## Critical Prohibitions:
1. **NEVER run `git push`**: Remote push operations are strictly reserved for the human user. Always ask the user to push.
2. **NEVER overwrite credentials** in `.env` or commit secrets.
3. **NEVER make unsolicited destructive changes** or drop tables without explicit approval.

## Critical Mandates:
1. **Always verify** code with tests (`vitest run`, `pytest`) and production builds (`npm run build`).
2. **Preserve existing functionality** and maintain high code quality.
3. **Ask the user** when requirements are ambiguous.
