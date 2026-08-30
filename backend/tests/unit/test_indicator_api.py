"""Indicator Scanner API: validate, save, scan, ownership."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.indicator_scanner.template import BREAKOUT_SCAN_SOURCE, BREAKOUT_SCAN_TITLE


@pytest.fixture()
def api(test_engine):
    with TestClient(app) as client:
        yield client


def _register(api: TestClient, name: str = "Indicator User") -> dict:
    email = f"ind_{uuid.uuid4().hex[:10]}@example.com"
    res = api.post(
        "/auth/register",
        json={"email": email, "password": "SecurePassword123!", "full_name": name},
    )
    assert res.status_code in (200, 201), res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_validate_requires_auth(api):
    assert api.post("/indicators/validate", json={"source_code": "plot(close)"}).status_code == 401


def test_validate_success_extracts_outputs_and_required_bars(api):
    headers = _register(api)
    res = api.post("/indicators/validate", json={"source_code": BREAKOUT_SCAN_SOURCE, "timeframe": "1D"}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["required_bars"] >= 253
    titles = [i["title"] for i in body["inputs"]]
    assert "ATR Multiplier" in titles
    names = [o["name"] for o in body["outputs"]]
    assert "52W Breakout Signal" in names
    assert "52W Breakout" in names
    assert "52W Breakout Scan" in names
    assert any("ATR Multiplier" in w["message"] for w in body["warnings"])


def test_validate_rejects_strategy(api):
    headers = _register(api)
    res = api.post(
        "/indicators/validate",
        json={"source_code": '//@version=6\nstrategy("x")\nplot(close, "c")\n'},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert any("indicator scanner" in e["message"].lower() for e in body["errors"])
    assert body["errors"][0]["line"] >= 1


def test_save_list_and_scan_mocked(api):
    headers = _register(api)
    save = api.post(
        "/indicators",
        json={
            "name": BREAKOUT_SCAN_TITLE,
            "description": "Scan template",
            "source_code": BREAKOUT_SCAN_SOURCE,
            "timeframe": "1D",
        },
        headers=headers,
    )
    assert save.status_code == 200, save.text
    indicator_id = save.json()["id"]
    listed = api.get("/indicators", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == indicator_id for item in listed.json()["indicators"])

    async def fake_start(**kwargs):
        return {
            "id": str(uuid.uuid4()),
            "scan_id": "IND-20260829-001",
            "status": "queued",
            "universe_size": 755,
            "total_count": 755,
            "progress_pct": 0,
        }

    with patch(
        "app.routes.indicator_scanner.start_scan_background",
        new=AsyncMock(side_effect=fake_start),
    ):
        scan = api.post(
            f"/indicators/{indicator_id}/scans",
            json={
                "universe_id": "nse-755",
                "timeframe": "1D",
                "filters": [{"field": "52W Breakout Signal", "operator": "=", "value": 1}],
            },
            headers=headers,
        )
    assert scan.status_code == 200, scan.text
    assert scan.json()["scan_id"] == "IND-20260829-001"


def test_create_same_name_updates_existing(api):
    headers = _register(api)
    payload = {
        "name": BREAKOUT_SCAN_TITLE,
        "description": "first",
        "source_code": BREAKOUT_SCAN_SOURCE,
        "timeframe": "1D",
    }
    first = api.post("/indicators", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    second = api.post("/indicators", json={**payload, "description": "updated"}, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["description"] == "updated"
    listed = api.get("/indicators", headers=headers)
    names = [item["name"] for item in listed.json()["indicators"]]
    assert names.count(BREAKOUT_SCAN_TITLE) == 1


@pytest.mark.asyncio
async def test_interrupted_scan_does_not_block_a_new_scan():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.services.indicator_scanner import persistence
    from app.services.indicator_scanner.compiler import compile_source
    from app.services.indicator_scanner.scan_service import start_scan_background

    stale_id = uuid.uuid4()
    stale = SimpleNamespace(
        id=stale_id,
        public_scan_id="IND-STALE-001",
        status="running",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    created = SimpleNamespace(
        id=uuid.uuid4(),
        public_scan_id="IND-NEW-001",
        indicator_id=None,
        indicator_name=BREAKOUT_SCAN_TITLE,
        universe="nse-755",
        universe_size=1,
        timeframe="1D",
        status="queued",
        stage="queued",
        progress_pct=0,
        processed_count=0,
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        matched_count=0,
        as_of=None,
        benchmark_symbol=None,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        cancelled_at=None,
        error_code=None,
        error_detail=None,
        summary={},
        indicator_snapshot={"outputs": []},
        filters=[],
        sort=None,
    )
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    with (
        patch.object(persistence, "find_active_scan", new=AsyncMock(return_value=stale)),
        patch.object(persistence, "update_scan", new=AsyncMock()) as updated,
        patch.object(persistence, "next_public_scan_id", new=AsyncMock(return_value="IND-NEW-001")),
        patch.object(persistence, "create_scan", new=AsyncMock(return_value=created)),
        patch.object(persistence, "touch_last_used", new=AsyncMock()),
        patch(
            "app.services.indicator_scanner.scan_service.load_universe",
            new=AsyncMock(return_value=[{"symbol": "RELIANCE"}]),
        ),
        patch("app.services.indicator_scanner.scan_service.execute_scan", new=AsyncMock()),
    ):
        result = await start_scan_background(
            user_id=uuid.uuid4(),
            compiled=compiled,
            indicator_id=uuid.uuid4(),
            universe_id="nse-755",
            timeframe="1D",
            filters=[],
            sort=None,
            input_overrides=None,
            scan_date=None,
        )
    assert updated.await_count >= 1
    assert result["scan_id"] == "IND-NEW-001"
    assert result.get("error_code") != "INDICATOR_SCAN_IN_PROGRESS"


@pytest.mark.asyncio
async def test_zero_progress_running_scan_does_not_block_a_new_scan():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.services.indicator_scanner import persistence
    from app.services.indicator_scanner.compiler import compile_source
    from app.services.indicator_scanner import scan_service as iss

    stale_id = uuid.uuid4()
    stale = SimpleNamespace(
        id=stale_id,
        public_scan_id="IND-20260829-013",
        status="running",
        processed_count=0,
        started_at=datetime.now(timezone.utc) - timedelta(seconds=45),
    )
    created = SimpleNamespace(
        id=uuid.uuid4(),
        public_scan_id="IND-NEW-002",
        indicator_id=None,
        indicator_name=BREAKOUT_SCAN_TITLE,
        universe="nse-755",
        universe_size=1,
        timeframe="1D",
        status="queued",
        stage="queued",
        progress_pct=0,
        processed_count=0,
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        matched_count=0,
        as_of=None,
        benchmark_symbol=None,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        cancelled_at=None,
        error_code=None,
        error_detail=None,
        summary={},
        indicator_snapshot={"outputs": []},
        filters=[],
        sort=None,
    )
    compiled = compile_source(BREAKOUT_SCAN_SOURCE)
    iss._active_scans.add(stale_id)
    try:
        with (
            patch.object(persistence, "find_active_scan", new=AsyncMock(return_value=stale)),
            patch.object(persistence, "update_scan", new=AsyncMock()) as updated,
            patch.object(persistence, "next_public_scan_id", new=AsyncMock(return_value="IND-NEW-002")),
            patch.object(persistence, "create_scan", new=AsyncMock(return_value=created)),
            patch.object(persistence, "touch_last_used", new=AsyncMock()),
            patch(
                "app.services.indicator_scanner.scan_service.load_universe",
                new=AsyncMock(return_value=[{"symbol": "RELIANCE"}]),
            ),
            patch("app.services.indicator_scanner.scan_service.execute_scan", new=AsyncMock()),
        ):
            result = await iss.start_scan_background(
                user_id=uuid.uuid4(),
                compiled=compiled,
                indicator_id=uuid.uuid4(),
                universe_id="nse-755",
                timeframe="1D",
                filters=[],
                sort=None,
                input_overrides=None,
                scan_date=None,
            )
    finally:
        iss._active_scans.discard(stale_id)
    assert updated.await_count >= 1
    assert result["scan_id"] == "IND-NEW-002"
    assert result.get("error_code") != "INDICATOR_SCAN_IN_PROGRESS"


def test_invalid_save_rejected(api):
    headers = _register(api)
    res = api.post(
        "/indicators",
        json={"name": "Bad", "source_code": "this is not pine", "timeframe": "1D"},
        headers=headers,
    )
    assert res.status_code == 422


def test_user_cannot_read_foreign_indicator(api):
    owner = _register(api, "Owner")
    other = _register(api, "Other")
    save = api.post(
        "/indicators",
        json={"name": BREAKOUT_SCAN_TITLE, "source_code": BREAKOUT_SCAN_SOURCE, "timeframe": "1D"},
        headers=owner,
    )
    assert save.status_code == 200, save.text
    indicator_id = save.json()["id"]
    res = api.get(f"/indicators/{indicator_id}", headers=other)
    assert res.status_code == 404


def test_indicator_end_date_keeps_tradingview_as_of():
    from datetime import date

    from app.services.indicator_scanner.scan_service import clip_series_to, indicator_end_date
    from app.services.strategy_tester.indicators import BarSeries

    with patch(
        "app.services.market_data_ingestion.calendar_utils.expected_last_completed_session",
        return_value=date(2026, 8, 28),
    ):
        assert indicator_end_date(date(2026, 8, 28)) == date(2026, 8, 28)
        assert indicator_end_date(None) == date(2026, 8, 28)
        assert indicator_end_date(date(2026, 8, 30)) == date(2026, 8, 28)

    series = BarSeries(
        dates=[date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 29)],
        open=[1, 2, 3, 4],
        high=[1, 2, 3, 4],
        low=[1, 2, 3, 4],
        close=[100.0, 101.0, 1938.5, 1940.0],
        volume=[1, 2, 3, 4],
    )
    clipped = clip_series_to(series, date(2026, 8, 28))
    assert clipped is not None
    assert clipped.dates[-1] == date(2026, 8, 28)
    assert clipped.close[-1] == 1938.5
