"""Provider-preview tests. Fakes only — no Postgres, Neon, Turso, or live FYERS."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.cli import ohlcv_repair_plan as repair_cli
from app.services.market_data_ingestion.repair_preview import (
    PREVIEW_LINE,
    PreviewAuthError,
    PreviewFyersGateway,
    PreviewRateLimitError,
    PreviewRequestError,
    PreviewTokenError,
    _classify_fyers_http_payload,
    classify_preview,
    preview_provider_keys,
    process_env_fyers_credentials,
    require_process_env_fyers_credentials,
)

pytestmark = pytest.mark.unit


def _anomaly(**overrides):
    row = {
        "table": "daily_ohlcv",
        "symbol": "IRFC-EQ",
        "trade_date": "2026-08-01",
        "open": 100.0,
        "high": 108.0,
        "low": 102.0,
        "close": 100.0,
        "volume": 800,
        "source": "historical_candles",
        "loaded_at": "2026-08-15T12:20:00",
    }
    row.update(overrides)
    return row


def _fyers_bar(**overrides):
    bar = {
        "trade_date": date(2026, 8, 1),
        "symbol": "IRFC-EQ",
        "open": 101.0,
        "high": 110.0,
        "low": 99.0,
        "close": 105.0,
        "volume": 2_000_000,
        "source": "FYERS",
    }
    bar.update(overrides)
    return bar


class FakeProvider:
    def __init__(self, equity=None, index=None, equity_error=None):
        self.equity = equity
        self.index = index if index is not None else []
        self.equity_error = equity_error
        self.daily_calls: list[tuple] = []
        self.index_calls: list[tuple] = []

    async def fetch_daily_session(self, symbol, session):
        self.daily_calls.append((symbol, session))
        if self.equity_error:
            raise self.equity_error
        return self.equity

    async def fetch_index_range(self, range_from, range_to, provider_symbol=None, store_symbol=None):
        self.index_calls.append((range_from, range_to, provider_symbol, store_symbol))
        return list(self.index)


def test_process_env_ignores_missing_and_does_not_use_settings(monkeypatch):
    monkeypatch.delenv("FYERS_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FYERS_APP_ID", raising=False)
    app_id, token = process_env_fyers_credentials()
    assert app_id == ""
    assert token == ""
    with pytest.raises(PreviewTokenError, match="process-environment"):
        require_process_env_fyers_credentials()


def test_classify_auth_expired_and_invalid():
    with pytest.raises(PreviewAuthError):
        _classify_fyers_http_payload({"code": -16, "message": "token expired"})
    with pytest.raises(PreviewAuthError):
        _classify_fyers_http_payload({"code": -15, "message": "invalid token"})


def test_classify_rate_limit_and_request_failed():
    with pytest.raises(PreviewRateLimitError):
        _classify_fyers_http_payload({"code": 429, "message": "too many requests"})
    with pytest.raises(PreviewRequestError):
        _classify_fyers_http_payload({"s": "error", "code": 500, "message": "boom"})


def test_valid_fyers_equity_bar_is_repairable():
    outcome = classify_preview(requested_date=date(2026, 8, 1), bars=[_fyers_bar()])
    assert outcome["verdict"] == "REPAIRABLE"


def test_missing_bar_on_expected_session():
    assert (
        classify_preview(
            requested_date=date(2026, 8, 3),
            bars=[],
            calendar={"calendar_status": "EXPECTED_NSE_TRADING_SESSION"},
        )["verdict"]
        == "NO_FYERS_BAR_ON_EXPECTED_TRADING_DAY"
    )


def test_missing_bar_on_unknown_calendar():
    assert (
        classify_preview(
            requested_date=date(2009, 5, 18),
            bars=[],
            calendar={"calendar_status": "WEEKDAY_UNKNOWN"},
        )["verdict"]
        == "NO_FYERS_BAR_ON_UNKNOWN_CALENDAR_DAY"
    )


def test_invalid_fyers_bar_is_fyers_bar_invalid():
    outcome = classify_preview(
        requested_date=date(2026, 8, 1),
        bars=[_fyers_bar(open=50.0, high=110.0, low=90.0, close=105.0)],
    )
    assert outcome["verdict"] == "FYERS_BAR_INVALID"


def test_date_mismatch_requires_manual_review():
    outcome = classify_preview(
        requested_date=date(2026, 8, 1),
        bars=[_fyers_bar(trade_date=date(2026, 8, 2))],
    )
    assert outcome["verdict"] == "REQUIRES_MANUAL_REVIEW"


@pytest.mark.asyncio
async def test_nifty500_uses_index_provider_path():
    provider = FakeProvider(
        equity=_fyers_bar(),
        index=[
            _fyers_bar(
                symbol="NIFTY500",
                trade_date=date(2026, 8, 3),
                open=10000,
                high=10100,
                low=9900,
                close=10050,
                volume=0,
            )
        ],
    )
    payload = await preview_provider_keys(
        [_anomaly(table="index_ohlcv", symbol="NIFTY500", trade_date="2026-08-03")],
        provider=provider,
    )
    assert provider.index_calls
    assert provider.daily_calls == []
    assert payload["rows"][0]["provider_path"] == "PreviewSessionProvider.fetch_index_range"
    assert payload["rows"][0]["verdict"] == "REPAIRABLE"


@pytest.mark.asyncio
async def test_preview_auth_error_maps_status():
    provider = FakeProvider(equity_error=PreviewAuthError("FYERS access token expired"))
    payload = await preview_provider_keys(
        [_anomaly(trade_date="2026-08-03")], provider=provider
    )
    assert payload["status"] == "FYERS_AUTH_FAILED"
    assert payload["wrote"] is False
    assert payload["db_connected"] is False


@pytest.mark.asyncio
async def test_preview_request_and_rate_limit_map_status():
    provider = FakeProvider(equity_error=PreviewRequestError("FYERS request failed"))
    payload = await preview_provider_keys(
        [_anomaly(trade_date="2026-08-03")], provider=provider
    )
    assert payload["status"] == "FYERS_REQUEST_FAILED"
    provider2 = FakeProvider(equity_error=PreviewRateLimitError("FYERS rate limit"))
    payload2 = await preview_provider_keys(
        [_anomaly(trade_date="2026-08-03")], provider=provider2
    )
    assert payload2["status"] == "FYERS_RATE_LIMITED"


@pytest.mark.asyncio
async def test_preview_json_contains_no_token_or_app_id():
    payload = await preview_provider_keys(
        [_anomaly(trade_date="2026-08-03")],
        provider=FakeProvider(equity=_fyers_bar(trade_date=date(2026, 8, 3))),
    )
    dumped = json.dumps(payload)
    assert "preview-token" not in dumped
    assert "FYERS_ACCESS_TOKEN" not in dumped
    assert "APPID-100" not in dumped
    assert payload["rows"][0]["proposed_action"] == "REPAIR_FROM_FYERS"
    assert payload["rows"][0]["original"]["loaded_at"]


@pytest.mark.asyncio
async def test_filters_report_skipped_keys():
    payload = await preview_provider_keys(
        [_anomaly(), _anomaly(symbol="BEL-EQ", trade_date="2026-08-25")],
        symbols=["IRFC-EQ"],
        dates=["2026-08-01"],
        provider=FakeProvider(equity=_fyers_bar()),
    )
    assert payload["skipped_count"] >= 1
    assert payload["row_count"] == 1
    assert payload["unknown_filters"]["symbols"] == []


@pytest.mark.asyncio
async def test_saturday_is_phantom_and_skips_fyers():
    provider = FakeProvider(equity=_fyers_bar())
    payload = await preview_provider_keys([_anomaly()], provider=provider)
    row = payload["rows"][0]
    assert row["trade_date"] == "2026-08-01"
    assert row["day_of_week"] == "Saturday"
    assert row["calendar_status"] == "WEEKEND_NON_TRADING_DAY"
    assert row["verdict"] == "NON_TRADING_DAY_PHANTOM"
    assert row["proposed_action"] == "EXCLUDE_FROM_PROVIDER_REPAIR_AND_MARK_FOR_DELETE_REVIEW"
    assert row["provider_called"] is False
    assert provider.daily_calls == []
    assert payload["provider_calls_avoided"] == 1
    assert payload["provider_call_count"] == 0
    assert row["original"]["source"] == "historical_candles"


@pytest.mark.asyncio
async def test_nse_holiday_is_phantom_without_fyers():
    provider = FakeProvider(equity=_fyers_bar())
    payload = await preview_provider_keys(
        [_anomaly(trade_date="2026-01-26")],
        provider=provider,
    )
    row = payload["rows"][0]
    assert row["calendar_status"] == "NSE_HOLIDAY_NON_TRADING_DAY"
    assert row["verdict"] == "NON_TRADING_DAY_PHANTOM"
    assert provider.daily_calls == []


@pytest.mark.asyncio
async def test_year_without_holiday_file_is_weekday_unknown_and_calls_provider():
    provider = FakeProvider(equity=_fyers_bar(trade_date=date(2009, 5, 18), symbol="NIFTY500"))
    payload = await preview_provider_keys(
        [_anomaly(table="index_ohlcv", symbol="NIFTY500", trade_date="2009-05-18")],
        provider=provider,
    )
    row = payload["rows"][0]
    assert row["calendar_status"] == "WEEKDAY_UNKNOWN"
    assert provider.index_calls
    assert row["verdict"] in {
        "REPAIRABLE",
        "NO_FYERS_BAR_ON_UNKNOWN_CALENDAR_DAY",
        "FYERS_BAR_INVALID",
        "REQUIRES_MANUAL_REVIEW",
    }


def test_preview_module_has_no_db_or_fyers_service_import():
    text = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "market_data_ingestion"
        / "repair_preview.py"
    ).read_text(encoding="utf-8")
    assert "AsyncSessionLocal" not in text
    assert "FyersService._client()" in text  # documented as forbidden only
    assert "from ...fyers_service" not in text
    assert "import FyersService" not in text
    assert "token_service" not in text
    assert "DATABASE_URL" in text  # mentioned only as something we do not read
    assert "HistoricalCandle" not in text


def test_gateway_builds_client_from_process_env(monkeypatch):
    monkeypatch.setenv("FYERS_ACCESS_TOKEN", "preview-token")
    monkeypatch.setenv("FYERS_APP_ID", "APPID-100")
    captured: dict = {}

    class FakeModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import fyers_apiv3.fyersModel as fm

    monkeypatch.setattr(fm, "FyersModel", FakeModel)
    client = PreviewFyersGateway()._build_client()
    assert captured["token"] == "preview-token"
    assert captured["client_id"] == "APPID-100"
    assert client is not None


def test_cli_missing_token_json(monkeypatch, capsys, tmp_path):
    report = tmp_path / "anomalies.json"
    report.write_text(json.dumps({"anomalies": [_anomaly()]}), encoding="utf-8")

    async def boom(*args, **kwargs):
        raise PreviewTokenError("Preview uses process-environment FYERS_APP_ID")

    monkeypatch.setattr(
        "app.services.market_data_ingestion.repair_preview.preview_provider_keys",
        boom,
    )
    code = repair_cli.main(["--preview-provider", "--from-anomaly-json", str(report), "--json"])
    assert code == 2
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["status"] == "TOKEN_MISSING"
    assert payload["db_connected"] is False
    assert PREVIEW_LINE in out
