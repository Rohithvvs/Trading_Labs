"""Provider-preview for daily/index repair. No database I/O.

Process-environment credentials only:
  FYERS_APP_ID
  FYERS_ACCESS_TOKEN

Never reads DATABASE_URL, LOCAL_POSTGRES_DATABASE_URL, Settings/.env token
fields, or FyersService._client(). Never writes rows.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from .session_calendar import classify_trade_date, load_holiday_years
from .source_policy import classify_daily_index_source
from .validators.ohlcv_gate import classify_ohlcv_bar

PREVIEW_LINE = "PROVIDER PREVIEW COMPLETE — NO DATA WAS WRITTEN"
INDEX_STORE_SYMBOL = "NIFTY500"
INDEX_PROVIDER_SYMBOL = "NSE:NIFTY500-INDEX"
_MAX_RATE_LIMIT_ATTEMPTS = 3

PROPOSED_ACTION = {
    "REPAIRABLE": "REPAIR_FROM_FYERS",
    "NON_TRADING_DAY_PHANTOM": "EXCLUDE_FROM_PROVIDER_REPAIR_AND_MARK_FOR_DELETE_REVIEW",
    "NO_FYERS_BAR_ON_EXPECTED_TRADING_DAY": "KEEP_UNCHANGED_MANUAL_REVIEW",
    "NO_FYERS_BAR_ON_UNKNOWN_CALENDAR_DAY": "KEEP_UNCHANGED_MANUAL_REVIEW",
    "NO_FYERS_BAR": "KEEP_UNCHANGED_MANUAL_REVIEW",
    "FYERS_BAR_INVALID": "KEEP_UNCHANGED_PROVIDER_INVALID",
    "REQUIRES_MANUAL_REVIEW": "KEEP_UNCHANGED_MANUAL_REVIEW",
    "FYERS_AUTH_FAILED": "KEEP_UNCHANGED_AUTH_OR_REQUEST_FAILURE",
    "FYERS_REQUEST_FAILED": "KEEP_UNCHANGED_AUTH_OR_REQUEST_FAILURE",
    "FYERS_RATE_LIMITED": "KEEP_UNCHANGED_AUTH_OR_REQUEST_FAILURE",
    "FYERS_RESPONSE_INVALID": "KEEP_UNCHANGED_AUTH_OR_REQUEST_FAILURE",
    "TOKEN_MISSING": "KEEP_UNCHANGED_AUTH_OR_REQUEST_FAILURE",
}


class PreviewTokenError(RuntimeError):
    status = "TOKEN_MISSING"


class PreviewAuthError(RuntimeError):
    status = "FYERS_AUTH_FAILED"


class PreviewRateLimitError(RuntimeError):
    status = "FYERS_RATE_LIMITED"


class PreviewRequestError(RuntimeError):
    status = "FYERS_REQUEST_FAILED"


class PreviewResponseInvalidError(RuntimeError):
    status = "FYERS_RESPONSE_INVALID"


def process_env_fyers_credentials() -> tuple[str, str]:
    """Read FYERS_APP_ID / FYERS_ACCESS_TOKEN from os.environ only."""
    app_id = (os.environ.get("FYERS_APP_ID") or "").strip().strip('"').strip("'")
    token = (os.environ.get("FYERS_ACCESS_TOKEN") or "").strip().strip('"').strip("'")
    return app_id, token


def require_process_env_fyers_credentials() -> tuple[str, str]:
    app_id, token = process_env_fyers_credentials()
    if not app_id or not token:
        raise PreviewTokenError(
            "Preview uses process-environment FYERS_APP_ID and FYERS_ACCESS_TOKEN only. "
            "It does not read DATABASE_URL, .env settings, Neon, or local Postgres."
        )
    if app_id and token.startswith(f"{app_id}:"):
        token = token.split(":", 1)[1]
    return app_id, token


def _classify_fyers_http_payload(response: Any) -> None:
    if response is None:
        raise PreviewResponseInvalidError("FYERS returned an empty response")
    if not isinstance(response, dict):
        raise PreviewResponseInvalidError("FYERS returned a non-object response")
    code = response.get("code", response.get("s"))
    message = str(response.get("message") or "")
    lower = message.lower()
    code_int = None
    try:
        if code is not None:
            code_int = int(code)
    except (TypeError, ValueError):
        code_int = None
    if code_int == -16 or "expired" in lower:
        raise PreviewAuthError("FYERS access token expired")
    if code_int == -15 or "invalid token" in lower:
        raise PreviewAuthError("FYERS access token is invalid")
    if code_int == 429 or "too many requests" in lower or "rate limit" in lower:
        raise PreviewRateLimitError("FYERS rate limit")
    if code_int not in (None, 200, 0) and str(response.get("s") or "").lower() in {"error", "fail", "failed"}:
        raise PreviewRequestError("FYERS request failed")


def _parse_candles(candles: list[Any], *, range_from: date, range_to: date, symbol: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in candles:
        if not row or len(row) < 6:
            continue
        ts = row[0]
        if isinstance(ts, (int, float)):
            if ts > 10_000_000_000:
                ts = ts / 1000.0
            trade_d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        else:
            try:
                trade_d = date.fromisoformat(str(ts)[:10])
            except ValueError:
                continue
        if trade_d < range_from or trade_d > range_to:
            continue
        out.append(
            {
                "trade_date": trade_d,
                "symbol": symbol,
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
                "source": "FYERS",
            }
        )
    return out


class PreviewFyersGateway:
    """Standalone FYERS history client. Never opens Postgres/Neon/Turso."""

    def __init__(self, *, sleeper=None) -> None:
        self._client = None
        self._sleeper = sleeper or (lambda seconds: None)

    def _normalize_symbol(self, symbol: str) -> str:
        from ...utils.symbol import canonical_symbol, fyers_symbol

        return fyers_symbol(canonical_symbol(symbol))

    def _build_client(self):
        app_id, token = require_process_env_fyers_credentials()
        from fyers_apiv3 import fyersModel

        return fyersModel.FyersModel(
            is_async=False,
            client_id=app_id,
            token=token,
            log_path="",
        )

    def history(self, fyers_symbol: str, range_from: date, range_to: date) -> dict[str, Any]:
        client = self._build_client()
        payload = {
            "symbol": fyers_symbol,
            "resolution": "1D",
            "date_format": "1",
            "range_from": range_from.isoformat(),
            "range_to": range_to.isoformat(),
            "cont_flag": "1",
        }
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RATE_LIMIT_ATTEMPTS + 1):
            try:
                response = client.history(data=payload)
                _classify_fyers_http_payload(response)
                if not isinstance(response, dict):
                    raise PreviewResponseInvalidError("FYERS history payload is invalid")
                return response
            except PreviewRateLimitError as exc:
                last_exc = exc
                if attempt >= _MAX_RATE_LIMIT_ATTEMPTS:
                    raise
                self._sleeper(45 * attempt)
            except PreviewAuthError:
                raise
            except PreviewTokenError:
                raise
            except PreviewResponseInvalidError:
                raise
            except PreviewRequestError:
                raise
            except Exception as exc:
                raise PreviewRequestError("FYERS request failed") from exc
        raise last_exc or PreviewRateLimitError("FYERS rate limit")


class _NoopProvider:
    async def fetch_daily_session(self, symbol: str, session: date) -> dict[str, Any] | None:
        raise RuntimeError("FYERS must not be called for non-trading-day phantom rows")

    async def fetch_index_range(
        self,
        range_from: date,
        range_to: date,
        provider_symbol: str | None = None,
        store_symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        raise RuntimeError("FYERS must not be called for non-trading-day phantom rows")


class PreviewSessionProvider:
    def __init__(self, gateway: PreviewFyersGateway | None = None) -> None:
        self.gateway = gateway or PreviewFyersGateway()

    async def fetch_daily_session(self, symbol: str, session: date) -> dict[str, Any] | None:
        fyers_sym = self.gateway._normalize_symbol(symbol)
        response = self.gateway.history(fyers_sym, session, session)
        candles = response.get("candles") if isinstance(response, dict) else None
        if not candles:
            return None
        rows = _parse_candles(list(candles), range_from=session, range_to=session, symbol=symbol)
        return rows[0] if rows else None

    async def fetch_index_range(
        self,
        range_from: date,
        range_to: date,
        provider_symbol: str | None = None,
        store_symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        prov = provider_symbol or INDEX_PROVIDER_SYMBOL
        store = store_symbol or INDEX_STORE_SYMBOL
        response = self.gateway.history(prov, range_from, range_to)
        candles = response.get("candles") if isinstance(response, dict) else None
        if not candles:
            return []
        rows = _parse_candles(list(candles), range_from=range_from, range_to=range_to, symbol=store)
        for row in rows:
            row["symbol"] = store
            row["source"] = "FYERS"
        return rows


class SessionProvider(Protocol):
    async def fetch_daily_session(self, symbol: str, session: date) -> dict[str, Any] | None:
        ...

    async def fetch_index_range(
        self,
        range_from: date,
        range_to: date,
        provider_symbol: str | None = None,
        store_symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        ...


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _diff(old: Any, new: Any) -> str | None:
    left, right = _dec(old), _dec(new)
    if left is None or right is None:
        return None
    return format(right - left, "f")


def _is_index_key(table: str, symbol: str) -> bool:
    return table == "index_ohlcv" or symbol.upper().replace(" ", "") in {"NIFTY500"}


def _group_counts(rows: list[dict[str, Any]], key) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = key(row) if callable(key) else row.get(key)
        name = str(value or "")
        counts[name] = counts.get(name, 0) + 1
    return counts


def original_ohlcv(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume": row.get("volume"),
        "source": row.get("source"),
        "loaded_at": row.get("loaded_at"),
    }


def _provider_bar_payload(bar: dict[str, Any] | None) -> dict[str, Any] | None:
    if not bar:
        return None
    return {
        "trade_date": str(bar.get("trade_date")) if bar.get("trade_date") is not None else None,
        "symbol": bar.get("symbol"),
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": bar.get("close"),
        "volume": bar.get("volume"),
        "source": bar.get("source"),
    }


def classify_preview(
    *,
    requested_date: date,
    bars: list[dict[str, Any]],
    requested_symbol: str | None = None,
    calendar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not bars:
        status = (calendar or {}).get("calendar_status")
        if status == "EXPECTED_NSE_TRADING_SESSION":
            verdict = "NO_FYERS_BAR_ON_EXPECTED_TRADING_DAY"
        elif status == "WEEKDAY_UNKNOWN":
            verdict = "NO_FYERS_BAR_ON_UNKNOWN_CALENDAR_DAY"
        else:
            verdict = "NO_FYERS_BAR"
        return {
            "verdict": verdict,
            "matching_date": False,
            "ohlc_gate": None,
            "source_policy": None,
            "reason": "provider returned no bar",
        }
    if len(bars) != 1:
        return {
            "verdict": "REQUIRES_MANUAL_REVIEW",
            "matching_date": False,
            "ohlc_gate": None,
            "source_policy": None,
            "reason": f"expected exactly one bar, got {len(bars)}",
        }
    bar = bars[0]
    returned_date = _as_date(bar.get("trade_date"))
    matching = returned_date == requested_date
    source_cls = classify_daily_index_source(bar.get("source"))
    if source_cls["decision"] != "accept" or bar.get("source") in {"historical_candles", "FYERS_LIVE_1D"}:
        return {
            "verdict": "REQUIRES_MANUAL_REVIEW",
            "matching_date": matching,
            "ohlc_gate": None,
            "source_policy": source_cls,
            "reason": "provider source not allowlisted or ACS/live fallback",
        }
    if requested_symbol and requested_symbol.upper().replace(" ", "") in {"NIFTY500"}:
        returned_sym = str(bar.get("symbol") or "")
        if returned_sym.replace(" ", "").upper() not in {"NIFTY500"}:
            return {
                "verdict": "REQUIRES_MANUAL_REVIEW",
                "matching_date": matching,
                "ohlc_gate": None,
                "source_policy": source_cls,
                "reason": f"index mapping mismatch ({returned_sym})",
            }
    if not matching:
        return {
            "verdict": "REQUIRES_MANUAL_REVIEW",
            "matching_date": False,
            "ohlc_gate": None,
            "source_policy": source_cls,
            "reason": f"provider date {returned_date} != requested session {requested_date}",
        }
    gate = classify_ohlcv_bar(
        {
            "trade_date": returned_date,
            "symbol": bar.get("symbol"),
            "open": bar.get("open"),
            "high": bar.get("high"),
            "low": bar.get("low"),
            "close": bar.get("close"),
            "volume": bar.get("volume"),
            "source": "FYERS",
        }
    )
    if gate["decision"] == "reject":
        return {
            "verdict": "FYERS_BAR_INVALID",
            "matching_date": True,
            "ohlc_gate": gate,
            "source_policy": source_cls,
            "reason": gate["material_reasons"],
        }
    return {
        "verdict": "REPAIRABLE",
        "matching_date": True,
        "ohlc_gate": gate,
        "source_policy": source_cls,
        "reason": None,
    }


async def _fetch_bars(
    provider: SessionProvider,
    *,
    table: str,
    symbol: str,
    session: date,
) -> tuple[list[dict[str, Any]], str]:
    if _is_index_key(table, symbol):
        rows = await provider.fetch_index_range(session, session)
        return list(rows or []), "PreviewSessionProvider.fetch_index_range"
    bar = await provider.fetch_daily_session(symbol, session)
    if bar is None:
        return [], "PreviewSessionProvider.fetch_daily_session"
    return [bar], "PreviewSessionProvider.fetch_daily_session"


def _row_record(
    *,
    table: str,
    symbol: str,
    trade_date: str,
    original: dict[str, Any],
    fyers_bar: dict[str, Any] | None,
    path: str | None,
    bars_len: int,
    outcome: dict[str, Any],
    diffs: dict[str, Any],
    calendar: dict[str, Any] | None = None,
    provider_called: bool = False,
) -> dict[str, Any]:
    verdict = outcome["verdict"]
    cal = calendar or {}
    return {
        "table": table,
        "symbol": symbol,
        "trade_date": trade_date,
        "day_of_week": cal.get("day_of_week"),
        "calendar_status": cal.get("calendar_status"),
        "original": original,
        "fyers_bar": fyers_bar,
        "provider_path": path,
        "provider_status": verdict,
        "provider_metadata": {
            "path": path,
            "source": None if fyers_bar is None else fyers_bar.get("source"),
            "returned_symbol": None if fyers_bar is None else fyers_bar.get("symbol"),
            "returned_trade_date": None if fyers_bar is None else fyers_bar.get("trade_date"),
            "bar_count": bars_len,
        },
        "matching_date": outcome.get("matching_date"),
        "ohlc_gate": outcome.get("ohlc_gate"),
        "source_policy_allows_replacement": bool(
            (outcome.get("source_policy") or {}).get("decision") == "accept"
        )
        if outcome.get("source_policy")
        else False,
        "diffs": diffs,
        "verdict": verdict,
        "proposed_action": PROPOSED_ACTION.get(verdict, "KEEP_UNCHANGED_MANUAL_REVIEW"),
        "provider_called": provider_called,
        "reason": outcome.get("reason"),
    }


async def preview_provider_keys(
    anomalies: list[dict[str, Any]],
    *,
    symbols: list[str] | None = None,
    dates: list[str] | None = None,
    tables: list[str] | None = None,
    limit: int | None = None,
    provider: SessionProvider | None = None,
) -> dict[str, Any]:
    wanted_symbols = {s.strip().upper() for s in (symbols or []) if s.strip()}
    wanted_dates = {d.strip()[:10] for d in (dates or []) if d.strip()}
    wanted_tables = {t.strip() for t in (tables or []) if t.strip()}
    report_symbols = {str(a.get("symbol") or "").strip().upper() for a in anomalies}
    report_dates = {str(a.get("trade_date") or "").strip()[:10] for a in anomalies}
    unknown_symbols = sorted(wanted_symbols - report_symbols) if wanted_symbols else []
    unknown_dates = sorted(wanted_dates - report_dates) if wanted_dates else []

    skipped: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in anomalies:
        table = str(raw.get("table") or "daily_ohlcv")
        symbol = str(raw.get("symbol") or "").strip()
        trade_date = str(raw.get("trade_date") or "").strip()[:10]
        if not symbol or not trade_date:
            skipped.append({"reason": "incomplete_key", "symbol": symbol, "trade_date": trade_date})
            continue
        key = (table, symbol, trade_date)
        if key in seen:
            skipped.append({"reason": "duplicate_key", "table": table, "symbol": symbol, "trade_date": trade_date})
            continue
        seen.add(key)
        if wanted_tables and table not in wanted_tables:
            skipped.append({"reason": "table_filter", "table": table, "symbol": symbol, "trade_date": trade_date})
            continue
        if wanted_symbols and symbol.upper() not in wanted_symbols:
            skipped.append({"reason": "symbol_filter", "table": table, "symbol": symbol, "trade_date": trade_date})
            continue
        if wanted_dates and trade_date not in wanted_dates:
            skipped.append({"reason": "date_filter", "table": table, "symbol": symbol, "trade_date": trade_date})
            continue
        selected.append(raw)

    considered = len(anomalies)
    if limit is not None:
        selected = selected[: max(int(limit), 0)]

    holidays = load_holiday_years()
    classified_selected: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for raw in selected:
        session = _as_date(str(raw.get("trade_date") or "").strip()[:10])
        cal = classify_trade_date(session, holidays_by_year=holidays) if session else None
        classified_selected.append((raw, cal))

    need_provider = [
        1
        for raw, cal in classified_selected
        if cal is not None and cal.get("should_call_provider")
    ]
    if need_provider and provider is None:
        require_process_env_fyers_credentials()
        provider = PreviewSessionProvider()
    elif provider is None:
        provider = _NoopProvider()

    rows: list[dict[str, Any]] = []
    abort_status: str | None = None
    abort_reason: str | None = None
    provider_calls = 0
    provider_calls_avoided = 0
    for raw, cal in classified_selected:
        table = str(raw.get("table") or "daily_ohlcv")
        symbol = str(raw.get("symbol") or "").strip()
        trade_date = str(raw.get("trade_date") or "").strip()[:10]
        original = original_ohlcv(raw)
        session = _as_date(trade_date)
        if session is None or cal is None:
            rows.append(
                _row_record(
                    table=table,
                    symbol=symbol,
                    trade_date=trade_date,
                    original=original,
                    fyers_bar=None,
                    path=None,
                    bars_len=0,
                    outcome={
                        "verdict": "REQUIRES_MANUAL_REVIEW",
                        "matching_date": False,
                        "ohlc_gate": None,
                        "source_policy": None,
                        "reason": "invalid requested trade_date",
                    },
                    diffs={},
                    calendar=cal,
                    provider_called=False,
                )
            )
            continue
        if not cal.get("should_call_provider"):
            provider_calls_avoided += 1
            rows.append(
                _row_record(
                    table=table,
                    symbol=symbol,
                    trade_date=trade_date,
                    original=original,
                    fyers_bar=None,
                    path=None,
                    bars_len=0,
                    outcome={
                        "verdict": "NON_TRADING_DAY_PHANTOM",
                        "matching_date": False,
                        "ohlc_gate": None,
                        "source_policy": None,
                        "reason": "non-trading-day phantom; FYERS not called",
                    },
                    diffs={},
                    calendar=cal,
                    provider_called=False,
                )
            )
            continue
        try:
            bars, path = await _fetch_bars(provider, table=table, symbol=symbol, session=session)
            provider_calls += 1
        except PreviewTokenError as exc:
            abort_status, abort_reason = "TOKEN_MISSING", str(exc)
            break
        except PreviewAuthError as exc:
            abort_status, abort_reason = "FYERS_AUTH_FAILED", str(exc)
            break
        except PreviewRateLimitError as exc:
            abort_status, abort_reason = "FYERS_RATE_LIMITED", str(exc)
            break
        except PreviewResponseInvalidError as exc:
            abort_status, abort_reason = "FYERS_RESPONSE_INVALID", str(exc)
            break
        except PreviewRequestError as exc:
            abort_status, abort_reason = "FYERS_REQUEST_FAILED", str(exc)
            break
        outcome = classify_preview(
            requested_date=session,
            bars=bars,
            requested_symbol=symbol,
            calendar=cal,
        )
        fyers_bar = bars[0] if len(bars) == 1 else None
        payload = _provider_bar_payload(fyers_bar)
        diffs = {}
        if fyers_bar is not None:
            diffs = {
                field: _diff(original.get(field), fyers_bar.get(field))
                for field in ("open", "high", "low", "close", "volume")
            }
        rows.append(
            _row_record(
                table=table,
                symbol=symbol,
                trade_date=trade_date,
                original=original,
                fyers_bar=payload,
                path=path,
                bars_len=len(bars),
                outcome=outcome,
                diffs=diffs,
                calendar=cal,
                provider_called=True,
            )
        )

    if abort_status:
        rows.append(
            _row_record(
                table="unknown",
                symbol="",
                trade_date="",
                original={},
                fyers_bar=None,
                path=None,
                bars_len=0,
                outcome={
                    "verdict": abort_status,
                    "matching_date": False,
                    "ohlc_gate": None,
                    "source_policy": None,
                    "reason": abort_reason,
                },
                diffs={},
            )
        )

    verdict_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    daily_n = 0
    index_n = 0
    for row in rows:
        verdict_counts[row["verdict"]] = verdict_counts.get(row["verdict"], 0) + 1
        action_counts[row["proposed_action"]] = action_counts.get(row["proposed_action"], 0) + 1
        if row["table"] == "index_ohlcv" or row["symbol"] == "NIFTY500":
            index_n += 1
        else:
            daily_n += 1

    return {
        "status": abort_status or "OK",
        "wrote": False,
        "db_connected": False,
        "turso_connected": False,
        "provider_called": provider_calls > 0,
        "provider_call_count": provider_calls,
        "provider_calls_avoided": provider_calls_avoided,
        "mode": "preview-provider",
        "considered": considered,
        "skipped": skipped,
        "skipped_count": len(skipped),
        "unknown_filters": {"symbols": unknown_symbols, "dates": unknown_dates},
        "row_count": len(rows),
        "verdict_counts": verdict_counts,
        "proposed_action_counts": action_counts,
        "calendar_counts": _group_counts(rows, "calendar_status"),
        "source_counts": _group_counts(rows, lambda r: (r.get("original") or {}).get("source")),
        "trade_date_counts": _group_counts(rows, "trade_date"),
        "repairable_count": verdict_counts.get("REPAIRABLE", 0),
        "phantom_count": verdict_counts.get("NON_TRADING_DAY_PHANTOM", 0),
        "no_data_count": (
            verdict_counts.get("NO_FYERS_BAR", 0)
            + verdict_counts.get("NO_FYERS_BAR_ON_EXPECTED_TRADING_DAY", 0)
            + verdict_counts.get("NO_FYERS_BAR_ON_UNKNOWN_CALENDAR_DAY", 0)
        ),
        "manual_review_count": verdict_counts.get("REQUIRES_MANUAL_REVIEW", 0)
        + verdict_counts.get("NO_FYERS_BAR_ON_EXPECTED_TRADING_DAY", 0)
        + verdict_counts.get("NO_FYERS_BAR_ON_UNKNOWN_CALENDAR_DAY", 0),
        "provider_invalid_count": verdict_counts.get("FYERS_BAR_INVALID", 0),
        "auth_or_request_failure_count": sum(
            verdict_counts.get(k, 0)
            for k in (
                "FYERS_AUTH_FAILED",
                "FYERS_REQUEST_FAILED",
                "FYERS_RATE_LIMITED",
                "FYERS_RESPONSE_INVALID",
                "TOKEN_MISSING",
            )
        ),
        "daily_count": daily_n,
        "index_count": index_n,
        "rows": rows,
        "abort_reason": abort_reason,
        "final_line": PREVIEW_LINE,
        "note": "Preview only. No UPDATE/INSERT. Replacement source remains FYERS when repairable.",
    }


def format_preview_text(payload: dict[str, Any]) -> str:
    lines = [
        f"status={payload.get('status')} considered={payload.get('considered')} "
        f"previewed={payload.get('row_count')} skipped={payload.get('skipped_count')}",
        f"REPAIRABLE={payload.get('repairable_count')} "
        f"PHANTOM={payload.get('phantom_count')} "
        f"provider_calls={payload.get('provider_call_count')} "
        f"avoided={payload.get('provider_calls_avoided')} "
        f"NO_FYERS_BAR={payload.get('no_data_count')} "
        f"FYERS_BAR_INVALID={payload.get('provider_invalid_count')} "
        f"MANUAL_REVIEW={payload.get('manual_review_count')} "
        f"AUTH_OR_REQUEST={payload.get('auth_or_request_failure_count')}",
        f"daily={payload.get('daily_count')} index={payload.get('index_count')}",
        f"db_connected={payload.get('db_connected')} turso_connected={payload.get('turso_connected')} wrote={payload.get('wrote')}",
    ]
    if payload.get("unknown_filters", {}).get("symbols") or payload.get("unknown_filters", {}).get("dates"):
        lines.append(f"unknown_filters={payload.get('unknown_filters')}")
    for row in payload.get("rows") or []:
        if not row.get("symbol"):
            continue
        lines.append(
            f"{row.get('table')} {row.get('symbol')} {row.get('trade_date')} "
            f"verdict={row.get('verdict')} action={row.get('proposed_action')}"
        )
    lines.append(payload.get("final_line") or PREVIEW_LINE)
    return "\n".join(lines)
