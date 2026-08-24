import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select
from ..config.settings import ROOT_DIR, settings
from ..db.session import AsyncSessionLocal
from ..models.stock import StockMaster
from ..schemas.workstation import UniverseInstrument, UniverseValidationReport
from ..utils.symbol import canonical_symbol, fyers_symbol
from .universe_csv import load_unique_nifty500_csv_rows

logger = logging.getLogger("app.services.universe")

_DEFAULT_EXCHANGE = "NSE"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UniverseService:
    @staticmethod
    async def get_active_symbols(universe: str) -> list[str]:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.scalars(
                    select(StockMaster.symbol)
                    .where(StockMaster.is_active == True)
                    .where(StockMaster.universe == universe)
                )
                symbols = list(result.all())
                return symbols
        except Exception as e:
            logger.error(f"Failed to fetch active symbols for universe {universe}: {e}")
            return []

    @staticmethod
    async def get_active_nifty500_symbols() -> list[str]:
        """Active NIFTY 500 membership for strategy market-data loads."""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.scalars(
                    select(StockMaster.symbol)
                    .where(StockMaster.is_active == True)
                    .where(
                        or_(
                            StockMaster.is_nifty500 == True,
                            StockMaster.universe == "NIFTY500",
                        )
                    )
                )
                symbols = list(result.all())
                return symbols
        except Exception as e:
            logger.error("Failed to fetch active NIFTY500 symbols: %s", e)
            return []

    @staticmethod
    async def get_all_active_symbols() -> list[str]:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.scalars(
                    select(StockMaster.symbol)
                    .where(StockMaster.is_active == True)
                )
                symbols = list(result.all())
                return symbols
        except Exception as e:
            logger.error(f"Failed to fetch all active symbols: {e}")
            return []

    @staticmethod
    async def get_company_name_map(universe: str | None = None) -> dict[str, str]:
        """Returns mapping from canonical, stored, and broker symbols to company names."""
        instruments = await UniverseService.list_active_instruments(universe)
        mapping: dict[str, str] = {}
        for inst in instruments:
            if inst.company_name:
                mapping[inst.symbol] = inst.company_name
                mapping[inst.universe_symbol] = inst.company_name
                if inst.broker_symbol:
                    mapping[inst.broker_symbol] = inst.company_name
        return mapping

    @staticmethod
    def get_company_name_map_sync() -> dict[str, str]:
        """Synchronous mapping from canonical, stored, and broker symbols to company names from CSV."""
        from .universe_service import load_unique_nifty500_csv_rows
        rows = load_unique_nifty500_csv_rows()
        mapping: dict[str, str] = {}
        for row in rows:
            if row.company_name:
                mapping[row.symbol] = row.company_name
                mapping[f"{row.symbol}-EQ"] = row.company_name
                mapping[f"NSE:{row.symbol}-EQ"] = row.company_name
        return mapping

    @staticmethod
    async def touch_lifecycle(symbols: list[str], *, is_nifty500: bool = True) -> None:
        """Update last_seen / first_seen / is_nifty500 for seen symbols."""
        if not symbols:
            return
        now = _utc_now()
        try:
            async with AsyncSessionLocal() as db:
                rows = (
                    await db.scalars(
                        select(StockMaster).where(StockMaster.symbol.in_(symbols))
                    )
                ).all()
                for row in rows:
                    if row.first_seen is None:
                        row.first_seen = now
                    row.last_seen = now
                    if is_nifty500:
                        row.is_nifty500 = True
                        row.universe = row.universe or "NIFTY500"
                    row.is_active = True
                await db.commit()
        except Exception as e:
            logger.warning("touch_lifecycle failed: %s", e)

    @staticmethod
    async def reconcile_nifty500(active_symbols: list[str]) -> None:
        """Soft-deactivate members no longer in the provided active NIFTY500 set."""
        active_set = set(active_symbols)
        now = _utc_now()
        try:
            async with AsyncSessionLocal() as db:
                await UniverseService.touch_lifecycle(list(active_set), is_nifty500=True)
                rows = (
                    await db.scalars(
                        select(StockMaster).where(
                            or_(
                                StockMaster.is_nifty500 == True,
                                StockMaster.universe == "NIFTY500",
                            )
                        )
                    )
                ).all()
                for row in rows:
                    if row.symbol not in active_set:
                        row.is_nifty500 = False
                        row.is_active = False
                        row.last_seen = now
                await db.commit()
        except Exception as e:
            logger.warning("reconcile_nifty500 failed: %s", e)

    @staticmethod
    def _instrument_from_row(row: StockMaster) -> UniverseInstrument | None:
        stock_id = int(row.id) if row.id is not None else None
        raw = (row.symbol or "").strip()
        if not raw:
            logger.warning(
                "SYMBOL_MISSING_FROM_UNIVERSE | stock_id=%s | universe=%s | reason=empty_stored_symbol",
                stock_id,
                row.universe,
            )
            return None
        canon = canonical_symbol(raw)
        if not canon:
            logger.warning(
                "SYMBOL_NORMALIZATION_FAILED | stock_id=%s | universe_symbol=%s | reason=empty_canonical",
                stock_id,
                raw,
            )
            return None
        broker = fyers_symbol(canon, exchange=_DEFAULT_EXCHANGE)
        if not broker:
            logger.warning(
                "BROKER_SYMBOL_MAPPING_FAILED | stock_id=%s | canonical_symbol=%s | exchange=%s",
                stock_id,
                canon,
                _DEFAULT_EXCHANGE,
            )
        return UniverseInstrument(
            symbol=canon,
            universe_symbol=raw.upper(),
            company_name=(row.company_name or "").strip() or None,
            exchange=_DEFAULT_EXCHANGE,
            series=(row.series or "").strip().upper() or None,
            broker_symbol=broker,
            isin=(row.isin or "").strip() or None,
            is_active=bool(row.is_active),
            universe=row.universe,
            stock_id=stock_id,
        )

    @staticmethod
    async def list_active_instruments(universe: str | None = None) -> list[UniverseInstrument]:
        logger.info("SYMBOL_MAPPING_STARTED | universe=%s", universe or "ALL")
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(StockMaster).where(StockMaster.is_active == True)
                if universe:
                    if universe.upper().replace(" ", "") in {"NIFTY500", "NIFTY_500"}:
                        stmt = stmt.where(
                            or_(
                                StockMaster.is_nifty500 == True,
                                StockMaster.universe == "NIFTY500",
                            )
                        )
                    else:
                        stmt = stmt.where(StockMaster.universe == universe)
                rows = (await db.scalars(stmt.order_by(StockMaster.symbol))).all()
        except Exception as e:
            logger.error("SYMBOL_MAPPING_FAILED | universe=%s | error=%s", universe or "ALL", e)
            return []

        instruments: list[UniverseInstrument] = []
        seen_canonical: set[str] = set()
        for row in rows:
            item = UniverseService._instrument_from_row(row)
            if item is None:
                continue
            if item.symbol in seen_canonical:
                logger.warning(
                    "SYMBOL_DUPLICATE_DETECTED | stock_id=%s | canonical_symbol=%s | universe_symbol=%s",
                    item.stock_id,
                    item.symbol,
                    item.universe_symbol,
                )
                continue
            seen_canonical.add(item.symbol)
            if not item.broker_symbol:
                logger.warning(
                    "BROKER_SYMBOL_MAPPING_FAILED | stock_id=%s | canonical_symbol=%s | exchange=%s",
                    item.stock_id,
                    item.symbol,
                    item.exchange,
                )
            instruments.append(item)

        logger.info(
            "SYMBOL_MAPPING_COMPLETED | universe=%s | mapped=%s | source_rows=%s",
            universe or "ALL",
            len(instruments),
            len(rows),
        )
        return instruments

    @staticmethod
    def _csv_path() -> Path:
        csv_path = Path(settings.nifty500_csv_path)
        if not csv_path.is_absolute():
            csv_path = ROOT_DIR / csv_path
        return csv_path

    @staticmethod
    async def validate_universe(universe: str = "NIFTY500") -> UniverseValidationReport:
        instruments = await UniverseService.list_active_instruments(universe)
        csv_rows = load_unique_nifty500_csv_rows(UniverseService._csv_path())
        csv_by_canon = {row["canonical_symbol"]: row for row in csv_rows}

        missing: list[dict[str, str]] = []
        invalid: list[dict[str, str]] = []
        duplicate_symbols: list[str] = []
        seen: set[str] = set()
        symbols_present = 0
        broker_missing = 0

        for item in instruments:
            if item.symbol in seen:
                duplicate_symbols.append(item.symbol)
            else:
                seen.add(item.symbol)
            if not item.symbol or not item.symbol.strip():
                invalid.append(
                    {
                        "company_name": item.company_name or "",
                        "current_stored_identifier": item.universe_symbol,
                        "attempted_canonical_symbol": item.symbol,
                        "reason": "empty_canonical_symbol",
                        "recommended_resolution": "Populate symbol from the NIFTY 500 CSV Symbol column.",
                    }
                )
                continue
            if " " in item.symbol:
                invalid.append(
                    {
                        "company_name": item.company_name or "",
                        "current_stored_identifier": item.universe_symbol,
                        "attempted_canonical_symbol": item.symbol,
                        "reason": "whitespace_in_symbol",
                        "recommended_resolution": "Replace company-name values with the CSV ticker.",
                    }
                )
                continue
            symbols_present += 1
            if not item.broker_symbol:
                broker_missing += 1

        for canon, csv_row in csv_by_canon.items():
            if canon not in seen:
                missing.append(
                    {
                        "company_name": csv_row.get("company_name") or "",
                        "current_stored_identifier": "",
                        "attempted_canonical_symbol": canon,
                        "reason": "present_in_csv_absent_from_stocks_master",
                        "recommended_resolution": "Re-run stocks_master import from ind_nifty500list.csv.",
                    }
                )

        inactive = 0
        try:
            async with AsyncSessionLocal() as db:
                inactive_rows = (
                    await db.scalars(
                        select(StockMaster).where(
                            StockMaster.is_active == False,
                            or_(
                                StockMaster.is_nifty500 == True,
                                StockMaster.universe == universe,
                            ),
                        )
                    )
                ).all()
                inactive = len(inactive_rows)
        except Exception as e:
            logger.warning("SYMBOL_MAPPING_FAILED | stage=inactive_count | error=%s", e)

        report = UniverseValidationReport(
            total_stocks=len(instruments),
            symbols_present=symbols_present,
            symbols_missing=len(missing),
            duplicates=len(duplicate_symbols),
            invalid_symbols=len(invalid),
            inactive_symbols=inactive,
            broker_mappings_missing=broker_missing,
            missing=missing,
            duplicate_symbols=duplicate_symbols,
            invalid=invalid,
        )
        logger.info(
            "UNIVERSE_SYMBOL_VALIDATION | total=%s | present=%s | missing=%s | duplicates=%s | invalid=%s | inactive=%s | broker_missing=%s",
            report.total_stocks,
            report.symbols_present,
            report.symbols_missing,
            report.duplicates,
            report.invalid_symbols,
            report.inactive_symbols,
            report.broker_mappings_missing,
        )
        return report
