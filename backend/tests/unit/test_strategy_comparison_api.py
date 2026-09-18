"""Strategy Comparison API: catalog, runs, compare using persisted Strategy Tester data."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.strategy_tester import persistence
from app.services.strategy_tester.schema import parse_strategy_config


@pytest.fixture()
def api(test_engine):
    with TestClient(app) as client:
        yield client


def _register(api: TestClient) -> dict:
    email = f"sc_{uuid.uuid4().hex[:10]}@example.com"
    res = api.post(
        "/auth/register",
        json={"email": email, "password": "SecurePassword123!", "full_name": "Strategy Compare"},
    )
    assert res.status_code in (200, 201), res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _strategy_payload(name: str, extra_filter_value: float = 55) -> dict:
    return {
        "name": name,
        "description": f"{name} description",
        "universe": "ALL_755",
        "timeframe": "1D",
        "side": "LONG",
        "filters": [
            {"id": "f1", "field": "CLOSE", "left": "CLOSE", "operator": ">", "value": {"indicator": "SMA", "period": 50}},
            {"id": "f2", "field": "RSI_14", "left": {"indicator": "RSI", "period": 14}, "operator": ">", "value": extra_filter_value},
        ],
        "signal_rules": {"buy_requires_all": True},
        "position_rules": {"side": "LONG", "entry_rule": "WINDOW_START", "exit_rule": "WINDOW_END"},
        "source": {"type": "builder"},
        "initial_capital": 100000,
    }


def _seed_completed_run(*, user_id, definition_id, name, snapshot, results, universe="ALL_755"):
    async def _go():
        run = await persistence.create_run(
            user_id=user_id,
            public_run_id=f"STR-{uuid.uuid4().hex[:8].upper()}",
            strategy_definition_id=definition_id,
            strategy_name=name,
            strategy_version=1,
            strategy_snapshot=snapshot,
            universe=universe,
            universe_size=3,
            timeframe="1D",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 6, 28),
            initial_capital=100000,
            calculation_version="strategy_tester.v1",
        )
        buy = sum(1 for r in results if r.get("signal") == "BUY")
        watch = sum(1 for r in results if r.get("signal") == "WATCH")
        reject = sum(1 for r in results if r.get("signal") == "REJECT")
        returns = [r["return_pct"] for r in results if r.get("return_pct") is not None]
        await persistence.update_run(
            run.id,
            status="completed",
            stage="completed",
            progress_pct=100,
            processed_count=len(results),
            total_count=len(results),
            buy_count=buy,
            watch_count=watch,
            reject_count=reject,
            completed_at=datetime.now(timezone.utc),
            summary={
                "buy": buy,
                "watch": watch,
                "reject": reject,
                "win_rate": (sum(1 for x in returns if x > 0) / len(returns) * 100.0) if returns else None,
                "average_return": (sum(returns) / len(returns)) if returns else None,
                "top_return": max(returns) if returns else None,
                "worst_return": min(returns) if returns else None,
            },
        )
        await persistence.save_results(run.id, results)
        return await persistence.get_run(run.id)

    return asyncio.run(_go())


def test_catalog_requires_auth(api):
    assert api.get("/strategy-comparison/catalog").status_code == 401


def test_catalog_and_compare_real_runs(api):
    headers = _register(api)
    cat0 = api.get("/strategy-comparison/catalog", headers=headers)
    assert cat0.status_code == 200, cat0.text
    assert cat0.json()["strategies"] == []
    assert cat0.json()["min_slots"] == 2
    assert cat0.json()["max_slots"] == 4

    a = api.post("/strategy-tests/strategies", json=_strategy_payload("Alpha Momentum"), headers=headers)
    b = api.post("/strategy-tests/strategies", json=_strategy_payload("Beta Breakout", extra_filter_value=60), headers=headers)
    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    a_id = a.json()["id"]
    b_id = b.json()["id"]

    defn_a = asyncio.run(persistence.get_definition(uuid.UUID(a_id)))
    defn_b = asyncio.run(persistence.get_definition(uuid.UUID(b_id)))
    snap_a = parse_strategy_config(defn_a.config).to_snapshot()
    snap_b = parse_strategy_config(defn_b.config).to_snapshot()

    run_a = _seed_completed_run(
        user_id=defn_a.user_id,
        definition_id=defn_a.id,
        name="Alpha Momentum",
        snapshot=snap_a,
        results=[
            {"symbol": "RELIANCE", "status": "ok", "signal": "BUY", "entry_price": 100, "exit_price": 112, "return_pct": 12.0, "return_bucket": "POSITIVE"},
            {"symbol": "TCS", "status": "ok", "signal": "BUY", "entry_price": 100, "exit_price": 94, "return_pct": -6.0, "return_bucket": "NEGATIVE"},
            {"symbol": "INFY", "status": "ok", "signal": "WATCH", "entry_price": 100, "exit_price": 101, "return_pct": 1.0, "return_bucket": "POSITIVE"},
        ],
    )
    run_b = _seed_completed_run(
        user_id=defn_b.user_id,
        definition_id=defn_b.id,
        name="Beta Breakout",
        snapshot=snap_b,
        universe="NIFTY500",
        results=[
            {"symbol": "RELIANCE", "status": "ok", "signal": "BUY", "entry_price": 100, "exit_price": 108, "return_pct": 8.0, "return_bucket": "POSITIVE"},
            {"symbol": "HDFCBANK", "status": "ok", "signal": "BUY", "entry_price": 100, "exit_price": 90, "return_pct": -10.0, "return_bucket": "NEGATIVE"},
            {"symbol": "INFY", "status": "ok", "signal": "REJECT", "entry_price": None, "exit_price": None, "return_pct": None},
        ],
    )

    cat = api.get("/strategy-comparison/catalog", headers=headers)
    names = {s["name"] for s in cat.json()["strategies"]}
    assert "Alpha Momentum" in names
    assert "Beta Breakout" in names
    by_name = {s["name"]: s for s in cat.json()["strategies"]}
    assert by_name["Alpha Momentum"]["latest_run"]
    assert by_name["Alpha Momentum"]["latest_run"]["run_id"] == run_a.public_run_id
    suggestions = cat.json().get("suggestions") or []
    assert suggestions
    assert {a_id, b_id} == set(suggestions[0]["strategy_ids"])

    runs_a = api.get(f"/strategy-comparison/strategies/{a_id}/runs", headers=headers)
    assert runs_a.status_code == 200, runs_a.text
    assert any(r["run_id"] == run_a.public_run_id for r in runs_a.json()["runs"])

    too_few = api.post(
        "/strategy-comparison",
        json={"slots": [{"strategy_id": a_id, "run_id": run_a.public_run_id}]},
        headers=headers,
    )
    assert too_few.status_code == 422

    compared = api.post(
        "/strategy-comparison",
        json={
            "slots": [
                {"strategy_id": a_id, "run_id": run_a.public_run_id, "source": "strategy_tester"},
                {"strategy_id": b_id, "run_id": run_b.public_run_id, "source": "strategy_tester"},
            ]
        },
        headers=headers,
    )
    assert compared.status_code == 200, compared.text
    body = compared.json()
    assert body["slot_count"] == 2
    assert body["aligned_config"] is False
    warn_fields = {w["field"] for w in body["config_warnings"]}
    assert "universe" in warn_fields
    assert len(body["slots"]) == 2
    for slot in body["slots"]:
        assert slot["metrics"]["sharpe_ratio"] is None
        assert slot["metrics"]["cagr"] is None
        assert slot["metrics"]["net_profit"] is None
        assert slot["metrics"]["win_rate"] is not None
        assert slot["logic"]["position_type"] == "LONG"
        assert slot["metrics"]["metrics_source"] == "strategy_tester"
    signals = body["signals"]
    assert signals["available"] is True
    shared = signals["pairwise"][0]["shared_buy"]
    assert "RELIANCE" in shared
    assert body["has_equity"] is False
    radar_keys = {axis["key"] for axis in body["radar"]["axes"]}
    assert "win_rate" in radar_keys
    assert "sharpe_ratio" not in radar_keys

    swapped = api.post(
        "/strategy-comparison",
        json={
            "slots": [
                {"strategy_id": a_id, "run_id": run_b.public_run_id, "source": "strategy_tester"},
                {"strategy_id": b_id, "run_id": run_a.public_run_id, "source": "strategy_tester"},
            ]
        },
        headers=headers,
    )
    assert swapped.status_code == 400


def test_catalog_latest_run_uses_strategy_name_when_definition_id_is_missing(api):
    headers = _register(api)
    saved = api.post("/strategy-tests/strategies", json=_strategy_payload("Name Only"), headers=headers)
    assert saved.status_code == 200, saved.text
    sid = saved.json()["id"]
    defn = asyncio.run(persistence.get_definition(uuid.UUID(sid)))
    snap = parse_strategy_config(defn.config).to_snapshot()
    run = _seed_completed_run(
        user_id=defn.user_id,
        definition_id=None,
        name="Name Only",
        snapshot=snap,
        results=[{"symbol": "RELIANCE", "status": "ok", "signal": "BUY", "entry_price": 100, "exit_price": 110, "return_pct": 10.0}],
    )
    cat = api.get("/strategy-comparison/catalog", headers=headers)
    assert cat.status_code == 200, cat.text
    row = next(s for s in cat.json()["strategies"] if s["name"] == "Name Only")
    assert row["completed_run_count"] >= 1
    assert row["latest_run"]
    assert row["latest_run"]["run_id"] == run.public_run_id


def test_compare_unknown_run_is_404(api):
    headers = _register(api)
    saved = api.post("/strategy-tests/strategies", json=_strategy_payload("Only One"), headers=headers)
    assert saved.status_code == 200, saved.text
    sid = saved.json()["id"]
    res = api.post(
        "/strategy-comparison",
        json={
            "slots": [
                {"strategy_id": sid, "run_id": "STR-MISSING-1"},
                {"strategy_id": sid, "run_id": "STR-MISSING-2"},
            ]
        },
        headers=headers,
    )
    assert res.status_code == 404
