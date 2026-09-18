"""Compose a side-by-side strategy comparison from persisted Strategy Tester runs and LEAN jobs.

Does not re-run backtests or invent metrics. Missing values stay null.
Equity / period returns are taken only from existing trading-session series
(LEAN equity curve), never from calendar-day interpolation.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select

from ...db.session import AsyncSessionLocal
from ...lean.models import LeanJobRecord, LeanJobStatus
from ...lean.services.lean_service import LeanBacktestService
from ...models.strategy_tester import StrategyDefinition, StrategyTestResult, StrategyTestRun
from ..strategy_tester import persistence
from ..strategy_tester.schema import StrategyConfigError, parse_strategy_config

MIN_SLOTS = 2
MAX_SLOTS = 4
SOURCE_TESTER = "strategy_tester"
SOURCE_LEAN = "lean"

_RETURN_BUCKETS = (
    ("lt_neg10", "< -10%", None, -10.0),
    ("neg10_neg5", "-10% to -5%", -10.0, -5.0),
    ("neg5_0", "-5% to 0%", -5.0, 0.0),
    ("eq_0", "0%", 0.0, 0.0),
    ("pos0_5", "0% to 5%", 0.0, 5.0),
    ("pos5_10", "5% to 10%", 5.0, 10.0),
    ("gt_10", "> 10%", 10.0, None),
)


class CompareError(ValueError):
    """Client-facing comparison error."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _pct_label(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:g}%"


def extract_logic(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Entry/exit/indicators/filters/risk rules from a strategy snapshot. No evaluation."""
    raw = snapshot if isinstance(snapshot, dict) else {}
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    pine = source.get("pine_code") or source.get("pineCode")
    pine_code = str(pine).strip() if isinstance(pine, str) and pine.strip() else None
    source_type = str(source.get("type") or ("pine" if pine_code else "builder"))

    entry: list[str] = []
    filters: list[str] = []
    indicators: list[str] = []
    exit_conditions: list[str] = []
    stop_loss: str | None = None
    take_profit: str | None = None
    trailing_stop: str | None = None
    position_type = str(raw.get("side") or "LONG").upper()
    time_exit = None

    try:
        cfg = parse_strategy_config(raw)
        position_type = cfg.position.side
        for leaf in cfg.root.leaf_nodes():
            label = leaf.display_label()
            entry.append(label)
            filters.append(label)
            for operand in (leaf.left, leaf.right, leaf.right_high):
                if operand is None or operand.kind != "series" or not operand.name:
                    continue
                indicators.append(operand.label())
        if cfg.position.entry_rule:
            entry.append(f"Entry rule: {str(cfg.position.entry_rule).replace('_', ' ').title()}")
        if cfg.position.exit_rule:
            exit_conditions.append(str(cfg.position.exit_rule).replace("_", " ").title())
        stop_loss = _pct_label(cfg.position.stop_loss_pct)
        take_profit = _pct_label(cfg.position.target_pct)
        trailing_stop = _pct_label(cfg.position.trailing_stop_pct)
        time_exit = cfg.position.time_exit_bars
        if time_exit:
            exit_conditions.append(f"Time exit after {time_exit} bars")
    except (StrategyConfigError, Exception):
        pos = raw.get("position_rules") if isinstance(raw.get("position_rules"), dict) else {}
        position_type = str(pos.get("side") or raw.get("side") or position_type).upper()
        stop_loss = _pct_label(_num(pos.get("stop_loss_pct")))
        take_profit = _pct_label(_num(pos.get("target_pct")))
        trailing_stop = _pct_label(_num(pos.get("trailing_stop_pct")))
        if pos.get("exit_rule"):
            exit_conditions.append(str(pos.get("exit_rule")).replace("_", " ").title())
        leaves = raw.get("filters")
        if isinstance(leaves, list):
            for item in leaves:
                if isinstance(item, dict) and item.get("label"):
                    entry.append(str(item["label"]))
                    filters.append(str(item["label"]))

    seen_ind: list[str] = []
    for name in indicators:
        if name not in seen_ind:
            seen_ind.append(name)

    return {
        "source_type": source_type,
        "pine_code": pine_code,
        "entry_conditions": entry,
        "exit_conditions": exit_conditions,
        "indicators": seen_ind,
        "filters": filters,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "trailing_stop": trailing_stop,
        "position_type": position_type if position_type in {"LONG", "SHORT"} else "LONG",
        "time_exit_bars": time_exit,
    }


def extract_config(
    *,
    universe: str | None,
    universe_size: int | None,
    timeframe: str | None,
    start_date: Any,
    end_date: Any,
    initial_capital: Any,
    commission: Any,
    slippage: Any,
    position_type: str | None,
    source: str,
) -> dict[str, Any]:
    return {
        "start_date": _iso(start_date),
        "end_date": _iso(end_date),
        "universe": universe,
        "universe_size": universe_size,
        "timeframe": timeframe,
        "initial_capital": _num(initial_capital),
        "commission": _num(commission),
        "slippage": _num(slippage),
        "position_type": position_type,
        "source": source,
    }


def config_mismatches(configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Warn when compared runs used different backtest settings. None is ignored unless mixed with a value."""
    fields = (
        ("start_date", "Date range start"),
        ("end_date", "Date range end"),
        ("universe", "Universe"),
        ("timeframe", "Timeframe"),
        ("initial_capital", "Initial capital"),
        ("commission", "Commission"),
        ("slippage", "Slippage"),
        ("position_type", "Position type"),
    )
    warnings: list[dict[str, Any]] = []
    for key, label in fields:
        values = []
        for cfg in configs:
            value = cfg.get(key)
            if value is None or value == "":
                continue
            if isinstance(value, float):
                value = round(value, 8)
            if value not in values:
                values.append(value)
        if len(values) > 1:
            present = sum(1 for cfg in configs if cfg.get(key) not in (None, ""))
            missing = len(configs) - present
            warnings.append(
                {
                    "field": key,
                    "label": label,
                    "values": values,
                    "message": f"{label} differs across selected runs.",
                    "missing_on_some": missing > 0,
                }
            )
        else:
            present = [cfg.get(key) not in (None, "") for cfg in configs]
            if any(present) and not all(present):
                warnings.append(
                    {
                        "field": key,
                        "label": label,
                        "values": [cfg.get(key) for cfg in configs],
                        "message": f"{label} is missing on some selected runs.",
                        "missing_on_some": True,
                    }
                )
    return warnings


def signal_comparison(slots: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare BUY (and WATCH) symbol sets from Strategy Tester results only."""
    usable = [s for s in slots if s.get("signals")]
    sets: dict[str, dict[str, set[str]]] = {}
    for slot in usable:
        sid = str(slot["slot_id"])
        buy: set[str] = set()
        watch: set[str] = set()
        reject: set[str] = set()
        for row in slot["signals"]:
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            sig = str(row.get("signal") or "").upper()
            if sig == "BUY":
                buy.add(symbol)
            elif sig == "WATCH":
                watch.add(symbol)
            elif sig == "REJECT":
                reject.add(symbol)
        sets[sid] = {"BUY": buy, "WATCH": watch, "REJECT": reject}

    pairwise: list[dict[str, Any]] = []
    ids = list(sets.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            buy_a, buy_b = sets[a]["BUY"], sets[b]["BUY"]
            union = buy_a | buy_b
            shared = buy_a & buy_b
            overlap = (len(shared) / len(union) * 100.0) if union else None
            pairwise.append(
                {
                    "left_slot_id": a,
                    "right_slot_id": b,
                    "shared_buy": sorted(shared),
                    "left_only_buy": sorted(buy_a - buy_b),
                    "right_only_buy": sorted(buy_b - buy_a),
                    "shared_count": len(shared),
                    "overlap_pct": _round(overlap, 2),
                }
            )

    all_symbols: set[str] = set()
    for groups in sets.values():
        all_symbols |= groups["BUY"] | groups["WATCH"] | groups["REJECT"]

    symbol_rows = []
    for symbol in sorted(all_symbols):
        per_slot = {}
        for sid, groups in sets.items():
            if symbol in groups["BUY"]:
                per_slot[sid] = "BUY"
            elif symbol in groups["WATCH"]:
                per_slot[sid] = "WATCH"
            elif symbol in groups["REJECT"]:
                per_slot[sid] = "REJECT"
            else:
                per_slot[sid] = None
        symbol_rows.append({"symbol": symbol, "signals": per_slot})

    overall_overlap = pairwise[0]["overlap_pct"] if len(pairwise) == 1 else None
    if len(pairwise) > 1:
        vals = [p["overlap_pct"] for p in pairwise if p["overlap_pct"] is not None]
        overall_overlap = _round(sum(vals) / len(vals), 2) if vals else None

    return {
        "available": len(usable) >= 2,
        "unavailable_reason": None
        if len(usable) >= 2
        else "Signal comparison needs at least two Strategy Tester scan runs with per-symbol results.",
        "slot_counts": {
            sid: {"buy": len(g["BUY"]), "watch": len(g["WATCH"]), "reject": len(g["REJECT"])}
            for sid, g in sets.items()
        },
        "pairwise": pairwise,
        "overlap_pct": overall_overlap,
        "symbols": symbol_rows[:2000],
        "symbol_count": len(symbol_rows),
    }


def monthly_yearly_from_equity(equity: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Period returns from an existing NSE-session equity curve. No weekend/holiday bars are inserted."""
    monthly_map: dict[str, list[tuple[str, float]]] = defaultdict(list)
    yearly_map: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for point in equity:
        d = str(point.get("date") or "")[:10]
        eq = _num(point.get("equity"))
        if len(d) < 7 or eq is None:
            continue
        monthly_map[d[:7]].append((d, eq))
        yearly_map[d[:4]].append((d, eq))

    def _period_rows(groups: dict[str, list[tuple[str, float]]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        prev_end: float | None = None
        for period in sorted(groups):
            pts = sorted(groups[period], key=lambda item: item[0])
            start_eq = pts[0][1] if prev_end is None else prev_end
            end_eq = pts[-1][1]
            ret = ((end_eq / start_eq) - 1.0) * 100.0 if start_eq else None
            rows.append(
                {
                    "period": period,
                    "start_equity": _round(start_eq, 2),
                    "end_equity": _round(end_eq, 2),
                    "return_pct": _round(ret, 4),
                }
            )
            prev_end = end_eq
        return rows

    return {"monthly": _period_rows(monthly_map), "yearly": _period_rows(yearly_map)}


def trade_distribution(returns: list[float | None]) -> list[dict[str, Any]]:
    values = [float(v) for v in returns if v is not None]
    counts = {
        "lt_neg10": 0,
        "neg10_neg5": 0,
        "neg5_0": 0,
        "eq_0": 0,
        "pos0_5": 0,
        "pos5_10": 0,
        "gt_10": 0,
    }
    for v in values:
        if v < -10:
            counts["lt_neg10"] += 1
        elif v <= -5:
            counts["neg10_neg5"] += 1
        elif v < 0:
            counts["neg5_0"] += 1
        elif v == 0:
            counts["eq_0"] += 1
        elif v <= 5:
            counts["pos0_5"] += 1
        elif v <= 10:
            counts["pos5_10"] += 1
        else:
            counts["gt_10"] += 1
    labels = {key: label for key, label, *_ in _RETURN_BUCKETS}
    return [{"bucket": key, "label": labels[key], "count": counts[key]} for key in counts]


def _empty_metrics() -> dict[str, Any]:
    return {
        "net_profit": None,
        "total_return_pct": None,
        "cagr": None,
        "win_rate": None,
        "total_trades": None,
        "profit_factor": None,
        "average_trade": None,
        "average_trade_unit": None,
        "max_drawdown": None,
        "max_drawdown_pct": None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "calmar_ratio": None,
        "avg_cash": None,
        "avg_exposure_pct": None,
        "long_trades": None,
        "short_trades": None,
        "best_trade": None,
        "worst_trade": None,
        "final_equity": None,
        "initial_capital": None,
        "metrics_source": None,
        "metrics_note": None,
    }


def metrics_from_lean(summary: Any, trades: list[Any]) -> dict[str, Any]:
    metrics = _empty_metrics()
    if summary is None:
        return metrics
    data = summary.model_dump() if hasattr(summary, "model_dump") else dict(summary)
    metrics.update(
        {
            "net_profit": _round(_num(data.get("net_profit") or data.get("netProfit")), 2),
            "total_return_pct": _round(_num(data.get("net_profit_pct") or data.get("netProfitPct")), 4),
            "cagr": _round(_num(data.get("cagr")), 4),
            "win_rate": _round(_num(data.get("win_rate") or data.get("winRate")), 4),
            "total_trades": int(data.get("total_trades") or data.get("totalTrades") or 0),
            "profit_factor": _round(_num(data.get("profit_factor") or data.get("profitFactor")), 4),
            "average_trade": _round(_num(data.get("average_trade") or data.get("averageTrade")), 4),
            "average_trade_unit": "pct",
            "max_drawdown": _round(_num(data.get("maximum_drawdown") or data.get("maximumDrawdown")), 2),
            "max_drawdown_pct": _round(_num(data.get("maximum_drawdown_pct") or data.get("maximumDrawdownPct")), 4),
            "sharpe_ratio": _round(_num(data.get("sharpe_ratio") or data.get("sharpeRatio")), 4),
            "sortino_ratio": _round(_num(data.get("sortino_ratio") or data.get("sortinoRatio")), 4),
            "calmar_ratio": _round(_num(data.get("calmar_ratio") or data.get("calmarRatio")), 4),
            "final_equity": _round(_num(data.get("final_equity") or data.get("finalEquity")), 2),
            "initial_capital": _round(_num(data.get("initial_capital") or data.get("initialCapital")), 2),
            "metrics_source": SOURCE_LEAN,
            "metrics_note": "LEAN backtest summary (NSE session bars, 252-session annualization).",
        }
    )
    long_n = 0
    short_n = 0
    best: dict[str, Any] | None = None
    worst: dict[str, Any] | None = None
    for trade in trades:
        td = trade.model_dump() if hasattr(trade, "model_dump") else dict(trade)
        direction = str(td.get("direction") or "LONG").upper()
        if direction == "SHORT":
            short_n += 1
        else:
            long_n += 1
        pnl = _num(td.get("net_pnl") or td.get("netPnL"))
        item = {
            "symbol": td.get("symbol"),
            "net_pnl": _round(pnl, 2),
            "return_pct": _round(_num(td.get("return_pct") or td.get("returnPct")), 4),
        }
        if pnl is not None:
            if best is None or (best.get("net_pnl") is None) or pnl > float(best["net_pnl"]):
                best = item
            if worst is None or (worst.get("net_pnl") is None) or pnl < float(worst["net_pnl"]):
                worst = item
    metrics["long_trades"] = long_n
    metrics["short_trades"] = short_n
    metrics["best_trade"] = best
    metrics["worst_trade"] = worst
    cagr = metrics.get("cagr")
    dd = metrics.get("max_drawdown_pct")
    if metrics.get("calmar_ratio") is None and cagr is not None and dd is not None and abs(dd) > 0:
        metrics["calmar_ratio"] = _round(float(cagr) / abs(float(dd)), 4)
    return metrics


def metrics_from_strategy_run(run: StrategyTestRun, results: list[StrategyTestResult]) -> dict[str, Any]:
    """Scanner-window metrics that already exist on the run. Does not synthesize Sharpe/CAGR/equity."""
    metrics = _empty_metrics()
    summary = run.summary if isinstance(run.summary, dict) else {}
    with_ret = [r for r in results if r.return_pct is not None]
    positive = [r for r in with_ret if (r.return_pct or 0) > 0]
    negative = [r for r in with_ret if (r.return_pct or 0) < 0]
    returns = [float(r.return_pct) for r in with_ret if r.return_pct is not None]
    win_rate = summary.get("win_rate")
    if win_rate is None and returns:
        win_rate = len(positive) / len(returns) * 100.0
    avg = summary.get("average_return")
    if avg is None and returns:
        avg = sum(returns) / len(returns)
    top = summary.get("top_return")
    worst_ret = summary.get("worst_return")
    best_row = max(with_ret, key=lambda r: float(r.return_pct or 0), default=None) if with_ret else None
    worst_row = min(with_ret, key=lambda r: float(r.return_pct or 0), default=None) if with_ret else None
    if top is None and best_row is not None:
        top = best_row.return_pct
    if worst_ret is None and worst_row is not None:
        worst_ret = worst_row.return_pct

    side = "LONG"
    snap = run.strategy_snapshot if isinstance(run.strategy_snapshot, dict) else {}
    pos = snap.get("position_rules") if isinstance(snap.get("position_rules"), dict) else {}
    side = str(pos.get("side") or snap.get("side") or "LONG").upper()
    n = len(with_ret)
    metrics.update(
        {
            "net_profit": None,
            "total_return_pct": _round(_num(avg), 4),
            "cagr": None,
            "win_rate": _round(_num(win_rate), 4),
            "total_trades": n if n else int(run.buy_count or 0),
            "profit_factor": None,
            "average_trade": _round(_num(avg), 4),
            "average_trade_unit": "pct",
            "max_drawdown": None,
            "max_drawdown_pct": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "long_trades": n if side != "SHORT" else 0,
            "short_trades": n if side == "SHORT" else 0,
            "best_trade": {
                "symbol": best_row.symbol if best_row else None,
                "net_pnl": None,
                "return_pct": _round(_num(top), 4),
            }
            if best_row or top is not None
            else None,
            "worst_trade": {
                "symbol": worst_row.symbol if worst_row else None,
                "net_pnl": None,
                "return_pct": _round(_num(worst_ret), 4),
            }
            if worst_row or worst_ret is not None
            else None,
            "final_equity": None,
            "initial_capital": _round(_num(run.initial_capital), 2),
            "metrics_source": SOURCE_TESTER,
            "metrics_note": (
                "Strategy Tester scan metrics. Net profit, CAGR, Sharpe, Sortino, "
                "drawdown and final equity require a completed LEAN backtest for this strategy."
            ),
        }
    )
    return metrics


_RADAR_AXES: list[dict[str, Any]] = [
    {"key": "win_rate", "label": "Win Rate", "higher_is_better": True, "scale": "pct"},
    {"key": "total_return_pct", "label": "Return %", "higher_is_better": True, "scale": "return"},
    {"key": "profit_factor", "label": "Profit Factor", "higher_is_better": True, "scale": "pf"},
    {"key": "sharpe_ratio", "label": "Sharpe", "higher_is_better": True, "scale": "ratio"},
    {"key": "max_drawdown_pct", "label": "Max Drawdown", "higher_is_better": False, "scale": "dd"},
    {"key": "cagr", "label": "CAGR", "higher_is_better": True, "scale": "return"},
    {"key": "sortino_ratio", "label": "Sortino", "higher_is_better": True, "scale": "ratio"},
    {"key": "average_trade", "label": "Avg Return", "higher_is_better": True, "scale": "return"},
    {"key": "best_trade", "label": "Best Trade", "higher_is_better": True, "scale": "return"},
    {"key": "total_trades", "label": "Trades", "higher_is_better": True, "scale": "count"},
    {"key": "buy_count", "label": "BUY signals", "higher_is_better": True, "scale": "count"},
    {"key": "watch_count", "label": "WATCH", "higher_is_better": True, "scale": "count"},
]


def _axis_raw(slot: dict[str, Any], key: str) -> float | None:
    if key == "buy_count":
        return _num((slot.get("scan_summary") or {}).get("buy"))
    if key == "watch_count":
        return _num((slot.get("scan_summary") or {}).get("watch"))
    if key == "best_trade":
        best = (slot.get("metrics") or {}).get("best_trade") or {}
        return _num(best.get("return_pct")) if isinstance(best, dict) else None
    return _num((slot.get("metrics") or {}).get(key))


def _scale_radar_value(scale: str, raw: float, count_max: float | None) -> float | None:
    if scale == "pct":
        return max(0.0, min(100.0, raw))
    if scale == "pf":
        return max(0.0, min(100.0, (raw / 5.0) * 100.0))
    if scale == "ratio":
        return max(0.0, min(100.0, ((raw + 1.0) / 5.0) * 100.0))
    if scale == "return":
        return max(0.0, min(100.0, ((raw + 20.0) / 70.0) * 100.0))
    if scale == "dd":
        return max(0.0, min(100.0, 100.0 - abs(raw)))
    if scale == "count":
        if not count_max:
            return None
        return max(0.0, min(100.0, (raw / count_max) * 100.0))
    return None


def radar_profile(slots: list[dict[str, Any]]) -> dict[str, Any]:
    """Relative 0–100 scales for charting only. Raw metric values remain the source of truth."""
    series_raw: list[dict[str, float | None]] = []
    for slot in slots:
        series_raw.append({axis["key"]: _axis_raw(slot, axis["key"]) for axis in _RADAR_AXES})

    usable: list[dict[str, Any]] = []
    for axis in _RADAR_AXES:
        values = [row.get(axis["key"]) for row in series_raw]
        if any(value is None for value in values):
            continue
        if axis["key"] == "average_trade" and all(
            row.get("average_trade") == row.get("total_return_pct") for row in series_raw
        ):
            continue
        usable.append({"key": axis["key"], "label": axis["label"], "higher_is_better": axis["higher_is_better"]})
        if len(usable) >= 6:
            break

    count_max: dict[str, float] = {}
    for axis in _RADAR_AXES:
        if axis["scale"] != "count":
            continue
        present = [abs(row[axis["key"]]) for row in series_raw if row.get(axis["key"]) is not None]
        if present:
            count_max[axis["key"]] = max(present)

    series = []
    for slot, raw in zip(slots, series_raw):
        values: dict[str, float | None] = {}
        for axis in _RADAR_AXES:
            raw_v = raw.get(axis["key"])
            if raw_v is None:
                values[axis["key"]] = None
                continue
            values[axis["key"]] = _scale_radar_value(axis["scale"], raw_v, count_max.get(axis["key"]))
        series.append(
            {
                "slot_id": slot.get("slot_id"),
                "name": slot.get("strategy_name"),
                "values": {axis["key"]: values[axis["key"]] for axis in usable},
                "raw": raw,
            }
        )
    return {
        "axes": usable,
        "series": series,
        "note": "Radar axes are a display scale of the same raw metrics. They are not a ranking.",
    }


def _detect_source(run_id: str, source: str | None) -> str:
    if source in {SOURCE_TESTER, SOURCE_LEAN}:
        return source
    if str(run_id).upper().startswith("LEAN-"):
        return SOURCE_LEAN
    return SOURCE_TESTER


def _lean_jobs(user_id: uuid.UUID | None = None) -> list[LeanJobRecord]:
    try:
        jobs = LeanBacktestService.list_jobs(limit=200)
    except Exception:
        return []
    uid = str(user_id) if user_id else None
    if not uid:
        return jobs
    scoped: list[LeanJobRecord] = []
    for job in jobs:
        owner = str(job.user_id) if job.user_id else ""
        if owner and owner != uid:
            continue
        scoped.append(job)
    return scoped


def _lean_matches_strategy(job: LeanJobRecord, strategy_id: str, strategy_name: str) -> bool:
    sid = str(job.strategy_id or "")
    name = str(job.strategy_name or "")
    if sid and sid == str(strategy_id):
        return True
    if strategy_name and name.strip().lower() == strategy_name.strip().lower():
        return True
    return False


def _run_preview(run: StrategyTestRun) -> dict[str, Any]:
    summary = run.summary if isinstance(run.summary, dict) else {}
    return {
        "run_id": run.public_run_id,
        "internal_id": str(run.id),
        "source": SOURCE_TESTER,
        "status": run.status,
        "strategy_name": run.strategy_name,
        "start_date": _iso(run.start_date),
        "end_date": _iso(run.end_date),
        "universe": run.universe,
        "universe_size": run.universe_size,
        "timeframe": run.timeframe,
        "initial_capital": run.initial_capital,
        "completed_at": _iso(run.completed_at),
        "buy": run.buy_count,
        "watch": run.watch_count,
        "reject": run.reject_count,
        "top_return": summary.get("top_return"),
        "average_return": summary.get("average_return"),
        "label": _run_label(
            SOURCE_TESTER,
            run.public_run_id,
            run.start_date,
            run.end_date,
            run.universe,
            run.timeframe,
        ),
    }


def _lean_preview(job: LeanJobRecord) -> dict[str, Any]:
    req = job.request
    return {
        "run_id": job.job_id,
        "internal_id": job.job_id,
        "source": SOURCE_LEAN,
        "status": str(job.status.value if hasattr(job.status, "value") else job.status),
        "strategy_name": job.strategy_name,
        "start_date": _iso(req.start_date) if req else None,
        "end_date": _iso(req.end_date) if req else None,
        "universe": ",".join(req.symbols[:8]) if req and req.symbols else None,
        "universe_size": len(req.symbols) if req and req.symbols else None,
        "timeframe": req.timeframe if req else None,
        "initial_capital": req.initial_capital if req else None,
        "completed_at": _iso(job.completed_at),
        "buy": None,
        "watch": None,
        "reject": None,
        "top_return": None,
        "average_return": None,
        "label": _run_label(
            SOURCE_LEAN,
            job.job_id,
            req.start_date if req else None,
            req.end_date if req else None,
            None,
            req.timeframe if req else None,
        ),
    }


def _run_label(source: str, run_id: str, start: Any, end: Any, universe: Any, timeframe: Any) -> str:
    prefix = "LEAN" if source == SOURCE_LEAN else "Scan"
    rng = ""
    if start and end:
        rng = f"{_iso(start)} → {_iso(end)}"
    extra = " · ".join(p for p in (universe, timeframe) if p)
    parts = [prefix, rng or run_id]
    if extra:
        parts.append(str(extra))
    return " · ".join(parts)


async def _completed_tester_runs(
    user_id: uuid.UUID,
    *,
    strategy_id: uuid.UUID | None = None,
    strategy_name: str | None = None,
    limit: int = 100,
) -> list[StrategyTestRun]:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(StrategyTestRun)
            .where(StrategyTestRun.user_id == user_id)
            .where(func.lower(StrategyTestRun.status) == "completed")
            .order_by(StrategyTestRun.completed_at.desc(), StrategyTestRun.started_at.desc())
            .limit(limit)
        )
        clauses = []
        if strategy_id is not None:
            clauses.append(StrategyTestRun.strategy_definition_id == strategy_id)
        if strategy_name:
            clauses.append(func.lower(StrategyTestRun.strategy_name) == strategy_name.strip().lower())
        if clauses:
            stmt = stmt.where(or_(*clauses))
        return list((await db.scalars(stmt)).all())


async def catalog(user_id: uuid.UUID) -> dict[str, Any]:
    rows = await persistence.list_definitions(user_id)
    runs = await _completed_tester_runs(user_id, limit=200)
    jobs = [j for j in _lean_jobs(user_id) if j.status == LeanJobStatus.COMPLETED and j.result]

    by_def: dict[str, int] = defaultdict(int)
    by_name: dict[str, int] = defaultdict(int)
    latest: dict[str, dict[str, Any]] = {}
    latest_by_name: dict[str, dict[str, Any]] = {}
    for run in runs:
        key = str(run.strategy_definition_id) if run.strategy_definition_id else ""
        name_key = (run.strategy_name or "").strip().lower()
        preview = _run_preview(run)
        if key:
            by_def[key] += 1
            latest.setdefault(key, preview)
        if name_key:
            by_name[name_key] += 1
            latest_by_name.setdefault(name_key, preview)

    lean_by_name: dict[str, int] = defaultdict(int)
    lean_by_id: dict[str, int] = defaultdict(int)
    for job in jobs:
        lean_by_id[str(job.strategy_id)] += 1
        lean_by_name[str(job.strategy_name or "").strip().lower()] += 1

    strategies = []
    seen: set[str] = set()
    for row in rows:
        if row.is_preset:
            continue
        name_key = (row.name or "").strip().lower()
        if not name_key or name_key in seen:
            continue
        seen.add(name_key)
        sid = str(row.id)
        run_count = by_def.get(sid, 0) or by_name.get(name_key, 0)
        lean_count = lean_by_id.get(sid, 0) or lean_by_name.get(name_key, 0)
        strategies.append(
            {
                "id": sid,
                "name": row.name,
                "description": row.description,
                "version": row.version,
                "updated_at": _iso(row.updated_at),
                "completed_run_count": run_count,
                "completed_lean_count": lean_count,
                "latest_run": latest.get(sid) or latest_by_name.get(name_key),
                "has_pine": bool(
                    isinstance(row.config, dict)
                    and isinstance(row.config.get("source"), dict)
                    and (row.config["source"].get("pine_code") or row.config["source"].get("pineCode"))
                ),
            }
        )
    suggestions: list[dict[str, Any]] = []
    with_runs = [s for s in strategies if (s["completed_run_count"] or s["completed_lean_count"])]
    for index in range(len(with_runs) - 1):
        left, right = with_runs[index], with_runs[index + 1]
        suggestions.append(
            {
                "title": f"{left['name']} vs {right['name']}",
                "subtitle": "Completed Strategy Tester / LEAN runs",
                "strategy_ids": [left["id"], right["id"]],
                "names": [left["name"], right["name"]],
            }
        )
        if len(suggestions) >= 4:
            break
    return {
        "strategies": strategies,
        "suggestions": suggestions,
        "min_slots": MIN_SLOTS,
        "max_slots": MAX_SLOTS,
        "strategy_count": len(strategies),
    }


async def list_runs_for_strategy(user_id: uuid.UUID, strategy_id: str) -> dict[str, Any]:
    definition = await persistence.get_definition(uuid.UUID(str(strategy_id)))
    if definition is None or (definition.user_id is not None and definition.user_id != user_id):
        raise CompareError("Strategy not found", 404)
    runs = await _completed_tester_runs(
        user_id,
        strategy_id=definition.id,
        strategy_name=definition.name,
        limit=100,
    )
    items = [_run_preview(run) for run in runs]
    for job in _lean_jobs(user_id):
        if job.status != LeanJobStatus.COMPLETED or not job.result:
            continue
        if _lean_matches_strategy(job, str(definition.id), definition.name):
            items.append(_lean_preview(job))
    items.sort(key=lambda r: r.get("completed_at") or "", reverse=True)
    return {
        "strategy_id": str(definition.id),
        "strategy_name": definition.name,
        "runs": items,
    }


def _trades_from_lean(job: LeanJobRecord) -> list[dict[str, Any]]:
    if not job.result:
        return []
    out = []
    for trade in job.result.trades:
        td = trade.model_dump(by_alias=True) if hasattr(trade, "model_dump") else dict(trade)
        out.append(
            {
                "symbol": td.get("symbol"),
                "entry_date": td.get("entryDate") or td.get("entry_date"),
                "exit_date": td.get("exitDate") or td.get("exit_date"),
                "entry_price": _num(td.get("entryPrice") or td.get("entry_price")),
                "exit_price": _num(td.get("exitPrice") or td.get("exit_price")),
                "quantity": td.get("quantity"),
                "direction": td.get("direction"),
                "net_pnl": _num(td.get("netPnL") or td.get("net_pnl")),
                "return_pct": _num(td.get("returnPct") or td.get("return_pct")),
                "holding_period": td.get("holdingPeriod") if td.get("holdingPeriod") is not None else td.get("holding_period"),
                "exit_reason": td.get("exitReason") or td.get("exit_reason"),
                "entry_reason": td.get("entryReason") or td.get("entry_reason"),
            }
        )
    return out


def _trades_from_results(
    results: list[StrategyTestResult],
    *,
    start_date: Any,
    end_date: Any,
    exit_rule: str | None,
    side: str,
) -> list[dict[str, Any]]:
    window = None
    if start_date and end_date:
        window = f"{_iso(start_date)} → {_iso(end_date)}"
    trades = []
    for row in results:
        if row.return_pct is None and row.entry_price is None:
            continue
        if row.status and str(row.status).lower() not in {"ok", "completed", ""}:
            continue
        trades.append(
            {
                "symbol": row.symbol,
                "entry_date": _iso(start_date),
                "exit_date": _iso(end_date),
                "entry_price": _num(row.entry_price),
                "exit_price": _num(row.exit_price),
                "quantity": None,
                "direction": side,
                "net_pnl": None,
                "return_pct": _num(row.return_pct),
                "holding_period": None,
                "holding_window": window,
                "exit_reason": exit_rule,
                "entry_reason": row.signal,
            }
        )
    return trades


def _apply_equity_averages(metrics: dict[str, Any], equity: list[dict[str, Any]]) -> dict[str, Any]:
    cashes = [p.get("cash") for p in equity if p.get("cash") is not None]
    invested = [p.get("invested") for p in equity if p.get("invested") is not None]
    if cashes:
        metrics["avg_cash"] = _round(sum(cashes) / len(cashes), 2)
    initial = _num(metrics.get("initial_capital"))
    if invested and initial and initial > 0:
        metrics["avg_exposure_pct"] = _round(sum(float(v) / initial * 100.0 for v in invested) / len(invested), 4)
    return metrics


def _equity_from_lean(job: LeanJobRecord) -> list[dict[str, Any]]:
    if not job.result:
        return []
    points = []
    for pt in job.result.equity_curve:
        data = pt.model_dump(by_alias=True) if hasattr(pt, "model_dump") else dict(pt)
        points.append(
            {
                "date": str(data.get("date") or "")[:10],
                "equity": _num(data.get("equity")),
                "cash": _num(data.get("cash")),
                "invested": _num(data.get("investedCapital") or data.get("invested_capital") or data.get("invested")),
                "drawdown": _num(data.get("drawdown")),
                "drawdown_pct": _num(data.get("drawdownPct") or data.get("drawdown_pct")),
            }
        )
    return points


async def _load_tester_slot(
    user_id: uuid.UUID,
    strategy: StrategyDefinition,
    run_id: str,
    slot_id: str,
) -> dict[str, Any]:
    run = await persistence.get_run(run_id)
    if run is None:
        raise CompareError(f"Backtest run {run_id} was not found", 404)
    if run.user_id is not None and run.user_id != user_id:
        raise CompareError(f"Backtest run {run_id} was not found", 404)
    belongs = False
    if run.strategy_definition_id and run.strategy_definition_id == strategy.id:
        belongs = True
    elif (run.strategy_name or "").strip().lower() == (strategy.name or "").strip().lower():
        belongs = True
    if not belongs:
        raise CompareError(f"Run {run.public_run_id} does not belong to this strategy", 400)
    if str(run.status).lower() != "completed":
        raise CompareError(f"Run {run.public_run_id} is not completed", 400)
    results = await persistence.all_result_rows(run.id)
    snapshot = run.strategy_snapshot if isinstance(run.strategy_snapshot, dict) else (strategy.config or {})
    logic = extract_logic(snapshot)
    metrics = metrics_from_strategy_run(run, results)
    signals = [
        {
            "symbol": row.symbol,
            "signal": row.signal,
            "return_pct": _num(row.return_pct),
            "entry_price": _num(row.entry_price),
            "exit_price": _num(row.exit_price),
        }
        for row in results
        if row.symbol
    ]
    pos = snapshot.get("position_rules") if isinstance(snapshot.get("position_rules"), dict) else {}
    exit_rule = pos.get("exit_rule")
    if not exit_rule:
        exits = logic.get("exit_conditions") or []
        exit_rule = exits[0] if exits else "Window End"
    trades = _trades_from_results(
        results,
        start_date=run.start_date,
        end_date=run.end_date,
        exit_rule=str(exit_rule),
        side=logic.get("position_type") or "LONG",
    )
    commission = snapshot.get("commission") if snapshot.get("commission") is not None else snapshot.get("commission_rate")
    slippage = snapshot.get("slippage") if snapshot.get("slippage") is not None else snapshot.get("slippage_rate")
    config = extract_config(
        universe=run.universe,
        universe_size=run.universe_size,
        timeframe=run.timeframe,
        start_date=run.start_date,
        end_date=run.end_date,
        initial_capital=run.initial_capital,
        commission=commission,
        slippage=slippage,
        position_type=logic.get("position_type"),
        source=SOURCE_TESTER,
    )
    summary = run.summary if isinstance(run.summary, dict) else {}
    return {
        "slot_id": slot_id,
        "strategy_id": str(strategy.id),
        "strategy_name": run.strategy_name or strategy.name,
        "description": strategy.description,
        "run_id": run.public_run_id,
        "source": SOURCE_TESTER,
        "status": run.status,
        "logic": logic,
        "metrics": metrics,
        "config": config,
        "signals": signals,
        "trades": trades,
        "equity_curve": [],
        "drawdown_curve": [],
        "monthly_returns": [],
        "yearly_returns": [],
        "trade_distribution": trade_distribution([t.get("return_pct") for t in trades]),
        "scan_summary": {
            "buy": run.buy_count,
            "watch": run.watch_count,
            "reject": run.reject_count,
            "universe_size": run.universe_size,
            "average_return": summary.get("average_return"),
        },
    }


def _load_lean_slot(strategy: StrategyDefinition, run_id: str, slot_id: str) -> dict[str, Any]:
    job = LeanBacktestService.get_job(run_id)
    if job is None or job.status != LeanJobStatus.COMPLETED or not job.result:
        raise CompareError(f"LEAN backtest {run_id} was not found or is not completed", 404)
    snapshot = strategy.config if isinstance(strategy.config, dict) else {}
    logic = extract_logic(snapshot)
    trades = _trades_from_lean(job)
    equity = _equity_from_lean(job)
    periods = monthly_yearly_from_equity(equity)
    req = job.request
    symbols = list(req.symbols) if req else []
    universe = None
    universe_size = len(symbols) if symbols else None
    if symbols and len(symbols) == 1 and symbols[0] in {"ALL_755", "ALL", "NIFTY500", "ALL_STOCKS"}:
        universe = symbols[0]
    elif symbols:
        universe = f"{len(symbols)} symbols"
    config = extract_config(
        universe=universe,
        universe_size=universe_size,
        timeframe=req.timeframe if req else None,
        start_date=req.start_date if req else job.result.start_date,
        end_date=req.end_date if req else job.result.end_date,
        initial_capital=req.initial_capital if req else None,
        commission=req.commission_rate if req else None,
        slippage=req.slippage_rate if req else None,
        position_type=logic.get("position_type"),
        source=SOURCE_LEAN,
    )
    return {
        "slot_id": slot_id,
        "strategy_id": str(strategy.id),
        "strategy_name": job.strategy_name or strategy.name,
        "description": strategy.description,
        "run_id": job.job_id,
        "source": SOURCE_LEAN,
        "status": str(job.status.value if hasattr(job.status, "value") else job.status),
        "logic": logic,
        "metrics": _apply_equity_averages(metrics_from_lean(job.result.summary, job.result.trades), equity),
        "config": config,
        "signals": [],
        "trades": trades,
        "equity_curve": equity,
        "drawdown_curve": [
            {"date": p["date"], "drawdown": p.get("drawdown"), "drawdown_pct": p.get("drawdown_pct")}
            for p in equity
        ],
        "monthly_returns": periods["monthly"],
        "yearly_returns": periods["yearly"],
        "trade_distribution": trade_distribution([t.get("return_pct") for t in trades]),
        "scan_summary": None,
    }


async def compare_slots(user_id: uuid.UUID, slots_in: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(slots_in, list):
        raise CompareError("slots must be a list")
    if len(slots_in) < MIN_SLOTS or len(slots_in) > MAX_SLOTS:
        raise CompareError(f"Select {MIN_SLOTS}–{MAX_SLOTS} strategies to compare")

    seen_runs: set[tuple[str, str]] = set()
    loaded: list[dict[str, Any]] = []
    for index, raw in enumerate(slots_in):
        strategy_id = str(raw.get("strategy_id") or "").strip()
        run_id = str(raw.get("run_id") or "").strip()
        if not strategy_id or not run_id:
            raise CompareError("Each slot needs a strategy_id and run_id")
        source = _detect_source(run_id, raw.get("source"))
        key = (source, run_id)
        if key in seen_runs:
            raise CompareError("Each selected run can only appear once")
        seen_runs.add(key)
        try:
            definition = await persistence.get_definition(uuid.UUID(strategy_id))
        except (ValueError, TypeError) as exc:
            raise CompareError("Invalid strategy_id") from exc
        if definition is None or (definition.user_id is not None and definition.user_id != user_id):
            raise CompareError("Strategy not found", 404)
        slot_id = f"s{index}"
        if source == SOURCE_LEAN:
            loaded.append(_load_lean_slot(definition, run_id, slot_id))
        else:
            loaded.append(await _load_tester_slot(user_id, definition, run_id, slot_id))

    warnings = config_mismatches([s["config"] for s in loaded])
    sources = {s.get("source") for s in loaded}
    if len(sources) > 1:
        warnings.insert(
            0,
            {
                "field": "source",
                "label": "Run type",
                "values": [s.get("source") for s in loaded],
                "message": "Selected runs mix Strategy Tester scans and LEAN backtests. Metrics are not like-for-like.",
                "missing_on_some": False,
            },
        )
    aligned = not warnings

    trade_symbols: set[str] = set()
    for slot in loaded:
        for trade in slot.get("trades") or []:
            if trade.get("symbol"):
                trade_symbols.add(str(trade["symbol"]).upper())
    trade_rows = []
    for symbol in sorted(trade_symbols):
        per_slot: dict[str, Any] = {}
        for slot in loaded:
            matches = [t for t in (slot.get("trades") or []) if str(t.get("symbol") or "").upper() == symbol]
            per_slot[slot["slot_id"]] = matches[0] if matches else None
        trade_rows.append({"symbol": symbol, "by_slot": per_slot})

    return {
        "slot_count": len(loaded),
        "aligned_config": aligned,
        "config_warnings": warnings,
        "slots": loaded,
        "radar": radar_profile(loaded),
        "signals": signal_comparison(loaded),
        "trades": {
            "symbols": trade_rows[:2000],
            "symbol_count": len(trade_rows),
        },
        "has_equity": any(s.get("equity_curve") for s in loaded),
        "has_pine": any((s.get("logic") or {}).get("pine_code") for s in loaded),
    }
