"""Strategy Tester API: catalog, create run, history, cancellation."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.strategy_tester.presets import PRESETS
from app.services.strategy_tester.schema import parse_strategy_config


@pytest.fixture()
def api(test_engine):
    with TestClient(app) as client:
        yield client


def _register(api: TestClient) -> dict:
    email = f"st_{uuid.uuid4().hex[:10]}@example.com"
    res = api.post(
        "/auth/register",
        json={"email": email, "password": "SecurePassword123!", "full_name": "Strategy Tester"},
    )
    assert res.status_code in (200, 201), res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_catalog_requires_auth(api):
    assert api.get("/strategy-tests/catalog").status_code == 401


def test_catalog_and_history(api):
    headers = _register(api)
    cat = api.get("/strategy-tests/catalog", headers=headers)
    assert cat.status_code == 200, cat.text
    body = cat.json()
    assert body["presets"]
    assert any(p["name"] == "Momentum Strategy" for p in body["presets"])
    hist = api.get("/strategy-tests/history", headers=headers)
    assert hist.status_code == 200
    assert hist.json()["runs"] == []


def test_create_run_returns_immediately_and_tracks_progress(api):
    headers = _register(api)
    start = (date.today() - timedelta(days=30)).isoformat()
    end = date.today().isoformat()
    cfg = dict(PRESETS[0])
    cfg["start_date"] = start
    cfg["end_date"] = end

    async def fake_start(**kwargs):
        parse_strategy_config(kwargs["config"].to_snapshot())
        return {
            "id": str(uuid.uuid4()),
            "run_id": "STR-20260826-001",
            "strategy_name": kwargs["config"].name,
            "status": "queued",
            "universe_size": 755,
            "progress_pct": 0,
        }

    with patch(
        "app.routes.strategy_tester.start_test_background",
        new=AsyncMock(side_effect=fake_start),
    ):
        res = api.post("/strategy-tests", json=cfg, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["run_id"] == "STR-20260826-001"
    assert body["strategy_name"] == "Momentum Strategy"
    assert body["status"] == "queued"


def test_save_same_name_updates_existing(api):
    headers = _register(api)
    payload = {
        "name": "Momentum Strategy",
        "description": "first",
        "universe": "ALL_755",
        "timeframe": "1D",
        "side": "LONG",
        "filters": [
            {"id": "f1", "field": "CLOSE", "left": "CLOSE", "operator": ">", "value": {"indicator": "SMA", "period": 50}},
            {
                "id": "f2",
                "field": "SMA_50",
                "left": {"indicator": "SMA", "period": 50},
                "operator": ">",
                "value": {"indicator": "SMA", "period": 200},
            },
            {"id": "f3", "field": "RSI_14", "left": {"indicator": "RSI", "period": 14}, "operator": ">", "value": 55},
            {"id": "f4", "field": "VOLUME", "operator": ">", "value": {"indicator": "AVG_VOLUME", "period": 20}},
        ],
        "signal_rules": {"buy_requires_all": True},
        "position_rules": {"side": "LONG"},
        "source": {"type": "builder"},
    }
    first = api.post("/strategy-tests/strategies", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    second = api.post("/strategy-tests/strategies", json={**payload, "description": "updated"}, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    listed = api.get("/strategy-tests/strategies", headers=headers)
    names = [item["name"] for item in listed.json()["strategies"]]
    assert names.count("Momentum Strategy") == 1


def test_invalid_strategy_rejected(api):
    headers = _register(api)
    res = api.post("/strategy-tests", json={"name": "Empty", "filters": []}, headers=headers)
    assert res.status_code == 422


def test_create_run_accepts_frontend_builder_payload(api):
    headers = _register(api)
    payload = {
        "name": "Momentum Strategy",
        "description": "Momentum based strategy using trend, momentum and volume filters.",
        "universe": "ALL_755",
        "timeframe": "1D",
        "side": "LONG",
        "start_date": (date.today() - timedelta(days=30)).isoformat(),
        "end_date": date.today().isoformat(),
        "initial_capital": 1_000_000,
        "filters": [
            {"id": "f1", "field": "CLOSE", "left": "CLOSE", "operator": ">", "value": {"indicator": "SMA", "period": 50}},
            {
                "id": "f2",
                "field": "SMA_50",
                "left": {"indicator": "SMA", "period": 50},
                "operator": ">",
                "value": {"indicator": "SMA", "period": 200},
            },
            {"id": "f3", "field": "RSI_14", "left": {"indicator": "RSI", "period": 14}, "operator": ">", "value": 55},
            {"id": "f4", "field": "VOLUME", "operator": ">", "value": {"indicator": "AVG_VOLUME", "period": 20}},
        ],
        "signal_rules": {"buy_requires_all": True},
        "position_rules": {"side": "LONG"},
        "source": {"type": "builder"},
    }

    async def fake_start(**kwargs):
        parse_strategy_config(kwargs["config"].to_snapshot())
        return {
            "id": str(uuid.uuid4()),
            "run_id": "STR-20260826-010",
            "strategy_name": kwargs["config"].name,
            "status": "queued",
            "universe_size": 755,
            "progress_pct": 0,
        }

    with patch(
        "app.routes.strategy_tester.start_test_background",
        new=AsyncMock(side_effect=fake_start),
    ):
        save = api.post("/strategy-tests/strategies", json=payload, headers=headers)
        assert save.status_code == 200, save.text
        res = api.post("/strategy-tests", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["run_id"] == "STR-20260826-010"


def test_create_run_accepts_breakout_and_rel_volume(api):
    headers = _register(api)
    payload = {
        "name": "Breakout Strategy",
        "description": "Close above prior 20-day high with expanding volume.",
        "universe": "ALL_755",
        "timeframe": "1D",
        "side": "LONG",
        "start_date": (date.today() - timedelta(days=30)).isoformat(),
        "end_date": date.today().isoformat(),
        "initial_capital": 1_000_000,
        "filters": [
            {"id": "close_high20", "field": "CLOSE", "left": "CLOSE", "operator": ">", "value": {"indicator": "HIGH", "period": 20}},
            {"id": "vol_1_5", "field": "REL_VOLUME", "left": "REL_VOLUME", "operator": ">", "value": 1.5, "label": "Volume > 1.5 × Average Volume"},
            {"id": "rsi_band", "field": "RSI", "left": "RSI", "operator": "between", "low": 50, "high": 70},
            {"id": "close_ema50", "field": "CLOSE", "left": "CLOSE", "operator": ">", "value": {"indicator": "EMA", "period": 50}},
        ],
        "signal_rules": {"buy_requires_all": True, "watch_min_passed": 2, "watch_min_pass_ratio": 0.5},
        "position_rules": {"side": "LONG", "return_method": "SIMPLE"},
        "source": {"type": "builder"},
    }

    async def fake_start(**kwargs):
        parse_strategy_config(kwargs["config"].to_snapshot())
        return {
            "id": str(uuid.uuid4()),
            "run_id": "STR-20260826-011",
            "strategy_name": kwargs["config"].name,
            "status": "queued",
            "universe_size": 755,
            "progress_pct": 0,
        }

    with patch(
        "app.routes.strategy_tester.start_test_background",
        new=AsyncMock(side_effect=fake_start),
    ):
        save = api.post("/strategy-tests/strategies", json=payload, headers=headers)
        assert save.status_code == 200, save.text
        res = api.post("/strategy-tests", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["run_id"] == "STR-20260826-011"

