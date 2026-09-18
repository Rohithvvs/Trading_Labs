"""NSE delivery statistics provider.

Primary source: daily **MTO** (Security-wise Delivery Position) archives, which
include deliverable qty / % and are available multi-year on nsearchives/archives.

Fallback: ``sec_bhavdata_full_DDMMYYYY.csv`` (has DELIV_QTY / DELIV_PER).

UDiFF CM bhavcopy is **not** used for delivery (no delivery columns).

**Limitations (documented):**
- Files exist only for NSE cash **trading sessions** (not weekends/holidays).
- Archive gaps or URL changes leave delivery fields NULL — never invented.
- Practical history via MTO has been verified back several years; if a day is
  missing from the archive, that session stays NULL.

Joins by symbol (with/without -EQ) and ISIN when present.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import zipfile
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import httpx

from ..validators.delivery_rules import validate_delivery_fields

logger = logging.getLogger("app.market_data_ingestion.nse_delivery")

# Prefer MTO (true delivery file), then full bhav with DELIV_* columns.
_MTO_URLS = (
    "https://nsearchives.nseindia.com/archives/equities/mto/MTO_{ddmmyyyy}.DAT",
    "https://archives.nseindia.com/archives/equities/mto/MTO_{ddmmyyyy}.DAT",
)

_SEC_BHAV_URLS = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv",
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv",
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 0.75


def _ddmmyyyy(d: date) -> str:
    return d.strftime("%d%m%Y")


def _is_likely_series(token: str) -> bool:
    t = (token or "").strip().upper()
    return 1 <= len(t) <= 3 and t.isalpha()


class NseDeliveryProvider:
    """Fetch per-session delivery maps. Fail soft → empty map."""

    def __init__(self, *, timeout_s: float = 30.0) -> None:
        self._timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout_s,
                headers=_HEADERS,
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def fetch_session_delivery(self, session: date) -> dict[str, dict[str, Any]]:
        """Return map keyed by SYMBOL / SYMBOL-EQ / ISIN → delivery fields."""
        # 1) MTO security-wise delivery (best multi-year source)
        text = await self._download_first_ok(
            [u.format(ddmmyyyy=_ddmmyyyy(session)) for u in _MTO_URLS],
            session=session,
            kind="MTO",
        )
        if text:
            parsed = self._parse_mto(text)
            if parsed:
                return parsed

        # 2) Full bhav with DELIV_QTY / DELIV_PER
        text = await self._download_first_ok(
            [u.format(ddmmyyyy=_ddmmyyyy(session)) for u in _SEC_BHAV_URLS],
            session=session,
            kind="SEC_BHAV",
        )
        if text:
            parsed = self._parse_bhav_csv(text)
            if parsed:
                return parsed

        logger.debug("NSE_DELIVERY_UNAVAILABLE | session=%s", session.isoformat())
        return {}

    async def fetch_range_delivery(
        self,
        range_from: date,
        range_to: date,
        *,
        trading_days_only: bool = True,
        concurrency: int = 6,
    ) -> dict[date, dict[str, dict[str, Any]]]:
        """Fetch delivery maps for each session in [range_from, range_to].

        Skips non-trading days when ``trading_days_only`` (uses TradingHoursService).
        """
        days = list(self._iter_sessions(range_from, range_to, trading_days_only=trading_days_only))
        if not days:
            return {}
        sem = asyncio.Semaphore(max(1, min(concurrency, 12)))
        out: dict[date, dict[str, dict[str, Any]]] = {}

        async def one(d: date) -> None:
            async with sem:
                try:
                    out[d] = await self.fetch_session_delivery(d)
                except Exception as exc:
                    logger.warning(
                        "NSE_DELIVERY_RANGE_FAIL | session=%s | err=%s",
                        d.isoformat(),
                        type(exc).__name__,
                    )
                    out[d] = {}

        await asyncio.gather(*[one(d) for d in days])
        ok = sum(1 for d in days if out.get(d))
        logger.info(
            "NSE_DELIVERY_RANGE_DONE | from=%s | to=%s | sessions=%s | with_data=%s",
            range_from.isoformat(),
            range_to.isoformat(),
            len(days),
            ok,
        )
        return out

    def _iter_sessions(
        self,
        range_from: date,
        range_to: date,
        *,
        trading_days_only: bool,
    ) -> Iterable[date]:
        if range_from > range_to:
            return
        th = None
        if trading_days_only:
            try:
                from ...trading_hours_service import TradingHoursService, trading_hours

                th = trading_hours if trading_hours is not None else TradingHoursService()
            except Exception:
                th = None

        cur = range_from
        while cur <= range_to:
            if th is None:
                # Fallback: skip weekends only
                if cur.weekday() < 5:
                    yield cur
            else:
                try:
                    if th.is_trading_day(datetime(cur.year, cur.month, cur.day)):
                        yield cur
                except Exception:
                    if cur.weekday() < 5:
                        yield cur
            cur += timedelta(days=1)

    async def _download_first_ok(
        self,
        urls: list[str],
        *,
        session: date,
        kind: str,
    ) -> str | None:
        client = await self._get_client()
        for url in urls:
            content = await self._get_with_retries(client, url, session=session, kind=kind)
            if not content:
                continue
            if content[:2] == b"PK":
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as zf:
                        name = zf.namelist()[0]
                        return zf.read(name).decode("utf-8", errors="replace")
                except Exception as exc:
                    logger.warning(
                        "NSE_DELIVERY_ZIP_FAIL | kind=%s | session=%s | err=%s",
                        kind,
                        session.isoformat(),
                        type(exc).__name__,
                    )
                    continue
            # HTML error page
            head = content[:200].lstrip().lower()
            if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                continue
            return content.decode("utf-8", errors="replace")
        return None

    async def _get_with_retries(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        session: date,
        kind: str,
    ) -> bytes | None:
        last_status = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await client.get(url)
                last_status = resp.status_code
                if resp.status_code == 200 and resp.content:
                    return resp.content
                if resp.status_code in {404, 403}:
                    # try next URL / no point hammering
                    return None
                if resp.status_code >= 500 or resp.status_code == 429:
                    await asyncio.sleep(_RETRY_BACKOFF_S * attempt)
                    continue
                return None
            except Exception as exc:
                logger.debug(
                    "NSE_DELIVERY_HTTP_ERR | kind=%s | session=%s | attempt=%s | err=%s",
                    kind,
                    session.isoformat(),
                    attempt,
                    type(exc).__name__,
                )
                await asyncio.sleep(_RETRY_BACKOFF_S * attempt)
        logger.debug(
            "NSE_DELIVERY_HTTP_GIVEUP | kind=%s | session=%s | status=%s | url=%s",
            kind,
            session.isoformat(),
            last_status,
            url[:80],
        )
        return None

    def _parse_mto(self, text: str) -> dict[str, dict[str, Any]]:
        """Parse MTO_*.DAT security-wise delivery file."""
        out: dict[str, dict[str, Any]] = {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("Security Wise") or line.startswith("Trade Date"):
                continue
            if line.startswith("Record Type"):
                continue
            # Header summary rows: 10,MTO,...
            if line.startswith("10,"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            if parts[0] != "20":
                continue
            # 20,sr,SYMBOL,SERIES,traded,deliv,pct  OR  20,sr,SYMBOL,traded,deliv,pct
            try:
                if len(parts) >= 7 and _is_likely_series(parts[3]):
                    symbol = parts[2].upper()
                    series = parts[3].upper()
                    traded_s, deliv_s, pct_s = parts[4], parts[5], parts[6]
                else:
                    symbol = parts[2].upper()
                    series = "EQ"
                    traded_s, deliv_s, pct_s = parts[3], parts[4], parts[5]
            except Exception:
                continue
            if series and series not in {"EQ", "BE", "BZ"}:
                # Still store EQ-like liquid names; skip most non-equity series for strategy use
                if series not in {"EQ", "BE", "BZ", "SM", "ST"}:
                    continue
            validated = validate_delivery_fields(deliv_s, traded_s)
            if validated["delivery_pct"] is None and pct_s not in (None, ""):
                try:
                    validated["delivery_pct"] = float(str(pct_s).replace("%", "").strip())
                except ValueError:
                    pass
            if (
                validated["delivery_qty"] is None
                and validated["delivery_pct"] is None
                and validated["traded_qty"] is None
            ):
                continue
            rec = {
                "symbol": symbol,
                "isin": None,
                "delivery_qty": validated["delivery_qty"],
                "traded_qty": validated["traded_qty"],
                "delivery_pct": validated["delivery_pct"],
            }
            out[symbol] = rec
            out[f"{symbol}-EQ"] = rec
        return out

    def _parse_bhav_csv(self, text: str) -> dict[str, dict[str, Any]]:
        # Normalize headers (sec_bhavdata_full has leading spaces in field names)
        sample = text.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(sample))
        if not reader.fieldnames:
            return {}
        # Rebuild with stripped fieldnames
        fieldnames = [f.strip() if f else f for f in reader.fieldnames]
        out: dict[str, dict[str, Any]] = {}

        def pick(row: dict, *names: str) -> str | None:
            lower = {k.lower().strip(): k for k in row.keys() if k}
            for n in names:
                k = lower.get(n.lower())
                if k and row.get(k) not in (None, ""):
                    return str(row[k]).strip()
            return None

        # Re-read with cleaned headers
        rows_iter = csv.reader(io.StringIO(sample))
        header = next(rows_iter, None)
        if not header:
            return out
        header = [h.strip() for h in header]

        for raw_vals in rows_iter:
            if not raw_vals:
                continue
            row = {header[i]: raw_vals[i] if i < len(raw_vals) else "" for i in range(len(header))}
            series = (pick(row, "SERIES", "Series", "SctySrs") or "").upper()
            if series and series not in {"EQ", "BE", "BZ", "SM", "ST"}:
                continue
            symbol = (pick(row, "SYMBOL", "Symbol", "TckrSymb") or "").upper()
            if not symbol:
                continue
            isin = pick(row, "ISIN", "ISIN Code", "Isin")
            deliv_qty_col = pick(
                row, "DELIV_QTY", "Deliverable Qty", "DELIVERY_QTY", "DelivQty"
            )
            traded_col = pick(
                row,
                "TTL_TRD_QNTY",
                "TOTTRDQTY",
                "Total Traded Quantity",
                "TtlTradgVol",
                "NO_OF_SHRS",
            )
            validated = validate_delivery_fields(deliv_qty_col, traded_col)
            deliv_per = pick(row, "DELIV_PER", "Deliverable Percentage", "DELIVERY_PER")
            if validated["delivery_pct"] is None and deliv_per is not None:
                try:
                    validated["delivery_pct"] = float(str(deliv_per).replace("%", "").strip())
                except ValueError:
                    pass
            if (
                validated["delivery_qty"] is None
                and validated["delivery_pct"] is None
            ):
                continue
            rec = {
                "symbol": symbol,
                "isin": isin,
                "delivery_qty": validated["delivery_qty"],
                "traded_qty": validated["traded_qty"],
                "delivery_pct": validated["delivery_pct"],
            }
            out[symbol] = rec
            out[f"{symbol}-EQ"] = rec
            if isin:
                out[isin.upper()] = rec
        return out

    def lookup(
        self,
        delivery_map: dict[str, dict[str, Any]],
        *,
        symbol: str,
        isin: str | None = None,
    ) -> dict[str, Any] | None:
        if not delivery_map:
            return None
        if isin and isin.upper() in delivery_map:
            return delivery_map[isin.upper()]
        raw = symbol.upper().replace("NSE:", "")
        if raw in delivery_map:
            return delivery_map[raw]
        base = raw.replace("-EQ", "")
        return delivery_map.get(base) or delivery_map.get(f"{base}-EQ")
