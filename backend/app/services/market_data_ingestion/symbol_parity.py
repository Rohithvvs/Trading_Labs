"""Compare symbol sets from two candle backends. No I/O and no secrets."""
from __future__ import annotations

from collections.abc import Iterable


def canonical_scan_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if text.endswith("-EQ"):
        text = text[:-3]
    return text


def classify_symbol_sets(
    local_symbols: Iterable[str],
    production_symbols: Iterable[str],
) -> dict[str, list[str]]:
    """Return sorted LOCAL ONLY, PRODUCTION ONLY, and BOTH symbol lists."""
    local = {canonical_scan_symbol(item) for item in local_symbols}
    local.discard("")
    production = {canonical_scan_symbol(item) for item in production_symbols}
    production.discard("")
    return {
        "local_only": sorted(local - production),
        "production_only": sorted(production - local),
        "both": sorted(local & production),
    }
