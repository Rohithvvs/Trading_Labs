# FYERS / NSE series suffixes (NOT hyphens inside the ticker name).
# Hyphenated equity names like BAJAJ-AUTO / NAM-INDIA must still get -EQ.
_EQUITY_SERIES_SUFFIXES = (
    "-EQ",
    "-BE",
    "-BZ",
    "-SM",
    "-ST",
    "-IV",
    "-RR",
    "-BL",
    "-BT",
    "-GC",
)
_INDEX_SUFFIX = "-INDEX"


def canonical_symbol(raw_symbol: str) -> str:
    """
    Normalizes any symbol format to a canonical internal format.
    Strips 'NSE:' or 'BSE:' prefixes.
    Strips equity series suffix (-EQ, -BE, …).
    Maintains '-INDEX' and hyphens that are part of the ticker name.

    Examples:
        'NSE:DATAPATTNS-EQ' -> 'DATAPATTNS'
        'DATAPATTNS-EQ' -> 'DATAPATTNS'
        'BAJAJ-AUTO-EQ' -> 'BAJAJ-AUTO'   # hyphen is part of name
        'nse:datapattns-eq' -> 'DATAPATTNS'
        'NSE:NIFTY50-INDEX' -> 'NIFTY50-INDEX'
    """
    if not raw_symbol:
        return ""

    s = raw_symbol.strip().upper()

    # Strip exchange prefixes
    if s.startswith("NSE:"):
        s = s[4:]
    elif s.startswith("BSE:"):
        s = s[4:]
    elif ":" in s:
        s = s.split(":", 1)[1]

    # Strip equity series suffix only (not mid-name hyphens like BAJAJ-AUTO)
    for suf in _EQUITY_SERIES_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
            break

    return s


def ohlcv_symbol_variants(symbol: str) -> list[str]:
    """Stored forms used by daily_ohlcv / historical_candles for one ticker.

    Scans publish the canonical display name (GLAXO). Strategy bars are stored
    as the universe identity (GLAXO-EQ). Lookup must try both, plus NSE: prefix
    drift, or a 3Y backtest returns 0 sessions for every name.
    """
    raw = (symbol or "").strip()
    if not raw:
        return []
    can = canonical_symbol(raw)
    variants = [
        raw,
        raw.upper(),
        can,
        f"{can}-EQ" if can else "",
        f"NSE:{can}-EQ" if can else "",
        f"NSE:{can}" if can else "",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for item in variants:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def preferred_ohlcv_store_symbol(symbols: list[str]) -> str | None:
    """Pick the daily_ohlcv identity when several alias forms are present."""
    if not symbols:
        return None
    counts: dict[str, int] = {}
    for item in symbols:
        if item:
            counts[item] = counts.get(item, 0) + 1
    if not counts:
        return None

    def score(item: str) -> tuple[int, int, int]:
        universe_eq = 1 if item.endswith("-EQ") and ":" not in item else 0
        any_eq = 1 if item.endswith("-EQ") else 0
        return (counts[item], universe_eq, any_eq)

    return max(counts, key=score)


def fyers_symbol(canonical: str, is_index: bool = False, exchange: str = "NSE") -> str:
    """
    Converts a canonical symbol to FYERS API format.

    CRITICAL: Hyphenated equity tickers (BAJAJ-AUTO, NAM-INDIA, …) must become
    ``NSE:BAJAJ-AUTO-EQ``. Using ``"-" in name`` as "already has a suffix" was
    wrong — FYERS then got ``NSE:BAJAJ-AUTO`` (HTTP 422) and the scanner
    quarantined valid Nifty names for 24h.

    Examples:
        'DATAPATTNS' -> 'NSE:DATAPATTNS-EQ'
        'BAJAJ-AUTO' -> 'NSE:BAJAJ-AUTO-EQ'
        'NIFTY50-INDEX' -> 'NSE:NIFTY50-INDEX'
    """
    if not canonical:
        return ""

    s = canonical.strip().upper()

    # Already fully qualified (NSE:TCS-EQ / NSE:NIFTY50-INDEX)
    if ":" in s:
        # Repair legacy bad form NSE:BAJAJ-AUTO (equity missing -EQ)
        _ex, _rest = s.split(":", 1)
        if (
            not is_index
            and not _rest.endswith(_INDEX_SUFFIX)
            and not any(_rest.endswith(suf) for suf in _EQUITY_SERIES_SUFFIXES)
        ):
            return f"{_ex}:{_rest}-EQ"
        return s

    if is_index or s.endswith(_INDEX_SUFFIX):
        if not s.endswith(_INDEX_SUFFIX):
            s = f"{s}{_INDEX_SUFFIX}"
        return f"{exchange}:{s}"

    # Equity: always ensure a series suffix (-EQ default)
    if not any(s.endswith(suf) for suf in _EQUITY_SERIES_SUFFIXES):
        s = f"{s}-EQ"

    return f"{exchange}:{s}"
