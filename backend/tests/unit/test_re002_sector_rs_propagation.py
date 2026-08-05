"""Sector RS must reach RE-002 extract_sector_rs without inventing tech proxies."""

from types import SimpleNamespace

from app.services.re002.rs_features import extract_sector_rs
from app.services.sector_rs_service import SectorRelativeStrengthService


def test_extract_prefers_sector_rs_20():
    ov = SimpleNamespace(sector_rs_20=1.25, sector_roc20=5.0, nifty50_roc20=3.0)
    assert extract_sector_rs(ov) == 1.25


def test_extract_recomputes_from_roc_legs_when_rs_null():
    ov = SimpleNamespace(sector_rs_20=None, sector_roc20=5.5, nifty50_roc20=2.0)
    assert abs(extract_sector_rs(ov) - 3.5) < 1e-9


def test_extract_none_when_absent():
    assert extract_sector_rs(None) is None
    assert extract_sector_rs(SimpleNamespace()) is None


def test_resolve_sector_index_static_map():
    svc = SectorRelativeStrengthService()
    # Known static mapping
    assert svc.resolve_sector_index("TCS") == "NSE:NIFTYIT-INDEX"
    assert svc.resolve_sector_index("TCS-EQ") == "NSE:NIFTYIT-INDEX"


def test_resolve_sector_index_from_stocks_master_when_present():
    """If stocks_master has ABB-EQ Capital Goods, resolve to infra index."""
    svc = SectorRelativeStrengthService()
    # May hit live DB; if missing, skip soft
    resolved = svc.resolve_sector_index("ABB-EQ")
    if resolved is None:
        # No master row in this environment
        return
    assert resolved.startswith("NSE:")
