"""Hyphenated NSE tickers must keep -EQ for FYERS history API.

Regression: BAJAJ-AUTO-EQ was sent as NSE:BAJAJ-AUTO → HTTP 422 → 24h quarantine,
which broke scanner OHLCV fetch for valid Nifty names.
"""
from app.utils.symbol import canonical_symbol, fyers_symbol


def test_bajaj_auto_gets_eq_suffix():
    assert canonical_symbol("BAJAJ-AUTO-EQ") == "BAJAJ-AUTO"
    assert fyers_symbol(canonical_symbol("BAJAJ-AUTO-EQ")) == "NSE:BAJAJ-AUTO-EQ"
    assert fyers_symbol("BAJAJ-AUTO") == "NSE:BAJAJ-AUTO-EQ"


def test_hyphenated_names_still_get_eq():
    cases = {
        "NAM-INDIA-EQ": "NSE:NAM-INDIA-EQ",
        "L&TFH-EQ": "NSE:L&TFH-EQ",
        "M&M-EQ": "NSE:M&M-EQ",
        "JAIBALAJI-EQ": "NSE:JAIBALAJI-EQ",
    }
    for raw, expected in cases.items():
        assert fyers_symbol(canonical_symbol(raw)) == expected, raw


def test_plain_equity_and_index_unchanged():
    assert fyers_symbol(canonical_symbol("RELIANCE-EQ")) == "NSE:RELIANCE-EQ"
    assert fyers_symbol(canonical_symbol("TCS")) == "NSE:TCS-EQ"
    assert fyers_symbol(canonical_symbol("NSE:NIFTY50-INDEX")) == "NSE:NIFTY50-INDEX"
    assert fyers_symbol("NIFTY50-INDEX", is_index=True) == "NSE:NIFTY50-INDEX"


def test_repair_legacy_bad_qualified_form():
    """Older code produced NSE:BAJAJ-AUTO without -EQ — repair on the way out."""
    assert fyers_symbol("NSE:BAJAJ-AUTO") == "NSE:BAJAJ-AUTO-EQ"
