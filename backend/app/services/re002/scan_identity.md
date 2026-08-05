# RE-002 scan_run_id Mapping

RE-002 reuses the same completed-scan identity family as RE-001 / latest-scan flows.

- Prefer orchestrator/contextvar `scan_run_id` from `re001.scan_context` (shared scan identity) when present
- Fallback: generated `scan-{UTC}-{hex}` style id in context builder
- Lab comparison lists decisions by `scan_run_id` + `engine_id=RE-002`

Do not invent a second scan identity scheme for RE-002.
