import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from ..db.session import AsyncSessionLocal
from ..models.stock import StockMaster

logger = logging.getLogger("app.services.universe")


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
