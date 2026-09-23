"""Per-run Indicator Scanner analytics from evaluated strategy conditions."""

from __future__ import annotations

from typing import Any

from .entry_conditions import CONDITIONS_OUTPUT_KEY, usable_condition_rows

RETURN_OUTPUT_KEY = "__scan_return_pct"


def signal_sort_rank(sig: str | None) -> int:
    text = (sig or "").strip().upper()
    if text in {"MATCH", "MATCHED", "BUY"}:
        return 0
    if text in {"REJECT", "FAILED"}:
        return 1
    if text == "SKIPPED":
        return 2
    return 3


def row_return_pct(outputs: dict[str, Any] | None, ohlcv: dict[str, Any] | None) -> float | None:
    data = outputs or {}
    bars = ohlcv or {}
    stored = data.get(RETURN_OUTPUT_KEY)
    if isinstance(stored, (int, float)):
        return float(stored)
    momentum = data.get("Momentum 252")
    if momentum is None:
        momentum = data.get("Mom 252")
    if momentum is None:
        momentum = data.get("First-Year Return")
    if isinstance(momentum, (int, float)):
        return float(momentum) * 100.0
    close = data.get("Close")
    if close is None:
        close = bars.get("close")
    close_t252 = data.get("Close t-252")
    if isinstance(close, (int, float)) and isinstance(close_t252, (int, float)) and close_t252:
        return (float(close) / float(close_t252) - 1.0) * 100.0
    for key in ("Prior 252 High", "Prior 252-Session High"):
        prior = data.get(key)
        if isinstance(close, (int, float)) and isinstance(prior, (int, float)) and prior:
            return (float(close) / float(prior) - 1.0) * 100.0
    return None


def row_signal(row: dict[str, Any] | Any) -> str:
    status = _get(row, "status")
    matched = bool(_get(row, "matched"))
    if status == "insufficient_history":
        return "SKIPPED"
    if status != "ok":
        return "REJECT"
    return "MATCH" if matched else "REJECT"


def stored_conditions(row: dict[str, Any] | Any) -> list[dict[str, Any]]:
    outputs = _get(row, "outputs") or {}
    if not isinstance(outputs, dict):
        return []
    return usable_condition_rows(outputs.get(CONDITIONS_OUTPUT_KEY))


def build_indicator_scan_analytics(
    rows: list[dict[str, Any]],
    *,
    universe_size: int,
    condition_defs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ok = [row for row in rows if row.get("status") == "ok"]
    skipped = sum(1 for row in rows if row.get("status") == "insufficient_history")
    errors = sum(1 for row in rows if row.get("status") not in {"ok", "insufficient_history"})
    matched = [row for row in ok if row.get("matched")]
    failed = [row for row in ok if not row.get("matched")]
    names = _condition_names(rows, condition_defs)
    independent = _independent_stats(ok, names)
    funnel = _sequential_funnel(ok, names, matched_count=len(matched), universe_size=len(ok) or universe_size)
    scored: list[tuple[dict[str, Any], float]] = []
    for row in ok:
        pct = row_return_pct(row.get("outputs") or {}, row.get("ohlcv") or {})
        if pct is None:
            continue
        scored.append((row, pct))
    positive = [item for item in scored if item[1] > 0]
    negative = [item for item in scored if item[1] < 0]
    flat = [item for item in scored if item[1] == 0]
    returns = [pct for _, pct in scored]
    top_pos = sorted(positive, key=lambda item: item[1], reverse=True)[:5]
    top_neg = sorted(negative, key=lambda item: item[1])[:5]
    return {
        "stocks_scanned": len(rows),
        "evaluated": len(ok),
        "positive_returns": len(positive),
        "negative_returns": len(negative),
        "flat_returns": len(flat),
        "average_return": (sum(returns) / len(returns)) if returns else None,
        "top_return": max(returns) if returns else None,
        "worst_return": min(returns) if returns else None,
        "top_positive": [_rank_row(row, pct, rank) for rank, (row, pct) in enumerate(top_pos, start=1)],
        "top_negative": [_rank_row(row, pct, rank) for rank, (row, pct) in enumerate(top_neg, start=1)],
        "filter_analytics": independent,
        "filter_funnel": funnel,
        "unmatched_count": len(failed),
        "skipped_count": skipped,
        "error_count": errors,
        "matched": len(matched),
    }


def _get(row: dict[str, Any] | Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _condition_names(rows: list[dict[str, Any]], defs: list[dict[str, Any]] | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in defs or []:
        name = str(item.get("name") or "").strip() if isinstance(item, dict) else str(item).strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
    if names:
        return names
    for row in rows:
        for cond in stored_conditions(row):
            name = str(cond.get("name") or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            names.append(name)
        if names:
            break
    return names


def _independent_stats(ok_rows: list[dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for index, name in enumerate(names, start=1):
        passed = failed = skipped = 0
        for row in ok_rows:
            match = next((item for item in stored_conditions(row) if str(item.get("name") or "") == name), None)
            if match is None:
                skipped += 1
            elif match.get("passed"):
                passed += 1
            else:
                failed += 1
        total = passed + failed
        stats.append(
            {
                "filter_id": f"c{index}",
                "label": name,
                "filter_name": name,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "pass_pct": (passed / total * 100.0) if total else 0.0,
                "fail_pct": (failed / total * 100.0) if total else 0.0,
            }
        )
    return stats


def _sequential_funnel(
    ok_rows: list[dict[str, Any]],
    names: list[str],
    *,
    matched_count: int,
    universe_size: int,
) -> list[dict[str, Any]]:
    start = universe_size or len(ok_rows)
    remaining_ids = {str(row.get("symbol") or "") for row in ok_rows}
    steps = [
        {
            "step": 0,
            "filter_id": None,
            "label": "Start Universe",
            "remaining": start,
            "drop": 0,
            "retention_pct": 100.0,
        }
    ]
    prev = start
    for index, name in enumerate(names, start=1):
        still: set[str] = set()
        for row in ok_rows:
            symbol = str(row.get("symbol") or "")
            if symbol not in remaining_ids:
                continue
            match = next((item for item in stored_conditions(row) if str(item.get("name") or "") == name), None)
            if match and match.get("passed"):
                still.add(symbol)
        remaining_ids = still
        remaining = len(remaining_ids)
        steps.append(
            {
                "step": index,
                "filter_id": f"c{index}",
                "label": name,
                "remaining": remaining,
                "drop": max(0, prev - remaining),
                "retention_pct": (remaining / start * 100.0) if start else 0.0,
            }
        )
        prev = remaining
    steps.append(
        {
            "step": len(names) + 1,
            "filter_id": "final",
            "label": "Final MATCHED Signals",
            "remaining": matched_count,
            "drop": max(0, prev - matched_count),
            "retention_pct": (matched_count / start * 100.0) if start else 0.0,
        }
    )
    return steps


def _rank_row(row: dict[str, Any], return_pct: float, rank: int) -> dict[str, Any]:
    outputs = row.get("outputs") or {}
    ohlcv = row.get("ohlcv") or {}
    close = outputs.get("Close") if isinstance(outputs.get("Close"), (int, float)) else ohlcv.get("close")
    close_t252 = outputs.get("Close t-252") if isinstance(outputs.get("Close t-252"), (int, float)) else None
    conditions = stored_conditions(row)
    passed = [str(item.get("name")) for item in conditions if item.get("passed")]
    failed = [str(item.get("name")) for item in conditions if not item.get("passed")]
    return {
        "rank": rank,
        "symbol": row.get("symbol"),
        "company": row.get("display_name"),
        "entry_price": close_t252,
        "exit_price": close,
        "return_pct": return_pct,
        "signal": "MATCH" if row.get("matched") else "REJECT",
        "key_filters": passed[:3],
        "passed_filters": passed,
        "failed_filters": failed,
    }
