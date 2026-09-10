"""Parse the bundled NIFTY 500 membership CSV.

The file is the authoritative *membership* source for the 755-name universe.
Some historical exports mixed comma-delimited rows with tab-collapsed rows
(the entire record stuffed into ``Company Name``). This parser recovers both
shapes so company names/symbols are not lost, without inventing tickers.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Iterable

from ..utils.symbol import canonical_symbol

logger = logging.getLogger("app.services.universe")

CSV_FIELDS = ("Company Name", "Industry", "Symbol", "Series", "ISIN Code")


def is_dummy_universe_symbol(symbol: str | None) -> bool:
    """Placeholder tickers (DUMMY*) are not part of the investable NSE universe."""
    raw = (symbol or "").strip().upper()
    if not raw:
        return False
    canon = canonical_symbol(raw) or raw
    return canon.startswith("DUMMY") or raw.startswith("DUMMY")


def parse_nifty500_row(row: dict[str, Any] | None) -> dict[str, str] | None:
    """Return a normalized CSV membership row, or None if no symbol is present."""
    if not row:
        return None

    company = str(row.get("Company Name") or row.get("company_name") or "").strip()
    industry = str(row.get("Industry") or row.get("industry") or "").strip()
    symbol = str(row.get("Symbol") or row.get("symbol") or "").strip().upper()
    series = str(row.get("Series") or row.get("series") or "").strip().upper()
    isin = str(row.get("ISIN Code") or row.get("isin") or "").strip().upper()

    if not symbol and "\t" in company:
        parts = [part.strip() for part in company.split("\t")]
        if len(parts) >= 3 and parts[2]:
            company = parts[0]
            industry = parts[1]
            symbol = parts[2].upper()
            series = parts[3].upper() if len(parts) > 3 else series
            isin = parts[4].upper() if len(parts) > 4 else isin
            logger.info(
                "SYMBOL_MAPPING_RECOVERED | reason=tab_collapsed_csv_row | symbol=%s | company_name=%s",
                symbol,
                company,
            )

    if not symbol:
        return None
    if is_dummy_universe_symbol(symbol):
        return None

    return {
        "symbol": symbol,
        "canonical_symbol": canonical_symbol(f"{symbol}-{series}" if series else symbol) or symbol,
        "company_name": company,
        "industry": industry,
        "series": series,
        "isin": isin,
    }


def iter_nifty500_csv_rows(csv_path: Path) -> Iterable[dict[str, str]]:
    if not csv_path.exists():
        logger.warning("SYMBOL_MISSING | reason=csv_not_found | path=%s", csv_path)
        return []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            parsed = parse_nifty500_row(row)
            if parsed:
                yield parsed


def load_unique_nifty500_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    """Unique membership rows keyed by canonical symbol, first-seen wins."""
    unique: dict[str, dict[str, str]] = {}
    duplicates = 0
    for parsed in iter_nifty500_csv_rows(csv_path):
        key = parsed["canonical_symbol"]
        if key in unique:
            duplicates += 1
            continue
        unique[key] = parsed
    if duplicates:
        logger.info(
            "SYMBOL_DUPLICATE_DETECTED | source=csv | duplicate_rows_skipped=%s | unique=%s",
            duplicates,
            len(unique),
        )
    return list(unique.values())
