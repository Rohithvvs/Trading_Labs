from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select


from ..models.paper_trading import ExecutionEvent, MarketEngineSession, PaperOrder, PaperPosition
from ..services.token_service import get_current_access_token
from ..services.fyers_service import FyersAuthExpiredError, FyersAuthInvalidError, FyersService
from ..services.market_data_feed import FyersMarketDataFeed
from ..db.session import AsyncSessionLocal, SessionLocal, is_db_connection_error, dispose_async_pool
from ..services.paper_trading_service import PaperTradingService
from ..utils import get_logger


IST = ZoneInfo("Asia/Kolkata")
ACTIVE_ORDER_STATES = {
    "PENDING_ENTRY",
    "WAITING_FOR_MARKET",
    "PENDING_MARKET_OPEN",
    "READY_TO_EXECUTE",
    "ERROR_RETRYING",
}
ACTIVE_POSITION_STATES = {"OPEN_POSITION"}
OPEN_ORDER_STATUSES = {
    "PENDING",
    "WAITING_FOR_MARKET",
    "PENDING_MARKET_OPEN",
    "READY_TO_EXECUTE",
    "FAILED",
    "OPEN",
    "PARTIALLY_EXECUTED",
}

# Consecutive transient DB failures before PRODUCTION_ALERT MARKET_ENGINE_DOWN.
# Neon/proxy cold-starts and pool pre_ping races produce short TimeoutError blips;
# a single failed connect must not page as "engine down".
_DB_TRANSIENT_ALERT_AFTER = 5
_DB_TRANSIENT_POOL_DISPOSE_EVERY = 3
_DB_TRANSIENT_MAX_BACKOFF_SEC = 30.0


def _is_transient_db_error(exc: BaseException) -> bool:
    """True when the market engine should retry rather than declare hard failure."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    if isinstance(exc, asyncio.CancelledError):
        # Connect-path timeouts surface CancelledError → TimeoutError; if a bare
        # CancelledError reaches the loop, treat as non-transient (shutdown).
        return False
    try:
        from sqlalchemy.exc import PendingRollbackError

        if isinstance(exc, PendingRollbackError):
            return True
    except Exception:
        pass
    try:
        if is_db_connection_error(exc):
            return True
    except Exception:
        pass
    msg = str(exc).lower()
    needles = (
        "timeout",
        "timed out",
        "connection is closed",
        "connection was closed",
        "server closed the connection",
        "ssl connection has been closed",
        "could not connect",
        "connection refused",
        "too many connections",
        "pool is closed",
        "cannot connect",
        # Session left invalid after a prior DBAPI failure; needs rollback + retry.
        "can't reconnect until invalid transaction",
        "pendingrollback",
        "invalid transaction is rolled back",
    )
    return any(n in msg for n in needles)


class MarketEngineService:
    def __init__(self) -> None:
        self.logger = get_logger("app.market_engine")
        self.fyers = FyersService()
        self.latest_ltp: dict[str, float] = {}
        self._active_positions_cache: dict[str, list[PaperPosition]] = {}
        self._task: asyncio.Task | None = None
        self._recon_task: asyncio.Task | None = None
        self._running = False
        self._feed = FyersMarketDataFeed(
            self._sync_on_tick, 
            self._sync_on_feed_error, 
            self._sync_on_connection_change
        )
        self._loop = None
        # Cap concurrent tick DB sessions so websocket floods never share one connection
        self._tick_sem = asyncio.Semaphore(8)
        self._consecutive_db_failures = 0

    def is_market_hours(self, now: datetime | None = None) -> bool:
        """Delegate to trading_hours_service (NSE calendar + session)."""
        from .trading_hours_service import trading_hours
        return trading_hours.is_market_open(now)

    def _sync_on_tick(self, symbol: str, price: float):
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(self._on_tick(symbol, price), self._loop)

    def _sync_on_feed_error(self, message: str | Exception):
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(self._on_feed_error(message), self._loop)

    def _sync_on_connection_change(self, connected: bool):
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(self._on_connection_change(connected), self._loop)

    async def start_loop(self) -> None:
        if self._task and not self._task.done():
            self.logger.info("Market engine loop already running; start is idempotent")
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run_loop(), name="market-engine-loop")
        self._recon_task = asyncio.create_task(self._reconciliation_loop(), name="market-reconciliation-loop")
        self.logger.info("MARKET_ENGINE_STARTED | Market engine loop started")

    async def shutdown(self) -> None:
        if not self._running and (self._task is None or self._task.done()):
            self.logger.info("Market engine loop already stopped; shutdown is idempotent")
            return
        self._running = False
        self._feed.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._recon_task:
            self._recon_task.cancel()
            try:
                await self._recon_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Market engine loop stopped")

    async def request_start(self) -> MarketEngineSession:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                session.status = "STARTING"
                session.requested_start_at = datetime.now(timezone.utc)
                session.paused_reason = None
                await db.refresh(session)
                self.logger.info("Market engine start requested | session_id=%s", session.id)
                return session

    async def request_stop(self) -> MarketEngineSession:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                session.status = "STOPPED"
                session.stopped_at = datetime.now(timezone.utc)
                session.websocket_connected = False
                await db.refresh(session)
                self.logger.info("MARKET_ENGINE_STOPPED | session_id=%s", session.id)
        self._feed.stop()
        return session

    async def heartbeat(self) -> None:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                session.last_heartbeat_at = datetime.now(timezone.utc)
                
                # Try to load symbols/positions for logging
                try:
                    positions_count = len((await db.scalars(select(PaperPosition.id).where(PaperPosition.status == "OPEN"))).all())
                    symbols_count = len(await self._desired_symbols(db))
                    actual_subscribed = len(self._feed._symbols) if self._feed else 0
                    connected = getattr(self._feed, 'connected', False)
                except Exception:
                    positions_count = 0
                    symbols_count = 0
                    actual_subscribed = 0
                    connected = False
                
                if symbols_count != actual_subscribed:
                    self.logger.warning("HEARTBEAT_DRIFT_DETECTED | desired_symbols=%s | actual_subscribed_symbols=%s", symbols_count, actual_subscribed)
                
                self.logger.info("MARKET_ENGINE_HEARTBEAT | session_id=%s | active_positions=%s | desired_symbols=%s | actual_subscribed_symbols=%s | connection_state=%s", session.id, positions_count, symbols_count, actual_subscribed, connected)

    async def status(self) -> dict:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                symbols = sorted(await self._desired_symbols(db))
                return {
                    "status": session.status,
                    "websocket_connected": bool(session.websocket_connected),
                    "token_status": session.token_status,
                    "paused_reason": session.paused_reason,
                    "last_heartbeat_at": session.last_heartbeat_at,
                    "last_tick_at": session.last_tick_at,
                    "active_monitored_symbols_count": len(symbols),
                    "active_symbols": symbols,
                    "trading_date": session.trading_date,
                }

    async def _run_loop(self) -> None:
        """Main loop: short-lived sessions only — never hold a txn during poll/IO.

        Holding ``async with db.begin()`` across network polls previously caused
        asyncpg ``another operation is in progress`` when ticks/upserts raced
        the same pool under scan load.

        Transient DB connect timeouts (Neon cold-start, pooler blips) are retried
        with backoff; MARKET_ENGINE_DOWN is only raised after sustained failures.
        """
        while self._running:
            try:
                should_reconcile = False
                # Bound session bootstrap so a hung checkout cannot stall the loop
                # for the full asyncpg connect timeout repeatedly without recovery.
                async with AsyncSessionLocal() as db:
                    session = await asyncio.wait_for(
                        self._get_or_create_session(db),
                        timeout=20.0,
                    )
                    if session.status in {
                        "STARTING",
                        "RUNNING",
                        "PAUSED_TOKEN_EXPIRED",
                        "ERROR_RETRYING",
                    }:
                        if session.status == "ERROR_RETRYING":
                            session.status = "RUNNING"
                            self.logger.info(
                                "MARKET_ENGINE_RECOVERED | Engine recovered from error state"
                            )
                        should_reconcile = True
                    await db.commit()

                if self._consecutive_db_failures:
                    self.logger.info(
                        "MARKET_ENGINE_DB_RECOVERED | previous_failures=%s",
                        self._consecutive_db_failures,
                    )
                self._consecutive_db_failures = 0

                if should_reconcile:
                    await self._reconcile_session_isolated()
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Never call db.rollback() here — session is already closed.
                if _is_transient_db_error(e):
                    self._consecutive_db_failures += 1
                    n = self._consecutive_db_failures
                    backoff = min(
                        _DB_TRANSIENT_MAX_BACKOFF_SEC,
                        float(2 ** min(n, 4)),
                    )
                    self.logger.warning(
                        "MARKET_ENGINE_DB_TRANSIENT | consecutive=%s | backoff_s=%.1f | "
                        "error_type=%s | error=%s",
                        n,
                        backoff,
                        type(e).__name__,
                        str(e)[:200] or type(e).__name__,
                    )
                    if n % _DB_TRANSIENT_POOL_DISPOSE_EVERY == 0:
                        try:
                            await dispose_async_pool(
                                reason=f"market_engine_transient_db_n={n}"
                            )
                        except Exception as dispose_exc:
                            self.logger.warning(
                                "MARKET_ENGINE_POOL_DISPOSE_FAILED | error=%s",
                                dispose_exc,
                            )
                    if n >= _DB_TRANSIENT_ALERT_AFTER:
                        self.logger.error(
                            "PRODUCTION_ALERT | category=MARKET_ENGINE_DOWN | "
                            "reason=sustained_db_failure | consecutive=%s | error=%s",
                            n,
                            str(e)[:200] or type(e).__name__,
                        )
                    await asyncio.sleep(backoff)
                    continue

                self.logger.exception(
                    "MARKET_ENGINE_EXCEPTION | Market engine loop failed | error=%s",
                    str(e),
                )
                self.logger.error(
                    "PRODUCTION_ALERT | category=MARKET_ENGINE_DOWN | error=%s",
                    str(e),
                )
                await asyncio.sleep(2)

    async def _reconcile_session_isolated(self) -> None:
        """Reconcile feed + missing prices without a long-held DB transaction."""
        desired: set[str] = set()
        token = None
        try:
            async with AsyncSessionLocal() as db:
                session = await self._get_or_create_session(db)
                desired = await self._desired_symbols(db)
                session.monitored_symbols_count = len(desired)
                if desired:
                    token = await get_current_access_token(db)
                session.status = "RUNNING"
                session.token_status = "VALID" if token else session.token_status
                session.paused_reason = None
                if session.started_at is None:
                    session.started_at = datetime.now(timezone.utc)
                    positions_count = len(
                        (
                            await db.scalars(
                                select(PaperPosition.id).where(
                                    PaperPosition.status == "OPEN"
                                )
                            )
                        ).all()
                    )
                    self.logger.info(
                        "MARKET_ENGINE_STARTED | session_id=%s | active_positions=%s | symbols=%s",
                        session.id,
                        positions_count,
                        len(desired),
                    )
                await db.commit()

            # Feed + LTP poll run *outside* any open transaction/session.
            self._feed.sync_symbols(desired)
            if desired:
                if token:
                    if self._feed.connected:
                        self._feed.start(str(token))
                    else:
                        self.logger.warning("Feed disconnected; force-restarting")
                        self._feed.restart(str(token))
                else:
                    self.logger.warning("No token available to start feed")
            await self._poll_missing_prices(desired)
        except (FyersAuthExpiredError, FyersAuthInvalidError):
            try:
                async with AsyncSessionLocal() as db:
                    session = await self._get_or_create_session(db)
                    await self._pause_for_token(db, session)
                    await db.commit()
            except Exception:
                self.logger.exception("Failed to pause market engine for token expiry")
        except Exception:
            self.logger.exception("Market engine reconcile failed")
            try:
                async with AsyncSessionLocal() as db:
                    session = await self._get_or_create_session(db)
                    session.status = "ERROR_RETRYING"
                    await db.commit()
            except Exception:
                self.logger.exception("Failed to mark market engine ERROR_RETRYING")

    async def _reconcile_session(self, db, session: MarketEngineSession) -> None:
        """Legacy helper kept for callers that already hold a short-lived session."""
        await self._reconcile_session_isolated()

    async def _poll_missing_prices(self, symbols: set[str]) -> None:
        import time
        missing = [sym for sym in symbols if sym not in self.latest_ltp]
        if not missing:
            return
            
        start_time = time.perf_counter()
        open_positions = 0
        try:
            async with AsyncSessionLocal() as db:
                open_positions = len((await db.scalars(select(PaperPosition.id).where(PaperPosition.status == "OPEN"))).all())
        except Exception:
            pass
            
        self.logger.info("RECONCILIATION_STARTED | open_positions=%s", open_positions)
            
        sem = asyncio.Semaphore(10)
        
        async def fetch_and_process(sym: str):
            async with sem:
                ltp = await self.fyers.fetch_ltp(sym)
                if ltp is not None:
                    await self._on_tick(sym, ltp, is_reconciliation=True)

        await asyncio.gather(*(fetch_and_process(sym) for sym in missing))
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        self.logger.info("RECONCILIATION_COMPLETED | duration_ms=%s | positions_checked=%s", duration_ms, open_positions)

    async def _on_tick(self, symbol: str, price: float, is_reconciliation: bool = False) -> None:
        from ..utils.symbol import canonical_symbol
        normalized = canonical_symbol(symbol)
        
        self.logger.debug(
            "TICK_RECEIVED | raw_symbol=%s | canonical_symbol=%s | price=%s",
            symbol,
            normalized,
            price,
        )
        
        self.latest_ltp[normalized] = price
        # Own session per tick; semaphore bounds concurrent checkouts.
        try:
            async with self._tick_sem:
                async with AsyncSessionLocal() as db:
                    await self._process_symbol(
                        db,
                        normalized,
                        price,
                        raw_symbol=symbol,
                        is_reconciliation=is_reconciliation,
                    )
                    session = await self._get_or_create_session(db)
                    session.last_tick_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            self.logger.exception(
                "Tick processing error for raw_symbol=%s canonical_symbol=%s",
                symbol,
                normalized,
            )

    async def _process_symbol(self, db, symbol: str, price: float, raw_symbol: str = "", is_reconciliation: bool = False) -> None:
        # Outside market hours: do not execute orders (PENDING_MARKET_OPEN stays pending).
        if not self.is_market_hours():
            return

        service = PaperTradingService(db)
        order_query = select(PaperOrder).where(
            PaperOrder.symbol.in_([symbol, f"{symbol}-EQ", f"NSE:{symbol}-EQ"]),
            PaperOrder.lifecycle_state.in_(ACTIVE_ORDER_STATES),
            PaperOrder.status.in_(tuple(OPEN_ORDER_STATUSES)),
            PaperOrder.monitor_enabled.is_(True),
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            order_query = order_query.with_for_update(skip_locked=True)
        orders = list((await db.scalars(order_query)).all())
        for order in orders:
            prior = order.lifecycle_state
            order.last_seen_ltp = price
            order.last_evaluated_at = datetime.now(timezone.utc)
            def _fill_order_sync(session, order_id, ltp):
                # Multi-user safe: fill against the order's own account_id only
                svc = PaperTradingService(session)  # system path — no user_id
                ord_obj = session.get(PaperOrder, order_id)
                if not ord_obj:
                    return "MISSING", None, None
                acc = svc.get_account_by_id(int(ord_obj.account_id), for_update=True)
                fo, pos, _, _ = svc._try_fill_order(acc, ord_obj, ltp, require_market_open=True)
                if fo.status == "FILLED":
                    fo.lifecycle_state = "ENTRY_FILLED"
                    if pos:
                        pos.lifecycle_state = "OPEN_POSITION"
                return fo.status, getattr(pos, "id", None), int(ord_obj.account_id)

            fo_status, pos_id, fill_account_id = await db.run_sync(_fill_order_sync, order.id, price)
            if fo_status == "FILLED":
                self.logger.info("PAPER_POSITION_OPENED | order_id=%s symbol=%s price=%s position_id=%s account_id=%s", order.id, symbol, price, pos_id, fill_account_id)
                await self._record_event(
                    db,
                    "ENTRY_FILLED",
                    symbol,
                    order.id,
                    pos_id,
                    prior,
                    "ENTRY_FILLED",
                    price,
                    dedupe_key=f"entry-filled:{order.id}",
                )
                def _add_notif(acc_id, oid):
                    with SessionLocal() as s:
                        PaperTradingService(s).add_notification(
                            acc_id,
                            f"Your BUY order for {symbol} has been executed successfully. Position has been added to your portfolio.",
                            "success",
                            "ORDER_EXECUTED",
                            "order",
                            oid,
                            dedupe_key=f"entry-filled:{oid}",
                            commit=True,
                        )
                # Notify the owning account only (never a shared/default account)
                notif_account_id = fill_account_id if fill_account_id is not None else int(order.account_id)
                await asyncio.to_thread(_add_notif, notif_account_id, order.id)

        position_query = select(PaperPosition).where(
            PaperPosition.symbol.in_([symbol, f"{symbol}-EQ", f"NSE:{symbol}-EQ"]),
            PaperPosition.status == "OPEN",
            PaperPosition.lifecycle_state.in_(ACTIVE_POSITION_STATES),
            PaperPosition.monitor_enabled.is_(True),
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            position_query = position_query.with_for_update(skip_locked=True)
        
        positions = list((await db.scalars(position_query)).all())
        
        if not positions:
            self.logger.debug("POSITION_MATCH_MISS | incoming_symbol=%s", symbol)
        else:
            for position in positions:
                position.last_evaluated_at = datetime.now(timezone.utc)
                self.logger.info("POSITION_MATCH_FOUND | position_id=%s | symbol=%s", position.id, position.symbol)
                
                if is_reconciliation:
                    self.logger.info("RECONCILIATION_POSITION_CHECK | position_id=%s | symbol=%s | target=%s | stop_loss=%s | ltp=%s", position.id, position.symbol, position.target, position.stop_loss, price)
                else:
                    self.logger.debug("POSITION_CHECK | position_id=%s | symbol=%s | target=%s | stop_loss=%s | price=%s", position.id, position.symbol, position.target, position.stop_loss, price)

                if position.target is not None and price >= position.target:
                    if is_reconciliation:
                        self.logger.info("RECONCILIATION_TARGET_HIT | position_id=%s | symbol=%s | price=%s | target=%s", position.id, position.symbol, price, position.target)
                    else:
                        self.logger.info("TARGET_HIT | position_id=%s | symbol=%s | price=%s | target=%s", position.id, position.symbol, price, position.target)
                        
                    self.logger.info("EXIT_ORDER_TRIGGERED | position_id=%s | symbol=%s | reason=%s", position.id, position.symbol, "TARGET_HIT")
                    try:
                        # Isolated sync session — never auto_exit on the shared async txn
                        # (SSL/drop mid-exit would poison the tick session).
                        await asyncio.to_thread(
                            self._auto_exit_isolated,
                            int(position.id),
                            float(price),
                            "TARGET_HIT",
                            "LIVE",
                        )
                        self.logger.info("EXIT_ORDER_SUCCESS | position_id=%s | symbol=%s", position.id, position.symbol)
                        await self._record_event(
                            db,
                            "EXIT_FILLED",
                            symbol,
                            None,
                            position.id,
                            "OPEN_POSITION",
                            "EXIT_FILLED",
                            price,
                            dedupe_key=f"exit-filled:{position.id}:TARGET_HIT",
                        )
                    except Exception as exc:
                        self.logger.exception(
                            "EXIT_ORDER_FAILED | position_id=%s | symbol=%s | error=%s",
                            position.id,
                            position.symbol,
                            str(exc),
                        )
                        await self._safe_db_rollback(db)
                
                elif position.stop_loss is not None and price <= position.stop_loss:
                    if is_reconciliation:
                        self.logger.info("RECONCILIATION_STOPLOSS_HIT | position_id=%s | symbol=%s | price=%s | stop_loss=%s", position.id, position.symbol, price, position.stop_loss)
                    else:
                        self.logger.info("STOPLOSS_HIT | position_id=%s | symbol=%s | price=%s | stop_loss=%s", position.id, position.symbol, price, position.stop_loss)
                        
                    self.logger.info("EXIT_ORDER_TRIGGERED | position_id=%s | symbol=%s | reason=%s", position.id, position.symbol, "STOPLOSS_HIT")
                    try:
                        await asyncio.to_thread(
                            self._auto_exit_isolated,
                            int(position.id),
                            float(price),
                            "STOPLOSS_HIT",
                            "LIVE",
                        )
                        self.logger.info("EXIT_ORDER_SUCCESS | position_id=%s | symbol=%s", position.id, position.symbol)
                        await self._record_event(
                            db,
                            "EXIT_FILLED",
                            symbol,
                            None,
                            position.id,
                            "OPEN_POSITION",
                            "EXIT_FILLED",
                            price,
                            dedupe_key=f"exit-filled:{position.id}:STOPLOSS_HIT",
                        )
                    except Exception as exc:
                        self.logger.exception(
                            "EXIT_ORDER_FAILED | position_id=%s | symbol=%s | error=%s",
                            position.id,
                            position.symbol,
                            str(exc),
                        )
                        await self._safe_db_rollback(db)

    async def _desired_symbols(self, db) -> set[str]:
        order_symbols = set(
            (await db.scalars(
                select(PaperOrder.symbol).where(
                    PaperOrder.status.in_(tuple(OPEN_ORDER_STATUSES)),
                    PaperOrder.lifecycle_state.in_(ACTIVE_ORDER_STATES),
                    PaperOrder.monitor_enabled.is_(True),
                )
            )).all()
        )
        positions = list(
            (await db.scalars(
                select(PaperPosition).where(
                    PaperPosition.status == "OPEN",
                    PaperPosition.lifecycle_state.in_(ACTIVE_POSITION_STATES),
                    PaperPosition.monitor_enabled.is_(True),
                )
            )).all()
        )
        
        self._active_positions_cache.clear()
        for pos in positions:
            self._active_positions_cache.setdefault(pos.symbol, []).append(pos)
            
        position_symbols = {pos.symbol for pos in positions if pos.symbol}
        return {s for s in order_symbols | position_symbols if s}

    async def _pause_for_token(self, db, session: MarketEngineSession) -> None:
        already_paused = session.status == "PAUSED_TOKEN_EXPIRED"
        session.status = "PAUSED_TOKEN_EXPIRED"
        session.token_status = "EXPIRED"
        session.paused_reason = "TOKEN_EXPIRED"
        session.websocket_connected = False
        affected_account_ids: set[int] = set()
        for order in (await db.scalars(select(PaperOrder).where(PaperOrder.status.in_(tuple(OPEN_ORDER_STATUSES))))).all():
            order.lifecycle_state = "TOKEN_EXPIRED_PAUSED"
            order.paused_reason = "TOKEN_EXPIRED"
            affected_account_ids.add(int(order.account_id))
        for position in (await db.scalars(select(PaperPosition).where(PaperPosition.status == "OPEN"))).all():
            position.lifecycle_state = "TOKEN_EXPIRED_PAUSED"
            position.paused_reason = "TOKEN_EXPIRED"
            affected_account_ids.add(int(position.account_id))
        if not already_paused:
            self.logger.warning("Token expired; monitoring paused | session_id=%s", session.id)
        def _add_notifs(acc_ids, sid):
            with SessionLocal() as s:
                svc = PaperTradingService(s)
                for acc_id in acc_ids:
                    svc.add_notification(
                        acc_id,
                        "FYERS token expired; monitoring paused.",
                        "error",
                        "TOKEN_EXPIRED",
                        "engine",
                        sid,
                        dedupe_key=f"token-expired:{sid}:acc:{acc_id}",
                        commit=True,
                    )
        if affected_account_ids:
            await asyncio.to_thread(_add_notifs, list(affected_account_ids), session.id)
        self._feed.stop(notify=False)

    async def _on_feed_error(self, message: str | Exception) -> None:
        if "expired" in str(message).lower():
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    session = await self._get_or_create_session(db)
                    await self._pause_for_token(db, session)
            return
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                session.status = "ERROR_RETRYING"
                session.websocket_connected = False
                # Multi-user: notify every account with open activity (no shared account)
                order_accs = set(
                    (await db.scalars(select(PaperOrder.account_id).where(PaperOrder.status.in_(tuple(OPEN_ORDER_STATUSES))))).all()
                )
                pos_accs = set(
                    (await db.scalars(select(PaperPosition.account_id).where(PaperPosition.status == "OPEN"))).all()
                )
                affected = {int(a) for a in (order_accs | pos_accs) if a is not None}
                def _add_err_notif(acc_ids, sid):
                    with SessionLocal() as s:
                        svc = PaperTradingService(s)
                        for acc_id in acc_ids:
                            svc.add_notification(
                                acc_id,
                                "Live market feed disconnected; monitoring degraded while retrying.",
                                "error",
                                "WEBSOCKET_DISCONNECTED",
                                "engine",
                                sid,
                                dedupe_key=f"feed-disconnected:{sid}:acc:{acc_id}",
                                commit=True,
                            )
                if affected:
                    await asyncio.to_thread(_add_err_notif, list(affected), session.id)
                self.logger.error("FYERS_WS_ERROR | Websocket connection failed | disconnect_reason=%s | downtime_seconds=0", str(message))
                self.logger.error("PRODUCTION_ALERT | category=WEBSOCKET_DOWN | reason=%s", str(message))

    async def _on_connection_change(self, connected: bool) -> None:
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    session = await self._get_or_create_session(db)
                    if connected:
                        self.logger.info("FYERS_WS_CONNECTED | Websocket connection state changed | connected=True")
                    else:
                        self.logger.warning("FYERS_WS_DISCONNECTED | Websocket connection state changed | connected=False | disconnect_reason=connection_lost | downtime_seconds=0")
                        self.logger.error("PRODUCTION_ALERT | category=WEBSOCKET_DOWN | reason=connection_lost")
                    session.websocket_connected = connected
        except Exception:
            self.logger.exception("Failed to persist websocket state change | connected=%s", connected)

    async def _safe_db_rollback(self, db) -> None:
        """Clear an invalid/failed transaction so the session can be reused or closed cleanly."""
        try:
            await db.rollback()
        except Exception as rb_exc:
            self.logger.warning(
                "DB_ROLLBACK_FAILED | error_type=%s | error=%s",
                type(rb_exc).__name__,
                str(rb_exc)[:200],
            )

    @staticmethod
    def _auto_exit_isolated(
        position_id: int,
        fill_price: float,
        reason: str,
        source: str,
        *,
        max_attempts: int = 3,
    ):
        """Run auto_exit on a fresh sync session (no shared/poisoned transaction).

        Retries transient DB disconnects (Neon/proxy SSL drops) with a new session
        each attempt. Business errors (ValueError) are not retried.
        """
        import time

        last_exc: BaseException | None = None
        for attempt in range(1, max(1, int(max_attempts)) + 1):
            try:
                with SessionLocal() as session:
                    return PaperTradingService(session).auto_exit(
                        int(position_id),
                        float(fill_price),
                        reason,
                        source,
                    )
            except ValueError:
                raise
            except Exception as exc:
                last_exc = exc
                if not _is_transient_db_error(exc) or attempt >= max_attempts:
                    raise
                # Brief backoff; next attempt uses a new pool connection (pre_ping).
                time.sleep(min(0.15 * attempt, 0.5))
        assert last_exc is not None
        raise last_exc

    async def _record_event(
        self,
        db,
        event_type: str,
        symbol: str | None,
        order_id: int | None,
        position_id: int | None,
        from_state: str | None,
        to_state: str | None,
        price: float | None,
        dedupe_key: str | None = None,
    ) -> None:
        if dedupe_key:
            for pending in db.new:
                if isinstance(pending, ExecutionEvent) and pending.dedupe_key == dedupe_key:
                    return
            existing = await db.scalar(select(ExecutionEvent).where(ExecutionEvent.dedupe_key == dedupe_key))
            if existing:
                return
        db.add(
            ExecutionEvent(
                event_type=event_type,
                symbol=symbol,
                order_id=order_id,
                position_id=position_id,
                from_state=from_state,
                to_state=to_state,
                price=price,
                dedupe_key=dedupe_key,
            )
        )

    async def _get_or_create_session(self, db) -> MarketEngineSession:
        today = datetime.now(IST).date().isoformat()
        session = await db.scalar(select(MarketEngineSession).where(MarketEngineSession.trading_date == today))
        if session:
            return session
        session = MarketEngineSession(trading_date=today, status="STOPPED")
        db.add(session)
        await db.flush()
        return session

    async def _reconciliation_loop(self) -> None:
        """
        Independent background task to reconcile OHLC paths.
        Runs every 5 minutes (300 seconds).
        """
        while self._running:
            try:
                await asyncio.sleep(300)
                await self._sweep_historical_positions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.exception("RECONCILIATION_SWEEP_ERROR | error=%s", str(e))

    async def _sweep_historical_positions(self) -> None:
        from datetime import timedelta
        try:
            # Phase 1: load IDs only, then close session before parallel work.
            five_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
            target_ids: list[int] = []
            active_count = 0
            async with AsyncSessionLocal() as db:
                stmt = select(PaperPosition).where(
                    PaperPosition.status == "OPEN",
                    PaperPosition.lifecycle_state.in_(ACTIVE_POSITION_STATES),
                    PaperPosition.monitor_enabled.is_(True),
                )
                positions = list((await db.scalars(stmt)).all())
                active_count = len(positions)
                target_ids = [
                    int(p.id)
                    for p in positions
                    if p.last_reconciled_at is None
                    or p.last_reconciled_at.replace(tzinfo=None)
                    < five_mins_ago.replace(tzinfo=None)
                ]

            if not target_ids:
                return

            self.logger.info(
                "RECONCILIATION_SWEEP_STARTED | active_positions=%s | target_symbols=%s",
                active_count,
                len(target_ids),
            )

            # Each reconcile opens its own session — never share the load session.
            sem = asyncio.Semaphore(3)

            async def reconcile_pos(position_id: int):
                async with sem:
                    await self._reconcile_ohlcv_sequence(position_id)

            await asyncio.gather(*(reconcile_pos(pid) for pid in target_ids))
            self.logger.info(
                "RECONCILIATION_SWEEP_COMPLETED | target_symbols=%s", len(target_ids)
            )

        except Exception as e:
            self.logger.exception("RECONCILIATION_SWEEP_FAILED | error=%s", str(e))

    async def _reconcile_ohlcv_sequence(self, position_id: int) -> None:
        from ..schemas import AnalysisMode
        from datetime import timedelta
        
        def _normalize_utc(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        try:
            async with AsyncSessionLocal() as db:
                # Use FOR UPDATE SKIP LOCKED
                stmt = select(PaperPosition).where(
                    PaperPosition.id == position_id,
                    PaperPosition.status == "OPEN"
                )
                if db.bind and db.bind.dialect.name == "postgresql":
                    stmt = stmt.with_for_update(skip_locked=True)
                
                position = await db.scalar(stmt)
                if not position:
                    # Locked by live tick, or already closed. Skip cleanly.
                    return

                # Calculate replay start time
                # Uses max(last_reconciled_at, last_evaluated_at, created_at)
                times = [t for t in [position.last_reconciled_at, position.last_evaluated_at, position.created_at] if t is not None]
                if not times:
                    return
                replay_start = max(times)
                replay_start_utc = _normalize_utc(replay_start)
                
                gap_duration = _normalize_utc(datetime.now(timezone.utc)) - replay_start_utc
                if gap_duration < timedelta(minutes=1):
                    self.logger.info("RECONCILIATION_SKIPPED_NO_GAP | symbol=%s | gap_seconds=%s", position.symbol, gap_duration.total_seconds())
                    position.last_reconciled_at = datetime.now(timezone.utc)
                    await db.commit()
                    return

                # Calculate lookback window in days (approximate 1 min candles)
                lookback_days = max(1, gap_duration.days + 1)
                
                symbol = position.symbol
                
            # Fetch candles outside DB lock
            candles = await self.fyers.fetch_ohlcv(symbol, AnalysisMode.intraday, "1", lookback_days)
            
            if not candles:
                return
                
            # Filter candles: A 1-minute candle's closure must be strictly after our replay_start
            valid_candles = [c for c in candles if _normalize_utc(c.timestamp) + timedelta(minutes=1) > replay_start_utc]
            
            if not valid_candles:
                # Do NOT update last_reconciled_at to utcnow().
                # If FYERS is lagging or the market is closed, we must retain the old
                # watermark and wait for new candles to arrive.
                return

            self.logger.info("RECONCILIATION_OHLC_FETCHED | symbol=%s | start_time=%s | end_time=%s | candles_count=%s", 
                symbol, valid_candles[0].timestamp, valid_candles[-1].timestamp, len(valid_candles))

            # Snapshot levels for breach detection, then release the read session
            # BEFORE exit. Never call auto_exit via db.run_sync on a shared async
            # session — a single DBAPI failure poisons that txn and every later
            # candle raises PendingRollbackError (production spam for OPEN positions).
            target_level: float | None = None
            stop_level: float | None = None
            pid = int(position_id)
            async with AsyncSessionLocal() as db:
                stmt = select(PaperPosition).where(
                    PaperPosition.id == position_id,
                    PaperPosition.status == "OPEN",
                )
                # No FOR UPDATE here: holding a lock while later calling auto_exit on
                # another connection can block/timeout; auto_exit locks its own row.
                position = await db.scalar(stmt)
                if not position:
                    return
                pid = int(position.id)
                target_level = (
                    float(position.target) if position.target is not None else None
                )
                stop_level = (
                    float(position.stop_loss)
                    if position.stop_loss is not None
                    else None
                )

            exited = False
            for candle in valid_candles:
                target_breached = (
                    target_level is not None and candle.high >= target_level
                )
                stop_breached = stop_level is not None and candle.low <= stop_level

                if not (target_breached or stop_breached):
                    continue

                conflict_resolved_as = (
                    "STOPLOSS_HIT" if stop_breached else "TARGET_HIT"
                )
                self.logger.info(
                    "RECONCILIATION_GAP_DETECTED | symbol=%s | target_breached=%s | "
                    "stop_breached=%s | conflict_resolved_as=%s",
                    symbol,
                    target_breached,
                    stop_breached,
                    conflict_resolved_as,
                )
                exit_price = candle.low if stop_breached else candle.high

                try:
                    await asyncio.to_thread(
                        self._auto_exit_isolated,
                        pid,
                        float(exit_price),
                        conflict_resolved_as,
                        "RECONCILIATION",
                    )
                except ValueError as exc:
                    # Already closed / not found — treat as done for this cycle.
                    self.logger.info(
                        "RECONCILIATION_EXIT_SKIPPED | position_id=%s | reason=%s",
                        pid,
                        str(exc),
                    )
                    exited = True
                    break
                except Exception as exc:
                    self.logger.exception(
                        "RECONCILIATION_EXIT_FAILED | position_id=%s | error=%s",
                        pid,
                        str(exc),
                    )
                    # One breach attempt only; next sweep retries. Do not walk
                    # remaining candles with the same broken exit path.
                    break

                self.logger.info(
                    "RECONCILIATION_EXIT_TRIGGERED | position_id=%s | reason=%s | "
                    "retroactive_time=%s | exit_price=%s",
                    pid,
                    conflict_resolved_as,
                    candle.timestamp,
                    exit_price,
                )
                # ExecutionEvent is already written inside auto_exit (same dedupe key).
                exited = True
                break

            # Watermark only when we did not exit: separate short session so a
            # prior failure cannot leave this update in PendingRollbackError.
            # Reason: Guarantees crash safety. If the server crashes mid-replay,
            # no progress is committed; on restart OHLC is fetched again.
            # auto_exit is idempotent (requires OPEN status), so replay is safe.
            if not exited:
                last_candle_close = (
                    _normalize_utc(valid_candles[-1].timestamp) + timedelta(minutes=1)
                )
                try:
                    async with AsyncSessionLocal() as db:
                        stmt = select(PaperPosition).where(
                            PaperPosition.id == pid,
                            PaperPosition.status == "OPEN",
                        )
                        position = await db.scalar(stmt)
                        if position:
                            # Anchor watermark to last evaluated candle close only.
                            # utcnow() would create a blind spot if FYERS is lagging.
                            position.last_reconciled_at = last_candle_close
                            await db.commit()
                except Exception as wm_exc:
                    self.logger.warning(
                        "RECONCILIATION_WATERMARK_FAILED | position_id=%s | error=%s",
                        pid,
                        str(wm_exc),
                    )

        except Exception as e:
            self.logger.warning("RECONCILIATION_FAILED | position_id=%s | error=%s", position_id, str(e))


market_engine = MarketEngineService()
