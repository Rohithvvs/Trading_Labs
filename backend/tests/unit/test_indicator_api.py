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
    condition_names = [item["name"] for item in body["entry_conditions"]]
    assert condition_names == [
        "NIFTY 500 Close > NIFTY 500 SMA 50",
        "Close >= Prior 252 High",
        "Volume > Average Volume 20",
    ]
    assert "52W Breakout Signal = 1" not in condition_names
    parsed_names = [item["name"] for item in (body["parsed_definition"] or {}).get("entry_conditions") or []]
    assert parsed_names == condition_names


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


@pytest.mark.asyncio
async def test_fetch_current_indicator_market_data_ensures_then_overlays():
    from datetime import date

    from app.services.indicator_scanner.scan_service import fetch_current_indicator_market_data
    from app.services.strategy_tester.indicators import BarSeries

    order: list[str] = []
    series = BarSeries(
        dates=[date(2026, 9, 8)],
        open=[100.0],
        high=[101.0],
        low=[99.0],
        close=[100.5],
        volume=[1_000.0],
    )

    async def ensure(symbols, **kwargs):
        order.append("ensure")
        assert kwargs.get("target_date") == date(2026, 9, 8)
        assert kwargs.get("max_duration_s") == 20.0
        return {"status": "SUCCESS"}

    async def repair(*_args, **_kwargs):
        order.append("repair")
        assert _kwargs.get("skip_thin") is True
        return {"repaired": 0}

    async def prepare(*_args, **_kwargs):
        order.append("prepare")
        assert _kwargs.get("overlay_live") is True
        return {"AAA": series}, series, "daily_ohlcv+live_session"

    with (
        patch(
            "app.services.indicator_scanner.scan_service.ensure_universe_market_data",
            new=ensure,
        ),
        patch(
            "app.services.market_data_ingestion.session_repair.repair_scan_market_history",
            new=repair,
        ),
        patch(
            "app.services.indicator_scanner.scan_service.prepare_scan_market_data",
            new=prepare,
        ),
        patch(
            "app.services.market_data_ingestion.calendar_utils.expected_last_completed_session",
            return_value=date(2026, 9, 8),
        ),
    ):
        loaded, bench, source, report = await fetch_current_indicator_market_data(
            ["AAA"],
            ["AAA-EQ"],
            from_date=date(2026, 1, 1),
            end_date=date(2026, 9, 8),
            need_benchmark=False,
            min_bars=20,
        )

    assert order == ["ensure", "repair", "prepare"]
    assert source == "daily_ohlcv+live_session"
    assert report["ensure"]["status"] == "SUCCESS"
    assert loaded["AAA"].close[-1] == 100.5
    assert bench is series


def test_indicator_end_date_keeps_tradingview_as_of():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from app.services.indicator_scanner.scan_service import indicator_end_date

    saturday = datetime(2026, 8, 29, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    monday = datetime(2026, 8, 31, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    with patch(
        "app.services.market_data_ingestion.calendar_utils.expected_last_completed_session",
        return_value=date(2026, 8, 28),
    ):
        assert indicator_end_date(date(2026, 8, 28), now=saturday) == date(2026, 8, 28)
        assert indicator_end_date(None, now=saturday) == date(2026, 8, 28)
        assert indicator_end_date(date(2026, 8, 30), now=saturday) == date(2026, 8, 28)
        assert indicator_end_date(date(2026, 8, 27), now=saturday) == date(2026, 8, 27)

    assert indicator_end_date(None, now=monday) == date(2026, 8, 31)
    assert indicator_end_date(date(2026, 8, 28), now=monday) == date(2026, 8, 28)


def test_indicator_end_date_weekend_today_uses_last_session():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from app.services.indicator_scanner.scan_service import indicator_end_date, pine_screener_bar

    saturday_morning = datetime(2026, 9, 5, 9, 14, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert pine_screener_bar(saturday_morning) == date(2026, 9, 4)
    assert indicator_end_date(date(2026, 9, 5), now=saturday_morning) == date(2026, 9, 4)
    assert indicator_end_date(None, now=saturday_morning) == date(2026, 9, 4)
    assert indicator_end_date(date(2026, 9, 3), now=saturday_morning) == date(2026, 9, 3)


def test_indicator_end_date_before_open_uses_today_on_trading_day():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from app.services.indicator_scanner.scan_service import (
        indicator_end_date,
        last_bar_covers_scan,
        pine_screener_bar,
    )

    thursday_midnight = datetime(2026, 9, 10, 0, 58, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert pine_screener_bar(thursday_midnight) == date(2026, 9, 9)
    assert indicator_end_date(date(2026, 9, 10), now=thursday_midnight) == date(2026, 9, 10)
    assert indicator_end_date(None, now=thursday_midnight) == date(2026, 9, 10)
    assert last_bar_covers_scan(date(2026, 9, 9), date(2026, 9, 10), now=thursday_midnight) is True
    assert last_bar_covers_scan(date(2026, 9, 8), date(2026, 9, 10), now=thursday_midnight) is False


def test_last_bar_covers_scan_requires_today_after_open():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from app.services.indicator_scanner.scan_service import last_bar_covers_scan

    thursday_open = datetime(2026, 9, 10, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert last_bar_covers_scan(date(2026, 9, 9), date(2026, 9, 10), now=thursday_open) is False
    assert last_bar_covers_scan(date(2026, 9, 10), date(2026, 9, 10), now=thursday_open) is True


def test_resolve_available_scan_end_falls_back_when_target_bar_missing():
    from datetime import date

    from app.services.indicator_scanner.scan_service import resolve_available_scan_end
    from app.services.strategy_tester.indicators import BarSeries

    def bars(*days: date) -> BarSeries:
        n = len(days)
        return BarSeries(
            dates=list(days),
            open=[1.0] * n,
            high=[1.0] * n,
            low=[1.0] * n,
            close=[1.0] * n,
            volume=[1.0] * n,
        )

    stale = {
        "AAA": bars(date(2026, 9, 10), date(2026, 9, 11)),
        "BBB": bars(date(2026, 9, 10), date(2026, 9, 11)),
    }
    end, note = resolve_available_scan_end(date(2026, 9, 15), stale)
    assert end == date(2026, 9, 11)
    assert note is not None
    assert "2026-09-15" in note
    assert "2026-09-11" in note

    end_ok, note_ok = resolve_available_scan_end(date(2026, 9, 11), stale)
    assert end_ok == date(2026, 9, 11)
    assert note_ok is None

    live = {
        "AAA": bars(date(2026, 9, 11), date(2026, 9, 15)),
        "BBB": bars(date(2026, 9, 11), date(2026, 9, 15)),
    }
    end_live, note_live = resolve_available_scan_end(date(2026, 9, 15), live)
    assert end_live == date(2026, 9, 15)
    assert note_live is None


def test_indicator_end_date_uses_today_during_rth_even_if_overlay_helper_is_none():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from app.services.indicator_scanner.scan_service import indicator_end_date, pine_screener_bar

    friday_noon = datetime(2026, 9, 4, 12, 18, tzinfo=ZoneInfo("Asia/Kolkata"))
    with (
        patch(
            "app.services.strategies.breakout52w.session_overlay.should_overlay_session",
            return_value=None,
        ),
        patch(
            "app.services.market_data_ingestion.calendar_utils.expected_last_completed_session",
            return_value=date(2026, 9, 3),
        ),
    ):
        assert pine_screener_bar(friday_noon) == date(2026, 9, 4)
        assert indicator_end_date(None, now=friday_noon) == date(2026, 9, 4)
        assert indicator_end_date(date(2026, 9, 4), now=friday_noon) == date(2026, 9, 4)
        assert indicator_end_date(date(2026, 9, 3), now=friday_noon) == date(2026, 9, 3)


def test_clip_series_stops_on_requested_session():
    from datetime import date

    from app.services.indicator_scanner.scan_service import clip_series_to
    from app.services.strategy_tester.indicators import BarSeries

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


LTM_SCAN_SOURCE = """
//@version=6
indicator("LTM Momentum 252 [SCAN]", overlay=false)
closeNow = close
closePast = close[252]
hasHistory = not na(closeNow) and not na(closePast) and closePast > 0 and closeNow > 0
momentum252 = hasHistory ? (closeNow / closePast - 1.0) : na
eligible = hasHistory and not na(momentum252) and momentum252 > 0.50
scanSignal = eligible ? 1 : 0
plot(scanSignal, "LTM Eligible Signal")
plot(momentum252, "Momentum 252")
plot(closeNow, "Close")
plot(closePast, "Close t-252")
"""


def test_symbol_detail_payload_expands_legacy_signal_filter_from_source():
    from types import SimpleNamespace

    from app.services.indicator_scanner.entry_conditions import CONDITIONS_OUTPUT_KEY
    from app.services.indicator_scanner.scan_service import symbol_detail_payload

    run = SimpleNamespace(
        public_scan_id="IND-20260904-001",
        indicator_id=None,
        indicator_name="LTM Momentum 252 [SCAN]",
        filters=[{"field": "LTM Eligible Signal", "operator": "=", "value": 1}],
        indicator_snapshot={"source_code": LTM_SCAN_SOURCE},
    )
    row = SimpleNamespace(
        symbol="RATEGAIN",
        display_name="Rategain Travel Technologies Ltd.",
        exchange="NSE",
        timeframe="1D",
        as_of="2026-09-04",
        status="ok",
        matched=True,
        outputs={
            "LTM Eligible Signal": 1.0,
            "Momentum 252": 0.76,
            "Close": 869.75,
            "Close t-252": 495.05,
        },
        ohlcv={"close": 869.75},
        error_detail=None,
        bar_count=400,
    )
    payload = symbol_detail_payload(run, row)
    assert payload["source"] == "indicator_scanner"
    assert payload["signal"] == "MATCH"
    assert payload["indicator_name"] == "LTM Momentum 252 [SCAN]"
    assert [item["name"] for item in payload["filter_results"]] == ["Momentum 252 > 0.5"]
    assert payload["filter_results"][0]["passed"] is True
    assert CONDITIONS_OUTPUT_KEY not in (payload.get("outputs") or {})
    assert payload["entry_price"] == 495.05
    assert payload["exit_price"] == 869.75
    assert abs(payload["return_pct"] - 76.0) < 1e-9
    names = {item["name"] for item in payload["filter_results"]}
    assert "LTM Eligible Signal = 1" not in names
    assert "Close > SMA 50" not in names
    assert "Rsi 14 > 55" not in names


def test_row_from_eval_requires_every_strategy_condition():
    from datetime import date
    from types import SimpleNamespace

    from app.services.indicator_scanner.entry_conditions import CONDITIONS_OUTPUT_KEY
    from app.services.indicator_scanner.evaluator import EvalResult
    from app.services.indicator_scanner.scan_service import _row_from_eval, symbol_detail_payload

    all_pass = [
        {"id": "c1", "name": "Close > SMA 50", "passed": True, "left_value": 1255.8, "right_value": 1200.0, "operator": ">"},
        {"id": "c2", "name": "SMA 50 > SMA 200", "passed": True, "left_value": 1306.47, "right_value": 869.7, "operator": ">"},
        {"id": "c3", "name": "RSI 14 > 55", "passed": True, "left_value": 62.4, "right_value": 55, "operator": ">"},
        {"id": "c4", "name": "Volume > Average Volume 20", "passed": True, "left_value": 1234567, "right_value": 987654, "operator": ">"},
    ]
    rsi_fail = [dict(item) for item in all_pass]
    rsi_fail[2] = {**rsi_fail[2], "passed": False, "left_value": 41.0}

    matched = _row_from_eval(
        "AAA",
        "AAA Ltd",
        EvalResult(as_of=date(2026, 9, 7), outputs={"Eligible Signal": 1.0}, ohlcv={"close": 1255.8}, status="ok", conditions=all_pass),
        [{"field": "Eligible Signal", "operator": "=", "value": 1}],
    )
    rejected = _row_from_eval(
        "BBB",
        "BBB Ltd",
        EvalResult(as_of=date(2026, 9, 7), outputs={"Eligible Signal": 1.0}, ohlcv={"close": 1255.8}, status="ok", conditions=rsi_fail),
        [{"field": "Eligible Signal", "operator": "=", "value": 1}],
    )
    assert matched["matched"] is True
    assert rejected["matched"] is False
    assert CONDITIONS_OUTPUT_KEY in matched["outputs"]

    run = SimpleNamespace(
        public_scan_id="IND-20260907-004",
        indicator_id=None,
        indicator_name="Momentum Strategy [SCAN]",
        filters=[{"field": "Eligible Signal", "operator": "=", "value": 1}],
        indicator_snapshot={"entry_conditions": [{"id": "c1", "name": "Close > SMA 50"}]},
    )
    row = SimpleNamespace(
        symbol="AAA",
        display_name="AAA Ltd",
        exchange="NSE",
        timeframe="1D",
        as_of="2026-09-07",
        status="ok",
        matched=True,
        outputs={"Eligible Signal": 1.0, CONDITIONS_OUTPUT_KEY: all_pass},
        ohlcv={"close": 1255.8},
        error_detail=None,
        bar_count=320,
    )
    payload = symbol_detail_payload(run, row)
    assert [item["name"] for item in payload["filter_results"]] == [
        "Close > SMA 50",
        "SMA 50 > SMA 200",
        "RSI 14 > 55",
        "Volume > Average Volume 20",
    ]
    assert all(item["passed"] is True for item in payload["filter_results"])
    assert "Eligible Signal = 1" not in {item["name"] for item in payload["filter_results"]}


def test_symbol_detail_payload_expands_52w_conditions_from_source():
    from types import SimpleNamespace

    from app.services.indicator_scanner.scan_service import symbol_detail_payload
    from app.services.indicator_scanner.template import BREAKOUT_SCAN_SOURCE

    run = SimpleNamespace(
        public_scan_id="IND-20260904-002",
        indicator_id=None,
        indicator_name="52-Week High Breakout [SCAN]",
        filters=[{"field": "52W Breakout Signal", "operator": "=", "value": 1}],
        indicator_snapshot={"source_code": BREAKOUT_SCAN_SOURCE},
    )
    row = SimpleNamespace(
        symbol="RELIANCE",
        display_name="Reliance Industries Ltd.",
        exchange="NSE",
        timeframe="1D",
        as_of="2026-09-04",
        status="ok",
        matched=True,
        outputs={
            "52W Breakout Signal": 1.0,
            "Close": 1400.0,
            "Prior 252 High": 1350.0,
            "Volume SMA 20": 1_000_000.0,
            "NIFTY 500 Close": 21000.0,
            "NIFTY 500 SMA 50": 20000.0,
        },
        ohlcv={"close": 1400.0, "volume": 1_500_000.0},
        error_detail=None,
        bar_count=400,
    )
    payload = symbol_detail_payload(run, row)
    names = [item["name"] for item in payload["filter_results"]]
    assert names == [
        "NIFTY 500 Close > NIFTY 500 SMA 50",
        "Close >= Prior 252 High",
        "Volume > Average Volume 20",
    ]
    assert all(item["passed"] is True for item in payload["filter_results"])
    assert "52W Breakout Signal = 1" not in names


def test_start_indicator_backtest_endpoints(api):
    headers = _register(api)
    save = api.post(
        "/indicators",
        json={
            "name": "52-Week High Breakout [SCAN]",
            "description": "52W Breakout for LEAN test",
            "source_code": BREAKOUT_SCAN_SOURCE,
            "timeframe": "1D",
        },
        headers=headers,
    )
    assert save.status_code == 200, save.text
    indicator_id = save.json()["id"]

    # Start backtest
    res = api.post(
        f"/indicators/{indicator_id}/backtest",
        json={
            "start_date": "2021-01-01",
            "end_date": "2021-06-01",
            "initial_capital": 100000.0,
            "universe_id": "nse-755",
            "engine": "LEAN",
            "max_positions": 5,
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    job_data = res.json()
    assert "jobId" in job_data
    assert job_data["strategyId"] == "09_52w_breakout"
    job_id = job_data["jobId"]

    # Query status
    status_res = api.get(f"/indicators/{indicator_id}/backtests/{job_id}", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["jobId"] == job_id


def test_momentum_pulse_backtest_uses_pulse_algorithm_not_ltm(api):
    headers = _register(api)
    save = api.post(
        "/indicators",
        json={
            "name": "Momentum Pulse Finder",
            "description": "EMA 20 + RSI crossover",
            "source_code": (
                '//@version=6\nindicator("Momentum Pulse Finder", overlay=true)\n'
                "ema20 = ta.ema(close, 20)\nrsiValue = ta.rsi(close, 14)\n"
                "buySignal = close > ema20 and ta.crossover(rsiValue, 50)\n"
                'plot(ema20, title="EMA 20")\n'
                'plotshape(buySignal, title="Momentum Signal")\n'
            ),
            "timeframe": "1D",
        },
        headers=headers,
    )
    assert save.status_code == 200, save.text
    indicator_id = save.json()["id"]
    res = api.post(
        f"/indicators/{indicator_id}/backtest",
        json={
            "start_date": "2021-01-01",
            "end_date": "2021-06-01",
            "initial_capital": 100000.0,
            "universe_id": "nse-755",
            "engine": "LEAN",
            "max_positions": 5,
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["strategyId"] == "momentum_pulse"
    assert res.json()["strategyId"] != "17_long_term_mom"

