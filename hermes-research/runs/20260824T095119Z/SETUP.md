# Phase A/B setup record

OS: Windows_NT, PowerShell 5.1, workspace `D:\Trading_Labs\Trading_Labs`.

## Hermes CLI

- Already installed: `C:\Users\k.sai chandra sekhar\AppData\Local\hermes\hermes-agent\bin\hermes.exe`
- Version: Hermes Agent v0.20.4 (2026.8.18), upstream e2c4793e
- `hermes version` is not a valid subcommand on this build; use `hermes --version`
- `hermes doctor`: Python 3.11.9 OK; config present; SQLite WAL advisory; connectivity checks were still running in background at first invoke (non-blocking)

PATH note: `hermes.exe` is on PATH for this user (`AppData\Local\hermes\hermes-agent\bin`).

## OpenCode brain

- Project key location: repo `.env` line `OPENCODE API KEY = sk-…` (not a standard `KEY=value` line; python-dotenv warns at line 116)
- User OpenCode config: `~/.config/opencode/opencode.jsonc` model `opencode/mimo-v2.5-free`
- Project Hermes intent: `hermes-research/config/agent.yaml` → provider `opencode-go`, model `glm-5.2`
- Documented Go Chat Completions base: `https://opencode.ai/zen/go/v1` (OpenCode Go docs; no base URL existed in this repo)

Configured (no key committed, no key echoed):

```
hermes config set model.provider custom
hermes config set model.base_url https://opencode.ai/zen/go/v1
hermes config set model.default glm-5.2
```

Secrets file: `hermes config env-path` → `%LOCALAPPDATA%\hermes\.env`  
Env names written: `OPENAI_API_KEY` (custom provider), `OPENCODE_API_KEY`, `OPENAI_BASE_URL=https://opencode.ai/zen/go/v1`

Sanity check:

```
hermes -z "Reply with only the exact token HERMES_OK and nothing else. Do not use tools." --yolo --safe-mode
→ HERMES_OK
```

## Comparison

Read-only harness: `hermes-research/harness/export_and_compare.py` (no engine edits).

Artifacts: this directory.
