from __future__ import annotations

from types import SimpleNamespace

from app.config.settings import ROOT_DIR, settings
from app.services.universe_csv import load_unique_nifty500_csv_rows, parse_nifty500_row
from app.services.universe_service import UniverseService
from app.utils.symbol import (
    canonical_symbol,
    fyers_symbol,
    ohlcv_symbol_variants,
    preferred_ohlcv_store_symbol,
)


def test_csv_authoritative_universe_has_755_unique_symbols():
    csv_path = ROOT_DIR / settings.nifty500_csv_path
    rows = load_unique_nifty500_csv_rows(csv_path)
    symbols = [row["canonical_symbol"] for row in rows]
    assert len(rows) == 755
    assert len(set(symbols)) == 755
    assert all(symbol and symbol.strip() for symbol in symbols)
    assert all(" " not in symbol for symbol in symbols)
    assert "360ONE" in symbols
    assert "AARTIDRUGS" in symbols


def test_tab_collapsed_csv_row_recovers_symbol_and_company():
    parsed = parse_nifty500_row(
        {
            "Company Name": "Aadhar Housing Finance Ltd.\tFinancial Services\tAADHARHFC\tEQ\tINE883F01010",
            "Industry": None,
            "Symbol": None,
            "Series": None,
            "ISIN Code": None,
        }
    )
    assert parsed is not None
    assert parsed["symbol"] == "AADHARHFC"
    assert parsed["canonical_symbol"] == "AADHARHFC"
    assert parsed["company_name"] == "Aadhar Housing Finance Ltd."
    assert parsed["series"] == "EQ"


def test_blank_csv_row_is_not_invented():
    assert parse_nifty500_row({"Company Name": "Unknown Co", "Symbol": ""}) is None


def test_ohlcv_symbol_variants_include_store_eq_form():
    variants = ohlcv_symbol_variants("GLAXO")
    assert "GLAXO" in variants
    assert "GLAXO-EQ" in variants
    assert "NSE:GLAXO-EQ" in variants
    assert ohlcv_symbol_variants("BAJAJ-AUTO")[0] == "BAJAJ-AUTO"
    assert "BAJAJ-AUTO-EQ" in ohlcv_symbol_variants("BAJAJ-AUTO")
    assert preferred_ohlcv_store_symbol(["GLAXO", "GLAXO-EQ", "NSE:GLAXO-EQ"]) == "GLAXO-EQ"


def test_instrument_mapping_keeps_store_and_broker_forms_separate():
    row = SimpleNamespace(
        id=11,
        symbol="360ONE-EQ",
        company_name="360 ONE WAM Ltd.",
        series="EQ",
        isin="INE466L01038",
        is_active=True,
        universe="NIFTY500",
    )
    item = UniverseService._instrument_from_row(row)
    assert item is not None
    assert item.symbol == "360ONE"
    assert item.universe_symbol == "360ONE-EQ"
    assert item.broker_symbol == "NSE:360ONE-EQ"
    assert item.company_name == "360 ONE WAM Ltd."
    assert item.exchange == "NSE"


def test_csv_membership_maps_to_755_unique_instruments():
    rows = load_unique_nifty500_csv_rows(ROOT_DIR / settings.nifty500_csv_path)
    instruments = []
    for idx, row in enumerate(rows, start=1):
        series = row["series"]
        stored = row["symbol"]
        if series in {"", "EQ"} and not stored.endswith("-EQ"):
            stored = f"{stored}-EQ"
        item = UniverseService._instrument_from_row(
            SimpleNamespace(
                id=idx,
                symbol=stored,
                company_name=row["company_name"],
                series=series,
                isin=row["isin"],
                is_active=True,
                universe="NIFTY500",
            )
        )
        assert item is not None
        instruments.append(item)
    canons = [item.symbol for item in instruments]
    assert len(instruments) == 755
    assert len(set(canons)) == 755
    assert all(item.company_name for item in instruments)
    assert all(item.broker_symbol.startswith("NSE:") for item in instruments)
    assert all(item.universe_symbol for item in instruments)


def test_every_csv_symbol_maps_to_fyers_without_guessing():
    rows = load_unique_nifty500_csv_rows(ROOT_DIR / settings.nifty500_csv_path)
    for row in rows:
        broker = fyers_symbol(row["canonical_symbol"])
        assert broker.startswith("NSE:")
        assert row["canonical_symbol"]
        assert " " not in row["canonical_symbol"]


def test_hyphenated_canonical_maps_to_fyers_eq():
    assert canonical_symbol("BAJAJ-AUTO-EQ") == "BAJAJ-AUTO"
    assert fyers_symbol(canonical_symbol("BAJAJ-AUTO-EQ")) == "NSE:BAJAJ-AUTO-EQ"


def test_empty_stored_symbol_is_not_fabricated():
    row = SimpleNamespace(
        id=99,
        symbol="  ",
        company_name="Missing Ticker Ltd.",
        series="EQ",
        isin=None,
        is_active=True,
        universe="NIFTY500",
    )
    assert UniverseService._instrument_from_row(row) is None
