import pytest
import os
from sqlalchemy import select
from backend.app.models.stock import StockMaster
from backend.app.services.universe_service import UniverseService
from backend.scripts.import_stocks_master import import_csv
from backend.app.db.session import AsyncSessionLocal

@pytest.fixture
def sample_csv(tmp_path):
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        "Symbol,Company Name,Industry,Series,ISIN Code\n"
        "RELIANCE,Reliance Industries,Energy,EQ,INE123456\n"
        "TCS,Tata Consultancy,IT,EQ,INE654321\n"
        "INFY,Infosys,IT,,INE987654\n"
        "DUP,Duplicate,IT,EQ,INE000\n"
        "DUP,Duplicate,IT,EQ,INE000\n"
    )
    return str(csv_file)

@pytest.mark.asyncio
async def test_table_creation_and_import(sample_csv):
    # Test CSV import
    await import_csv(sample_csv, "TEST_UNIVERSE")
    
    # Test retrieval
    symbols = await UniverseService.get_active_symbols("TEST_UNIVERSE")
    assert len(symbols) == 4
    
    assert "RELIANCE-EQ" in symbols
    assert "TCS-EQ" in symbols
    assert "INFY-EQ" in symbols
    assert "DUP-EQ" in symbols

@pytest.mark.asyncio
async def test_empty_universe():
    symbols = await UniverseService.get_active_symbols("EMPTY_UNIVERSE")
    assert symbols == []

@pytest.mark.asyncio
async def test_active_nifty500_has_755_canonical_symbols():
    from backend.app.config.settings import ROOT_DIR

    await import_csv(str(ROOT_DIR / "ind_nifty500list.csv"), "NIFTY500")
    instruments = await UniverseService.list_active_instruments("NIFTY500")
    report = await UniverseService.validate_universe("NIFTY500")
    symbols = [item.symbol for item in instruments]
    store_symbols = [item.universe_symbol for item in instruments]

    assert report.total_stocks == 755
    assert report.symbols_present == 755
    assert report.symbols_missing == 0
    assert report.duplicates == 0
    assert report.invalid_symbols == 0
    assert report.broker_mappings_missing == 0
    assert len(instruments) == 755
    assert len(set(symbols)) == 755
    assert all(item.symbol for item in instruments)
    assert all(item.broker_symbol.startswith("NSE:") for item in instruments)
    assert all(item.company_name for item in instruments)
    assert "360ONE" in symbols
    assert "360ONE-EQ" in store_symbols


@pytest.mark.asyncio
async def test_duplicate_handling(sample_csv):
    # DUP is in the CSV twice
    await import_csv(sample_csv, "DUP_UNIVERSE")
    
    async with AsyncSessionLocal() as db:
        result = await db.scalars(
            select(StockMaster).where(StockMaster.symbol == "DUP-EQ")
        )
        # Should only be one entry
        assert len(list(result.all())) == 1
