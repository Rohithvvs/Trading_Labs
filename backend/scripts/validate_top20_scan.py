"""Real Top Set=20 scanner validation (in-process, same code path as UI).

Runs ScanExecutionService.execute_scan with top_n=20 against live settings/DB/FYERS.
Does not raise the 600s timeout — measures actual wall clock and stage markers.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure backend root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    from app.schemas import AnalysisMode, ScreenerRequest, TimeframeConfig
    from app.services.scan_execution_service import ScanExecutionService

    progress_log: list[dict] = []
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    # execute_scan fire-and-forgets _run_scan_task; completion arrives on the queue
    # as status=complete|error (same contract as the UI SSE stream).
    SCAN_WAIT_SEC = 700.0

    payload = ScreenerRequest(
        symbols=[],  # full universe path
        mode=AnalysisMode.swing,
        top_n=20,
        timeframe=TimeframeConfig(swing="1d", lookback_window=180),
    )

    # Bypass scanner result cache so this is a real pipeline run, not CACHE_HIT.
    try:
        from app.services import scanner_cache as _sc

        async def _no_cache(*_a, **_k):
            return None

        _sc.get_cached_scanner_result = _no_cache  # type: ignore[assignment]
        print("CACHE_BYPASS | get_cached_scanner_result forced empty", flush=True)
    except Exception as cache_exc:
        print(f"CACHE_BYPASS_WARN | {cache_exc}", flush=True)

    t0 = time.perf_counter()
    print("SCAN_START | top_n=20 | universe=NIFTY500", flush=True)
    status = "UNKNOWN"
    result = None
    err = None
    try:
        # Starts worker task; returns after lock/ensure setup, NOT after full scan.
        await ScanExecutionService.execute_scan(
            payload,
            progress_queue=q,
            trigger_source="ui",
            save_history=False,
        )
        print("WORKER_LAUNCHED | waiting for status=complete|error on progress queue", flush=True)

        deadline = time.perf_counter() + SCAN_WAIT_SEC
        while time.perf_counter() < deadline:
            try:
                item = await asyncio.wait_for(q.get(), timeout=5.0)
            except asyncio.TimeoutError:
                elapsed = time.perf_counter() - t0
                print(f"WAIT | elapsed={elapsed:.0f}s | still running...", flush=True)
                continue
            progress_log.append(item)
            stage = item.get("stage") or item.get("status")
            if stage:
                print(
                    f"PROGRESS | stage={stage} | progress={item.get('progress')} | "
                    f"done={item.get('done')} | remaining={item.get('remaining')}",
                    flush=True,
                )
            if item.get("status") == "complete":
                result = item.get("result")
                status = "SUCCESS"
                print(
                    f"RESULT_TYPE | type={type(result).__name__} | "
                    f"keys={list(result.keys())[:30] if isinstance(result, dict) else 'n/a'}",
                    flush=True,
                )
                break
            if item.get("status") == "error":
                status = "FAILED"
                err = item.get("message") or item.get("error_type") or "scan error event"
                print(f"SCAN_ERROR_EVENT | {err}", flush=True)
                break
        else:
            status = "FAILED"
            err = f"no complete/error event within {SCAN_WAIT_SEC:.0f}s"
            print(f"SCAN_ERROR | {err}", flush=True)
    except Exception as exc:
        status = "FAILED"
        err = f"{type(exc).__name__}: {exc}"
        print(f"SCAN_ERROR | {err}", flush=True)
        import traceback

        traceback.print_exc()
    duration = time.perf_counter() - t0

    # Parse result payload
    symbols_scanned = 0
    eligible = shortlisted = buy = watch = reject = 0
    if isinstance(result, dict):
        symbols_scanned = len(result.get("data_valid_symbols") or result.get("symbols") or [])
        shortlisted = len(result.get("shortlisted_symbols") or [])
        buy = len(result.get("buy_candidate_symbols") or [])
        watch = len(result.get("watch_candidate_symbols") or [])
        eligible = len(result.get("eligible_symbols") or []) or len(
            result.get("matched_symbols") or []
        )
        # Fallback from screener_results
        if not symbols_scanned and result.get("screener_results"):
            symbols_scanned = len(result["screener_results"])
        items = result.get("analysis", {}).get("items") if isinstance(result.get("analysis"), dict) else None
        if items is None and isinstance(result.get("items"), list):
            items = result["items"]
        if items:
            for it in items:
                rec = (it or {}).get("recommendation") or {}
                act = str(rec.get("action") or "").upper()
                if act == "BUY":
                    buy = max(buy, 0)
                # recount from items if lists empty
            if not buy and not watch:
                buy = sum(
                    1
                    for it in items
                    if str(((it or {}).get("recommendation") or {}).get("action") or "").upper()
                    == "BUY"
                )
                watch = sum(
                    1
                    for it in items
                    if str(((it or {}).get("recommendation") or {}).get("action") or "").upper()
                    == "WATCH"
                )
                reject = sum(
                    1
                    for it in items
                    if str(((it or {}).get("recommendation") or {}).get("action") or "").upper()
                    == "REJECT"
                )

    stages = [p.get("stage") for p in progress_log if p.get("stage")]
    print("=== VALIDATION SUMMARY ===", flush=True)
    print(f"status={status}", flush=True)
    print(f"duration_sec={duration:.2f}", flush=True)
    print(f"symbols_scanned={symbols_scanned}", flush=True)
    print(f"eligible={eligible}", flush=True)
    print(f"shortlisted={shortlisted}", flush=True)
    print(f"buy={buy}", flush=True)
    print(f"watch={watch}", flush=True)
    print(f"reject={reject}", flush=True)
    if err:
        print(f"error={err}", flush=True)
    print(f"progress_events={len(progress_log)}", flush=True)
    print(f"last_stages={stages[-15:]}", flush=True)

    out_path = ROOT / "logs" / "validate_top20_scan_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "status": status,
                "duration_sec": duration,
                "symbols_scanned": symbols_scanned,
                "eligible": eligible,
                "shortlisted": shortlisted,
                "buy": buy,
                "watch": watch,
                "reject": reject,
                "error": err,
                "stages": stages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote={out_path}", flush=True)
    return 0 if status == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
