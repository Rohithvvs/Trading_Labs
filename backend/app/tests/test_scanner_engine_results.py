"""Unit tests for scanner engine projection (Production | RE-001 | RE-002)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.scanner_engine_results import (
    _lab_decisions_to_screener,
    normalize_scanner_engine,
)


def test_normalize_scanner_engine_aliases():
    assert normalize_scanner_engine(None) == "Production"
    assert normalize_scanner_engine("production") == "Production"
    assert normalize_scanner_engine("prod") == "Production"
    assert normalize_scanner_engine("re001") == "RE-001"
    assert normalize_scanner_engine("RE-001") == "RE-001"
    assert normalize_scanner_engine("re-002") == "RE-002"
    assert normalize_scanner_engine("RE_002") == "RE-002"


def test_lab_mapper_splits_buy_watch_reject():
    rows = [
        SimpleNamespace(
            symbol="AAA",
            recommendation_state="BUY",
            confidence_score=0.9,
            production_score=80,
            strategy_name="trend",
            strategy_family="tc",
            explanation="strong",
            trade_guidance={"entry_low": 10, "entry_high": 11, "stop_loss": 9, "target_1": 13},
        ),
        SimpleNamespace(
            symbol="BBB",
            recommendation_state="WATCH",
            confidence_score=0.5,
            production_score=55,
            strategy_name=None,
            strategy_family=None,
            explanation="",
            trade_guidance={},
        ),
        SimpleNamespace(
            symbol="CCC",
            recommendation_state="REJECT",
            confidence_score=0.1,
            production_score=20,
            strategy_name=None,
            strategy_family=None,
            explanation="weak",
            trade_guidance=None,
        ),
    ]
    payload = _lab_decisions_to_screener(
        rows,
        engine="RE-001",
        scan_run_id="scan-xyz",
        scanned_at="2026-08-07T10:00:00+00:00",
    )
    assert payload["available"] is True
    assert payload["recommendation_engine"] == "RE-001"
    assert payload["buy_candidate_symbols"] == ["AAA"]
    assert payload["watch_candidate_symbols"] == ["BBB"]
    assert payload["reject_candidate_symbols"] == ["CCC"]
    # Full cohort: BUY + WATCH + REJECT — matches Recommendation Lab Scan Comparison
    assert payload["shortlisted_symbols"] == ["AAA", "BBB", "CCC"]
    assert payload["total_count"] == 3
    assert payload["buy_count"] == 1
    assert payload["watch_count"] == 1
    assert payload["reject_count"] == 1
    assert payload["scanned_symbols"] == 3
    assert len(payload["all_analyzed_stocks"]) == 3
    assert len(payload["analysis"]["items"]) == 3
    assert any(a["symbol"] == "CCC" and not a["matched"] for a in payload["all_analyzed_stocks"])
    assert any(i["symbol"] == "CCC" and i["recommendation"]["action"] == "REJECT" for i in payload["analysis"]["items"])
    assert payload["analysis"]["items"][0]["recommendation"]["action"] == "BUY"


def test_lab_mapper_never_drops_reject_majority():
    """RE-002-style cohort: many REJECT must still appear in Scanner shortlist."""
    rows = [
        SimpleNamespace(
            symbol=f"S{i:02d}",
            recommendation_state="BUY" if i < 6 else ("WATCH" if i == 6 else "REJECT"),
            confidence_score=0.5,
            production_score=50,
            strategy_name=None,
            strategy_family=None,
            explanation="",
            trade_guidance={},
        )
        for i in range(20)
    ]
    payload = _lab_decisions_to_screener(
        rows, engine="RE-002", scan_run_id="scan-20", scanned_at="2026-08-07T10:00:00+00:00"
    )
    assert payload["total_count"] == 20
    assert payload["buy_count"] == 6
    assert payload["watch_count"] == 1
    assert payload["reject_count"] == 13
    assert len(payload["shortlisted_symbols"]) == 20
    assert len(payload["analysis"]["items"]) == 20
