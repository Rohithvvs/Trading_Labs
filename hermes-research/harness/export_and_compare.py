"""Read-only TV vs Trading Labs trade export and comparison.

Does not modify the backtesting engine. Allowed without approval.
Writes artifacts under hermes-research/runs/<utc_timestamp>/.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

REF = ROOT / "hermes-research" / "tradingview_reference" / "Strategy_001"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
# One tick: XLSX Properties tick size 0.10. Covers TV list vs chart-open *.x5 ties.
PRICE_TOL = 0.10
PNL_TOL = 0.10
COMPARE_EPS = 1e-9


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n):
        return None
    return n


def parse_tv_trades(path: Path) -> list[dict[str, Any]]:
    by_num: dict[int, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            n = int(row["Trade number"])
            rec = by_num.setdefault(
                n,
                {
                    "trade_number": n,
                    "direction": "LONG",
                    "entry_dt": None,
                    "entry_price": None,
                    "entry_qty": None,
                    "exit_dt": None,
                    "exit_price": None,
                    "exit_qty": None,
                    "gross_pnl": None,
                    "commission": None,
                    "slippage": 0.0,
                    "net_pnl": None,
                    "return_pct": None,
                    "exit_reason": None,
                    "entry_signal": None,
                    "duration_bars": None,
                    "mae": None,
                    "mfe": None,
                    "cumulative_pnl": None,
                },
            )
            typ = (row.get("Type") or "").strip()
            dt = (row.get("Date and time") or "").strip()
            price = _f(row.get("Price INR"))
            qty = _f(row.get("Size (qty)"))
            net = _f(row.get("Net PnL INR"))
            comm = _f(row.get("Commission INR"))
            dur = row.get("Duration (bars)")
            if typ.lower().startswith("entry"):
                rec["entry_dt"] = dt
                rec["entry_price"] = price
                rec["entry_qty"] = qty
                rec["entry_signal"] = (row.get("Signal") or "").strip()
                rec["direction"] = "LONG" if "long" in typ.lower() else "SHORT"
            elif typ.lower().startswith("exit"):
                rec["exit_dt"] = dt
                rec["exit_price"] = price
                rec["exit_qty"] = qty
                rec["exit_reason"] = (row.get("Signal") or "").strip()
            if net is not None:
                rec["net_pnl"] = net
                rec["gross_pnl"] = net if comm in (None, 0.0) else (net + comm)
            if comm is not None:
                rec["commission"] = comm
            rec["return_pct"] = _f(row.get("Return %"))
            rec["mae"] = _f(row.get("Adverse excursion INR"))
            rec["mfe"] = _f(row.get("Favorable excursion INR"))
            rec["cumulative_pnl"] = _f(row.get("Cumulative PnL INR"))
            if dur not in (None, ""):
                try:
                    rec["duration_bars"] = int(float(dur))
                except ValueError:
                    rec["duration_bars"] = dur
    return [by_num[k] for k in sorted(by_num)]


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out: list[str] = []
    for si in root.findall("m:si", NS):
        texts = [t.text or "" for t in si.findall(".//m:t", NS)]
        out.append("".join(texts))
    return out


def _xlsx_sheet_rows(zf: zipfile.ZipFile, sheet: str, shared: list[str]) -> list[list[str]]:
    path = f"xl/worksheets/{sheet}"
    root = ET.fromstring(zf.read(path))
    rows: list[list[str]] = []
    for row in root.findall("m:sheetData/m:row", NS):
        cells: list[str] = []
        for c in row.findall("m:c", NS):
            t = c.get("t")
            v = c.find("m:v", NS)
            if v is None or v.text is None:
                cells.append("")
                continue
            if t == "s":
                cells.append(shared[int(v.text)])
            else:
                cells.append(v.text)
        rows.append(cells)
    return rows


def parse_tv_xlsx(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        shared = _xlsx_shared_strings(zf)
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets = []
        for sh in wb.findall("m:sheets/m:sheet", NS):
            sheets.append(sh.get("name"))
        # Standard TV export order: sheet1 Performance, 2 Trades analysis,
        # 3 Risk-adjusted, 4 Trades, 5 Properties — names already audited.
        perf = _xlsx_sheet_rows(zf, "sheet1.xml", shared)
        analysis = _xlsx_sheet_rows(zf, "sheet2.xml", shared)
        risk = _xlsx_sheet_rows(zf, "sheet3.xml", shared)
        props = _xlsx_sheet_rows(zf, "sheet5.xml", shared)

    def kv_map(rows: list[list[str]]) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in rows:
            if len(row) >= 2 and row[0]:
                out[row[0].strip()] = row[1].strip() if len(row) > 1 else ""
            if len(row) >= 3 and row[0] and row[2] and row[0] not in out:
                out[row[0].strip()] = row[2].strip()
        return out

    return {
        "sheet_names": sheets,
        "performance_pairs": kv_map(perf),
        "trades_analysis_pairs": kv_map(analysis),
        "risk_pairs": kv_map(risk),
        "properties_pairs": kv_map(props),
        "performance_raw_head": perf[:40],
        "analysis_raw_head": analysis[:40],
        "risk_raw_head": risk[:40],
        "properties_raw_head": props[:40],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


TV_FIELDS = [
    "trade_number",
    "direction",
    "entry_dt",
    "entry_price",
    "entry_qty",
    "exit_dt",
    "exit_price",
    "exit_qty",
    "gross_pnl",
    "commission",
    "slippage",
    "net_pnl",
    "return_pct",
    "exit_reason",
    "entry_signal",
    "duration_bars",
]


def classify_fill(price: float | None, bar: dict[str, float | None], tol: float = 0.01) -> str:
    if price is None:
        return "no_price"
    hits = []
    for name in ("open", "high", "low", "close"):
        v = bar.get(name)
        if v is not None and abs(float(price) - float(v)) <= tol:
            hits.append(name)
    if not hits:
        return "unmatched"
    return "+".join(hits)


def summarize_tv(trades: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [t["net_pnl"] for t in trades if t.get("net_pnl") is not None]
    wins = [p for p in nets if p > 0]
    losses = [p for p in nets if p < 0]
    even = [p for p in nets if p == 0]
    durs = [t["duration_bars"] for t in trades if isinstance(t.get("duration_bars"), int)]
    qtys = {t.get("entry_qty") for t in trades}
    comms = {t.get("commission") for t in trades}
    dirs = {t.get("direction") for t in trades}
    signals = Counter(t.get("entry_signal") for t in trades)
    reasons = Counter(t.get("exit_reason") for t in trades)
    dur_c = Counter(durs)
    gp = sum(p for p in nets if p > 0)
    gl = abs(sum(p for p in nets if p < 0))
    return {
        "total_trades": len(trades),
        "winners": len(wins),
        "losers": len(losses),
        "even": len(even),
        "net_profit": round(sum(nets), 6) if nets else None,
        "gross_profit": round(gp, 6),
        "gross_loss": round(gl, 6),
        "profit_factor": round(gp / gl, 6) if gl else None,
        "avg_trade": round(sum(nets) / len(nets), 6) if nets else None,
        "win_rate": round(100.0 * len(wins) / len(trades), 4) if trades else None,
        "duration_counts": dict(dur_c),
        "unique_qty": sorted(q for q in qtys if q is not None),
        "unique_commission": sorted(c for c in comms if c is not None),
        "directions": sorted(d for d in dirs if d),
        "entry_signals": dict(signals),
        "exit_reasons": dict(reasons),
        "first_entry": trades[0]["entry_dt"] if trades else None,
        "last_exit": trades[-1]["exit_dt"] if trades else None,
    }


async def load_ohlc(symbol: str) -> list[dict[str, Any]]:
    from app.services.market_data_ingestion.repository import fetch_equity_history

    rows = await fetch_equity_history(symbol)
    out = []
    for r in rows:
        d = _as_date(r.get("trade_date"))
        if d is None:
            continue
        out.append(
            {
                "date": d,
                "open": _f(r.get("open")),
                "high": _f(r.get("high")),
                "low": _f(r.get("low")),
                "close": _f(r.get("close")),
                "volume": _f(r.get("volume")),
            }
        )
    out.sort(key=lambda x: x["date"])
    return out


def tv_session_calendar(
    trades: list[dict[str, Any]],
    *,
    ohlc_dates: list[date] | None = None,
) -> set[date]:
    """Union of golden entry/exit dates, plus the CSV bar before the first entry."""
    out: set[date] = set()
    for t in trades:
        for key in ("entry_dt", "exit_dt"):
            d = _as_date(t.get(key))
            if d is not None:
                out.add(d)
    if not ohlc_dates or not trades:
        return out
    first_entry = _as_date(trades[0].get("entry_dt"))
    from app.services.strategies.breakout52w.tv_ohlc_csv import expand_tv_session_calendar

    return expand_tv_session_calendar(out, ohlc_dates, first_entry=first_entry)


async def run_tl_backtest(
    symbol: str,
    profile: str,
    start: date,
    end: date,
    capital: float,
    *,
    session_dates: set[date] | None = None,
) -> dict[str, Any]:
    from app.services.strategies.breakout52w.window_backtest import run_symbol_window_backtest

    kwargs: dict[str, Any] = {}
    if session_dates is not None and profile.upper() in {"TV_TESTER", "TEST_TAPE", "TV_TEST"}:
        kwargs["session_dates"] = session_dates
    return await run_symbol_window_backtest(
        symbol,
        window="ALL",
        asof=end,
        start=start,
        end=end,
        initial_capital=capital,
        execution_profile=profile,
        **kwargs,
    )


def tl_trades_from_dashboard(dash: dict[str, Any]) -> list[dict[str, Any]]:
    raw = dash.get("trades") or []
    out: list[dict[str, Any]] = []
    n = 0
    for t in raw:
        if t.get("open"):
            continue
        n += 1
        entry_p = _f(t.get("entry_price"))
        exit_p = _f(t.get("exit_price"))
        qty = _f(t.get("shares") if t.get("shares") is not None else t.get("quantity"))
        net = _f(t.get("net_pnl"))
        comm = _f(t.get("commission")) or 0.0
        slip = _f(t.get("slippage")) or 0.0
        gross = _f(t.get("gross_pnl"))
        if gross is None and entry_p is not None and exit_p is not None and qty is not None:
            gross = qty * (exit_p - entry_p)
        if net is None and gross is not None:
            net = gross - comm - slip
        out.append(
            {
                "trade_number": n,
                "direction": (t.get("direction") or "LONG").upper(),
                "entry_dt": t.get("entry_date") or t.get("entry_fill_time"),
                "entry_price": entry_p,
                "entry_qty": qty,
                "exit_dt": t.get("exit_date") or t.get("exit_fill_time"),
                "exit_price": exit_p,
                "exit_qty": qty,
                "gross_pnl": gross,
                "commission": comm,
                "slippage": slip,
                "net_pnl": net,
                "return_pct": _f(t.get("pnl_pct")),
                "exit_reason": t.get("exit_reason") or t.get("reason"),
                "entry_signal": "BuySignal",
                "duration_bars": t.get("holding_period"),
                "symbol": t.get("symbol"),
            }
        )
    return out


def first_divergence(tv: list[dict[str, Any]], tl: list[dict[str, Any]]) -> dict[str, Any]:
    n = max(len(tv), len(tl))
    lines: list[str] = []
    found = None
    for i in range(n):
        a = tv[i] if i < len(tv) else None
        b = tl[i] if i < len(tl) else None
        num = i + 1
        if a is None:
            found = {
                "trade_number": num,
                "kind": "TL_EXTRA_TRADE",
                "tv": None,
                "tl": b,
                "suspected_cause": "Trading Labs emitted a trade with no TV counterpart at this index",
            }
            lines.append(f"Trade {num}: TL EXTRA TRADE (TV list exhausted)")
            break
        if b is None:
            found = {
                "trade_number": num,
                "kind": "TL_MISSING_TRADE",
                "tv": a,
                "tl": None,
                "suspected_cause": "Trading Labs has no trade at this index; TV does",
            }
            lines.append(f"Trade {num}: TL MISSING TRADE")
            break
        diffs = []
        if a.get("direction") != b.get("direction"):
            diffs.append("DIRECTION")
        if abs((a.get("entry_price") or 0) - (b.get("entry_price") or 0)) > PRICE_TOL + COMPARE_EPS:
            diffs.append("ENTRY PRICE")
        if abs((a.get("exit_price") or 0) - (b.get("exit_price") or 0)) > PRICE_TOL + COMPARE_EPS:
            diffs.append("EXIT PRICE")
        if str(a.get("entry_dt") or "")[:10] != str(b.get("entry_dt") or "")[:10]:
            diffs.append("ENTRY DATE")
        if str(a.get("exit_dt") or "")[:10] != str(b.get("exit_dt") or "")[:10]:
            diffs.append("EXIT DATE")
        aq, bq = a.get("entry_qty"), b.get("entry_qty")
        if aq is not None and bq is not None and abs(float(aq) - float(bq)) > 1e-9:
            diffs.append("QTY")
        an, bn = a.get("net_pnl"), b.get("net_pnl")
        if an is not None and bn is not None and abs(float(an) - float(bn)) > PNL_TOL + COMPARE_EPS:
            diffs.append("NET PNL")
        if diffs:
            found = {
                "trade_number": num,
                "kind": "+".join(diffs),
                "tv": a,
                "tl": b,
                "suspected_cause": None,
            }
            lines.append(f"Trade {num}: {' DIFFERENCE / '.join(diffs)} DIFFERENCE")
            break
        lines.append(f"Trade {num}: MATCH")
    return {"scan_lines": lines, "divergence": found}


def md_dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


async def main() -> int:
    run_id = utc_stamp()
    out_dir = ROOT / "hermes-research" / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    tv_trades = parse_tv_trades(REF / "trades.csv")
    write_csv(out_dir / "tv_trades_normalized.csv", tv_trades, TV_FIELDS)
    tv_summary = summarize_tv(tv_trades)
    xlsx = parse_tv_xlsx(REF / "strategy_report.xlsx")

    import yaml

    cfg = yaml.safe_load((REF / "test_config.yaml").read_text(encoding="utf-8"))

    tl_error = None
    tl_kernel: dict[str, Any] = {}
    tl_tvcompat: dict[str, Any] = {}
    tl_tester: dict[str, Any] = {}
    tl_trades: list[dict[str, Any]] = []
    ohlc: list[dict[str, Any]] = []
    fill_stats: dict[str, Any] = {}
    ohlc_span: dict[str, Any] = {}

    try:
        import asyncio  # noqa: F401
        from app.config.settings import settings  # noqa: F401

        fyers = await load_ohlc("WELCORP-EQ")
        cfg_start = date.fromisoformat(str(cfg["backtest"]["start_date"]))
        cfg_end = date.fromisoformat(str(cfg["backtest"]["end_date"]))
        kernel_start, kernel_end = cfg_start, cfg_end
        if fyers:
            kernel_start = max(cfg_start, fyers[0]["date"])
            kernel_end = min(cfg_end, fyers[-1]["date"])

        from app.services.strategies.breakout52w.tv_ohlc_csv import (
            parse_tv_ohlc_csv,
            resolve_tv_tester_ohlc_csv,
        )

        tv_csv = resolve_tv_tester_ohlc_csv("TV_TESTER")
        tv_bars: list[dict[str, Any]] = []
        if tv_csv is not None:
            tv_bars = [
                {
                    "date": r["trade_date"],
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "volume": r["volume"],
                }
                for r in parse_tv_ohlc_csv(tv_csv)
            ]
        # TV_TESTER window follows the golden CSV; KERNEL/TV_COMPAT stay on FYERS.
        tester_start, tester_end = cfg_start, cfg_end
        ohlc = tv_bars or fyers
        if tv_bars:
            tester_start = max(cfg_start, tv_bars[0]["date"])
            tester_end = min(cfg_end, tv_bars[-1]["date"])
        elif fyers:
            tester_start, tester_end = kernel_start, kernel_end
        ohlc_by_date = {r["date"]: r for r in ohlc}
        ohlc_span = {
            "symbol": "WELCORP-EQ",
            "source": "tv_ohlc_csv" if tv_bars else "daily_ohlcv",
            "path": str(tv_csv) if tv_csv else None,
            "rows": len(ohlc),
            "min": ohlc[0]["date"].isoformat() if ohlc else None,
            "max": ohlc[-1]["date"].isoformat() if ohlc else None,
            "kernel_span": {
                "min": fyers[0]["date"].isoformat() if fyers else None,
                "max": fyers[-1]["date"].isoformat() if fyers else None,
            },
        }
        capital = float(cfg["capital"]["initial_capital"])
        sessions = tv_session_calendar(
            tv_trades,
            ohlc_dates=[r["date"] for r in tv_bars] if tv_bars else None,
        )
        tl_kernel = await run_tl_backtest(
            "WELCORP-EQ", "KERNEL", kernel_start, kernel_end, capital
        )
        tl_tvcompat = await run_tl_backtest(
            "WELCORP-EQ", "TV_COMPAT", kernel_start, kernel_end, capital
        )
        tl_tester = await run_tl_backtest(
            "WELCORP-EQ",
            "TV_TESTER",
            tester_start,
            tester_end,
            capital,
            session_dates=sessions,
        )
        # Primary comparison profile: approved TV_TESTER tape.
        tl_trades = tl_trades_from_dashboard(tl_tester)
        tl_trades.sort(key=lambda r: str(r.get("entry_dt") or ""))
        for i, row in enumerate(tl_trades, 1):
            row["trade_number"] = i
        write_csv(out_dir / "tl_trades_normalized.csv", tl_trades, TV_FIELDS)
        write_csv(
            out_dir / "tl_trades_kernel_normalized.csv",
            tl_trades_from_dashboard(tl_kernel),
            TV_FIELDS,
        )
        write_csv(
            out_dir / "tl_trades_tvcompat_normalized.csv",
            tl_trades_from_dashboard(tl_tvcompat),
            TV_FIELDS,
        )

        entry_hits: Counter[str] = Counter()
        exit_hits: Counter[str] = Counter()
        overlap = 0
        no_bar = 0
        for t in tv_trades:
            ed = _as_date(t["entry_dt"])
            xd = _as_date(t["exit_dt"])
            if ed is None or ed not in ohlc_by_date:
                no_bar += 1
                continue
            overlap += 1
            entry_hits[classify_fill(t["entry_price"], ohlc_by_date[ed])] += 1
            if xd is not None and xd in ohlc_by_date:
                exit_hits[classify_fill(t["exit_price"], ohlc_by_date[xd])] += 1
            else:
                exit_hits["no_bar"] += 1
        fill_stats = {
            "tv_trades": len(tv_trades),
            "tv_entries_with_labs_bar": overlap,
            "tv_entries_without_labs_bar": no_bar,
            "entry_fill_vs_ohlc": dict(entry_hits),
            "exit_fill_vs_ohlc": dict(exit_hits),
        }
    except Exception as exc:  # noqa: BLE001 — harness must still emit TV artifacts
        tl_error = f"{type(exc).__name__}: {exc}"
        (out_dir / "tl_trades_normalized.csv").write_text(
            ",".join(TV_FIELDS) + "\n", encoding="utf-8"
        )

    div = first_divergence(tv_trades, tl_trades)
    d = div["divergence"]
    (out_dir / "run_meta.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "tv_summary": tv_summary,
                "xlsx_sheet_names": xlsx.get("sheet_names"),
                "test_config": cfg,
                "ohlc_span": ohlc_span,
                "fill_stats": fill_stats,
                "tl_error": tl_error,
                "compare_tolerances": {
                    "price": PRICE_TOL,
                    "pnl": PNL_TOL,
                    "eps": COMPARE_EPS,
                    "note": "one tick (TV Properties tick size 0.10)",
                },
                "match_count": sum(1 for line in div["scan_lines"] if line.endswith("MATCH")),
                "first_divergence": d,
                "tl_kernel_trade_count": (tl_kernel.get("trade_distribution") or {}).get("total_trades")
                if tl_kernel
                else None,
                "tl_tvcompat_trade_count": (tl_tvcompat.get("trade_distribution") or {}).get("total_trades")
                if tl_tvcompat
                else None,
                "tl_tester_trade_count": (tl_tester.get("trade_distribution") or {}).get("total_trades")
                if tl_tester
                else None,
                "tl_kernel_metrics": {
                    k: tl_kernel.get(k)
                    for k in (
                        "total_return",
                        "cagr",
                        "max_drawdown",
                        "win_rate",
                        "trade_count",
                        "profit_factor",
                        "initial_capital",
                        "ending_capital",
                        "unavailable_reason",
                        "period_start",
                        "period_end",
                    )
                }
                if tl_kernel
                else None,
                "tl_tvcompat_metrics": {
                    k: tl_tvcompat.get(k)
                    for k in (
                        "total_return",
                        "cagr",
                        "max_drawdown",
                        "win_rate",
                        "trade_count",
                        "profit_factor",
                        "initial_capital",
                        "ending_capital",
                        "unavailable_reason",
                        "period_start",
                        "period_end",
                    )
                }
                if tl_tvcompat
                else None,
                "tl_tester_metrics": {
                    k: tl_tester.get(k)
                    for k in (
                        "total_return",
                        "cagr",
                        "max_drawdown",
                        "win_rate",
                        "trade_count",
                        "profit_factor",
                        "initial_capital",
                        "ending_capital",
                        "unavailable_reason",
                        "period_start",
                        "period_end",
                    )
                }
                if tl_tester
                else None,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (out_dir / "xlsx_extract.json").write_text(json.dumps(xlsx, indent=2, default=str), encoding="utf-8")
    print(str(out_dir))
    print("tv_trades", len(tv_trades), "tl_trades", len(tl_trades), "tl_error", tl_error)
    print("tolerances price", PRICE_TOL, "pnl", PNL_TOL)
    if d:
        print("FIRST_DIVERGENCE", d.get("kind"), "trade", d.get("trade_number"))
    else:
        print("PASS all", len(tv_trades), "trades MATCH")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
