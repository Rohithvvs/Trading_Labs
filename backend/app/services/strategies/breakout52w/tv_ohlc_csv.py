"""Optional TradingView daily OHLC CSV for the isolated TV_TESTER tape.

KERNEL / TV_COMPAT / the scanner never read this file. The default path is
``hermes-research/tradingview_reference/Strategy_001/ohlc.csv`` and is used
only for WELCORP when ``execution_profile=TV_TESTER``.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

TV_OHLC_CSV_RELATIVE = (
    Path("hermes-research") / "tradingview_reference" / "Strategy_001" / "ohlc.csv"
)
TV_TRADES_CSV_RELATIVE = (
    Path("hermes-research") / "tradingview_reference" / "Strategy_001" / "trades.csv"
)
TV_REFERENCE_TICKERS = frozenset({"WELCORP", "WELCORP-EQ", "NSE:WELCORP"})


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def default_tv_ohlc_csv_path() -> Path:
    return repo_root() / TV_OHLC_CSV_RELATIVE


def default_tv_trades_csv_path() -> Path:
    return repo_root() / TV_TRADES_CSV_RELATIVE


def _canonical_ticker(symbol: str | None) -> str:
    key = (symbol or "").strip().upper()
    if key.startswith("NSE:"):
        key = key[4:]
    if key.endswith("-EQ"):
        key = key[:-3]
    return key


def is_tv_reference_symbol(symbol: str | None) -> bool:
    """True only for the Strategy_001 WELCORP golden reference."""
    if not symbol:
        return False
    raw = symbol.strip().upper()
    if raw in TV_REFERENCE_TICKERS:
        return True
    return _canonical_ticker(symbol) == "WELCORP"


def resolve_tv_tester_ohlc_csv(
    profile: str | None,
    *,
    path: Path | str | None = None,
    symbol: str | None = None,
) -> Path | None:
    """Return a readable CSV path for TV_TESTER, else None (fall back to DB).

    The default Strategy_001 file is WELCORP only. An explicit ``path`` is
    used for tests and harnesses regardless of symbol.
    """
    key = (profile or "").strip().upper()
    if key not in {"TV_TESTER", "TEST_TAPE", "TV_TEST"}:
        return None
    if path is None and symbol is not None and not is_tv_reference_symbol(symbol):
        return None
    candidate = Path(path) if path is not None else default_tv_ohlc_csv_path()
    if candidate.is_file() and candidate.stat().st_size > 0:
        return candidate
    return None


def parse_tv_trades_dates(path: Path | str) -> tuple[set[date], date | None]:
    """Entry/exit session dates and the first entry date from trades.csv."""
    p = Path(path)
    trade_dates: set[date] = set()
    first_entry: date | None = None
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            d = _as_date(raw.get("Date and time") or raw.get("date") or raw.get("time"))
            if d is None:
                continue
            trade_dates.add(d)
            typ = (raw.get("Type") or "").strip().lower()
            if typ.startswith("entry") and (first_entry is None or d < first_entry):
                first_entry = d
    return trade_dates, first_entry


def load_tv_tester_session_dates(
    *,
    symbol: str | None = None,
    trades_csv: Path | str | None = None,
    ohlc_dates: Iterable[date] | None = None,
) -> set[date] | None:
    """TV tester session calendar, or None when the golden trades file is absent."""
    if symbol is not None and not is_tv_reference_symbol(symbol):
        return None
    path = Path(trades_csv) if trades_csv is not None else default_tv_trades_csv_path()
    if not path.is_file() or path.stat().st_size <= 0:
        return None
    trade_dates, first_entry = parse_tv_trades_dates(path)
    if not trade_dates:
        return None
    if ohlc_dates is None:
        return trade_dates
    return expand_tv_session_calendar(trade_dates, ohlc_dates, first_entry=first_entry)


def predecessor_session(ohlc_dates: Iterable[date], entry: date) -> date | None:
    """Last OHLC session strictly before ``entry``, or None."""
    prev = [d for d in ohlc_dates if d < entry]
    return max(prev) if prev else None


def expand_tv_session_calendar(
    trade_dates: set[date],
    ohlc_dates: Iterable[date],
    *,
    first_entry: date | None,
) -> set[date]:
    """Trade entry/exit dates plus the CSV session before the first fill.

    Intra-hold bars are not added, so an 8-bar TV hold stays a jump to the
    next listed exit session.
    """
    out = set(trade_dates)
    if first_entry is not None:
        pred = predecessor_session(ohlc_dates, first_entry)
        if pred is not None:
            out.add(pred)
    return out


def csv_fingerprint(path: Path) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _norm_header(name: str) -> str:
    return "".join(ch for ch in (name or "").strip().lower() if ch.isalnum())


def _header_map(fieldnames: Iterable[str] | None) -> dict[str, str]:
    aliases = {
        "date": {"date", "time", "datetime", "timestamp", "dt"},
        "open": {"open", "openinr"},
        "high": {"high", "highinr"},
        "low": {"low", "lowinr"},
        "close": {"close", "closeinr"},
        "volume": {"volume", "vol"},
    }
    found: dict[str, str] = {}
    for raw in fieldnames or []:
        key = _norm_header(raw)
        for canon, names in aliases.items():
            if key in names and canon not in found:
                found[canon] = raw
    return found


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
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
    return n


def parse_tv_ohlc_csv(path: Path | str) -> list[dict[str, Any]]:
    """Parse a TV/generic daily OHLC CSV. Requires date + open at minimum."""
    p = Path(path)
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = _header_map(reader.fieldnames)
        if "date" not in cols or "open" not in cols:
            raise ValueError(
                f"ohlc.csv must include date and open columns; got {reader.fieldnames}"
            )
        for raw in reader:
            d = _as_date(raw.get(cols["date"]))
            o = _f(raw.get(cols["open"]))
            if d is None or o is None:
                continue
            h = _f(raw.get(cols["high"])) if "high" in cols else o
            low = _f(raw.get(cols["low"])) if "low" in cols else o
            c = _f(raw.get(cols["close"])) if "close" in cols else o
            v = _f(raw.get(cols["volume"])) if "volume" in cols else 0.0
            rows.append(
                {
                    "trade_date": d,
                    "open": float(o),
                    "high": float(h if h is not None else o),
                    "low": float(low if low is not None else o),
                    "close": float(c if c is not None else o),
                    "volume": float(v or 0.0),
                    "source": "tv_ohlc_csv",
                }
            )
    rows.sort(key=lambda r: r["trade_date"])
    return rows


def maps_from_ohlc_rows(
    symbol: str,
    rows: list[dict[str, Any]],
    *,
    start: date | None = None,
    end: date | None = None,
) -> tuple[
    list[date],
    dict[str, dict[date, float]],
    dict[str, dict[date, float]],
    dict[str, dict[date, float]],
    dict[str, dict[date, float]],
    dict[date, float],
    dict[str, dict[date, float]],
]:
    high_m: dict[str, dict[date, float]] = {symbol: {}}
    low_m: dict[str, dict[date, float]] = {symbol: {}}
    close_m: dict[str, dict[date, float]] = {symbol: {}}
    vol_m: dict[str, dict[date, float]] = {symbol: {}}
    open_m: dict[str, dict[date, float]] = {symbol: {}}
    dates: list[date] = []
    for row in rows:
        d = row["trade_date"]
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue
        high_m[symbol][d] = float(row["high"])
        low_m[symbol][d] = float(row["low"])
        close_m[symbol][d] = float(row["close"])
        vol_m[symbol][d] = float(row.get("volume") or 0.0)
        open_m[symbol][d] = float(row["open"])
        dates.append(d)
    dates.sort()
    index: dict[date, float] = {}
    return dates, high_m, low_m, close_m, vol_m, index, open_m
