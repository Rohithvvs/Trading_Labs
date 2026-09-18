"""
Gap Replay Engine
-----------------
On startup, fetches 1-minute candles for the offline gap period and
replays them to fill missed limit orders and trigger missed exits.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from math import ceil
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db.session import is_db_connection_error
from .server_state import read_last_shutdown, write_startup_time
from ..models.paper_trading import (
    ExecutionEvent,
    PaperOrder,
    PaperPosition,
    ReplaySession,
    PaperTradingAccount,
    PaperTradeHistory,
    PaperTransaction,
)
from ..services.fyers_service import FyersService
from ..schemas import AnalysisMode
from .log_manager import trading_logger as logger

SKIP_FIRST_RUN = "First run — no previous shutdown recorded."
SKIP_GAP_TOO_SMALL = "Gap too small (< 2 minutes), skipping."
SKIP_ALREADY_COMPLETED = "Replay window already completed."
SKIP_NOTHING_TO_REPLAY = "No open positions or pending orders to replay."
SKIP_TOKEN_NOT_READY = "fyers_token_not_ready"
SKIP_NO_CANDLE_DATA = "candle_data_unavailable"
SKIP_DB_CONNECTION_CLOSED = "db_connection_closed"

# NSE cash session is ~375 one-minute bars. Extra day of lookback is already
# included in lookback_days; 400 bars/day covers a full session plus margin.
_BARS_PER_SESSION = 400
_TOKEN_WAIT_TIMEOUT_SEC = 300.0
_TOKEN_WAIT_POLL_SEC = 2.0
_CANDLE_RETRIES = 3
_CANDLE_RETRY_DELAY_SEC = 10.0


def _fyers_ready(fyers_service: Any) -> bool:
    """True when FYERS can serve live history, or the caller is a test fake."""
    checker = getattr(fyers_service, "_is_fyers_configured", None)
    if not callable(checker):
        return True
    try:
        return bool(checker())
    except Exception:
        logger.exception("[GAP_REPLAY] FYERS configuration check failed")
        return False


def _intraday_points_for_gap(lookback_days: int) -> int:
    return max(_BARS_PER_SESSION, int(lookback_days) * _BARS_PER_SESSION)


def _task_is_cancelling() -> bool:
    task = asyncio.current_task()
    if task is None:
        return False
    cancelling = getattr(task, "cancelling", None)
    if callable(cancelling):
        return bool(cancelling())
    return bool(task.cancelled())


async def _safe_rollback(db: AsyncSession) -> None:
    """Clear a failed transaction so the same session can continue."""
    try:
        await db.rollback()
    except Exception as exc:
        if is_db_connection_error(exc):
            logger.warning("[GAP_REPLAY] Session rollback skipped; connection already closed")
            return
        logger.exception("[GAP_REPLAY] Session rollback failed")


async def run_gap_replay(db: AsyncSession, fyers_service: FyersService) -> Dict:
    summary: Dict = {
        "gap_start": None,
        "gap_end": None,
        "orders_filled": [],
        "positions_exited": [],
        "warnings": [],
        "skipped_reason": None,
    }

    last_shutdown = read_last_shutdown()
    now = datetime.now(timezone.utc)

    if last_shutdown is None:
        summary["skipped_reason"] = SKIP_FIRST_RUN
        logger.info("[GAP_REPLAY] First run, skipping replay.")
        write_startup_time()
        return summary

    gap_minutes = (now - last_shutdown).total_seconds() / 60.0
    if gap_minutes < 2:
        summary["skipped_reason"] = SKIP_GAP_TOO_SMALL
        write_startup_time()
        return summary

    gap_start = last_shutdown
    gap_end = now
    replay_key = f"{gap_start.isoformat()}:{gap_end.isoformat()}"
    summary["gap_start"] = gap_start.isoformat()
    summary["gap_end"] = gap_end.isoformat()

    logger.info("[GAP_REPLAY] Gap detected: %s → %s (%s minutes)", gap_start.isoformat(), gap_end.isoformat(), int(gap_minutes))

    try:
        accounts = list((await db.scalars(select(PaperTradingAccount))).all())
    except Exception as e:
        logger.error("[GAP_REPLAY] Failed to load accounts: %s", e)
        summary["warnings"].append(f"Failed to load accounts: {e}")
        return summary

    all_symbols: set[str] = set()
    for account in accounts:
        try:
            acc_id = int(account.id)
            open_positions = list(
                (
                    await db.scalars(
                        select(PaperPosition).where(
                            PaperPosition.account_id == acc_id,
                            PaperPosition.status == "OPEN",
                        )
                    )
                ).all()
            )
            pending_orders = list(
                (
                    await db.scalars(
                        select(PaperOrder).where(
                            PaperOrder.account_id == acc_id,
                            PaperOrder.status.in_(
                                (
                                    "PENDING",
                                    "WAITING_FOR_MARKET",
                                    "PENDING_MARKET_OPEN",
                                    "READY_TO_EXECUTE",
                                    "FAILED",
                                    "OPEN",
                                    "PARTIALLY_EXECUTED",
                                )
                            ),
                        )
                    )
                ).all()
            )
            all_symbols.update(
                {p.symbol for p in open_positions} | {o.symbol for o in pending_orders}
            )
        except Exception as e:
            await _safe_rollback(db)
            summary["warnings"].append(f"Failed to collect symbols for account: {e}")
            logger.error("[GAP_REPLAY] Symbol collection failed: %s", e)

    if not all_symbols:
        summary["skipped_reason"] = SKIP_NOTHING_TO_REPLAY
        logger.info("[GAP_REPLAY] %s", SKIP_NOTHING_TO_REPLAY)
        write_startup_time()
        return summary

    if not _fyers_ready(fyers_service):
        summary["skipped_reason"] = SKIP_TOKEN_NOT_READY
        warning = (
            f"FYERS token not ready — deferring replay for {len(all_symbols)} symbols"
        )
        summary["warnings"].append(warning)
        logger.warning("[GAP_REPLAY] %s", warning)
        return summary

    existing_replay = (
        await db.scalars(select(ReplaySession).where(ReplaySession.replay_key == replay_key))
    ).first()
    if existing_replay and existing_replay.status == "COMPLETED":
        summary["skipped_reason"] = SKIP_ALREADY_COMPLETED
        write_startup_time()
        return summary
    if existing_replay is None:
        existing_replay = ReplaySession(
            replay_key=replay_key, gap_start=gap_start, gap_end=gap_end, status="RUNNING"
        )
        db.add(existing_replay)
        try:
            await db.flush()
        except Exception as e:
            await db.rollback()
            summary["warnings"].append(f"Failed to create replay session: {e}")
            return summary

    # Pre-fetch all candles — enough 1m bars to cover the whole offline window.
    # fetch_ohlcv defaults to 40 intraday points (chart size), which would drop
    # most of a multi-hour gap.
    lookback_days = max(1, ceil(gap_minutes / (60 * 24)) + 1)
    max_points = _intraday_points_for_gap(lookback_days)
    pre_fetched_candles = {}
    for symbol in all_symbols:
        try:
            pre_fetched_candles[symbol] = await fyers_service.fetch_ohlcv(
                symbol,
                AnalysisMode.intraday,
                "1m",
                lookback_days,
                allow_mock=False,
                max_points=max_points,
            )
        except TypeError:
            # Test fakes may not accept max_points.
            try:
                pre_fetched_candles[symbol] = await fyers_service.fetch_ohlcv(
                    symbol, AnalysisMode.intraday, "1m", lookback_days, allow_mock=False
                )
            except Exception as e:
                logger.error("[GAP_REPLAY] Failed to fetch candles for %s: %s", symbol, e)
        except Exception as e:
            logger.error("[GAP_REPLAY] Failed to fetch candles for %s: %s", symbol, e)

    fetched_any = any(pre_fetched_candles.get(symbol) for symbol in all_symbols)
    if not fetched_any:
        warning = "No candle data for any symbol in the gap period — not marking COMPLETED"
        summary["skipped_reason"] = SKIP_NO_CANDLE_DATA
        summary["warnings"].append(warning)
        logger.error("[GAP_REPLAY] %s", warning)
        try:
            existing_replay.status = "FAILED"
            existing_replay.error_message = warning[:2000]
            await db.commit()
        except Exception:
            await _safe_rollback(db)
        return summary

    for account in accounts:
        try:
            account_id = int(account.id)
        except Exception as e:
            await _safe_rollback(db)
            summary["warnings"].append(f"Account load failed after prior error: {e}")
            logger.error("[GAP_REPLAY] Cannot access account after session failure: %s", e)
            continue

        try:
            open_positions = list(
                (
                    await db.scalars(
                        select(PaperPosition).where(
                            PaperPosition.account_id == account_id,
                            PaperPosition.status == "OPEN",
                        )
                    )
                ).all()
            )
            pending_orders = list(
                (
                    await db.scalars(
                        select(PaperOrder).where(
                            PaperOrder.account_id == account_id,
                            PaperOrder.status.in_(
                                (
                                    "PENDING",
                                    "WAITING_FOR_MARKET",
                                    "PENDING_MARKET_OPEN",
                                    "READY_TO_EXECUTE",
                                    "FAILED",
                                    "OPEN",
                                    "PARTIALLY_EXECUTED",
                                )
                            ),
                        )
                    )
                ).all()
            )
        except Exception as e:
            await _safe_rollback(db)
            summary["warnings"].append(f"Account {account_id}: failed to load positions/orders — {e}")
            logger.error("[GAP_REPLAY] Account %s load failed: %s", account_id, e)
            continue

        if not open_positions and not pending_orders:
            continue

        symbols = {p.symbol for p in open_positions} | {o.symbol for o in pending_orders}

        logger.info(
            "[GAP_REPLAY] Account %s: positions=%s pending_orders=%s symbols=%s",
            account_id,
            len(open_positions),
            len(pending_orders),
            list(symbols),
        )

        for symbol in symbols:
            try:
                candles = pre_fetched_candles.get(symbol)

                if not candles:
                    warning = f"{symbol}: No candle data for gap period — verify manually"
                    summary["warnings"].append(warning)
                    logger.warning("[GAP_REPLAY] %s", warning)
                    continue

                # Filter candles to gap period
                market_candles = [
                    c for c in candles if c.timestamp >= gap_start and c.timestamp <= gap_end
                ]
                market_candles.sort(key=lambda c: c.timestamp)

                if not market_candles:
                    logger.info("[GAP_REPLAY] %s: No candles inside gap", symbol)
                    continue

                # Replay pending LIMIT BUY orders — engine-scoped positions
                for order in [o for o in pending_orders if o.symbol == symbol and o.side == "BUY"]:
                    fill_dedupe = f"replay-fill:{replay_key}:{order.id}"
                    if (
                        await db.scalars(
                            select(ExecutionEvent).where(ExecutionEvent.dedupe_key == fill_dedupe)
                        )
                    ).first():
                        continue
                    for candle in market_candles:
                        candle_low = float(candle.low)
                        candle_time = candle.timestamp
                        if order.order_price is None:
                            continue
                        if candle_low <= float(order.order_price):
                            fill_price = float(order.order_price)
                            cost = fill_price * int(order.qty)
                            if account.cash_balance >= cost:
                                order.status = "FILLED"
                                order.lifecycle_state = "ENTRY_FILLED"
                                order.filled_price = fill_price
                                order.filled_at = candle_time

                                # Unique open key: (account, symbol)
                                existing_pos = (
                                    await db.scalars(
                                        select(PaperPosition).where(
                                            PaperPosition.account_id == account_id,
                                            PaperPosition.symbol == symbol,
                                            PaperPosition.status == "OPEN",
                                        )
                                    )
                                ).first()
                                if existing_pos:
                                    total_cost = (
                                        float(existing_pos.avg_entry_price) * float(existing_pos.qty)
                                    ) + cost
                                    existing_pos.qty = existing_pos.qty + order.qty
                                    existing_pos.avg_entry_price = total_cost / float(
                                        existing_pos.qty
                                    )
                                    existing_pos.stop_loss = order.stop_loss
                                    existing_pos.target = order.target
                                    existing_pos.updated_at = candle_time
                                    position_id = existing_pos.id
                                else:
                                    new_pos = PaperPosition(
                                        account_id=account_id,
                                        status="OPEN",
                                        lifecycle_state="OPEN_POSITION",
                                        symbol=symbol,
                                        qty=order.qty,
                                        avg_entry_price=fill_price,
                                        current_price=fill_price,
                                        stop_loss=order.stop_loss,
                                        target=order.target,
                                        notes=order.notes,
                                        source_signal=getattr(order, "source_signal", None),
                                        source_score=getattr(order, "source_score", None),
                                        source_confidence=getattr(order, "source_confidence", None),
                                    )
                                    try:
                                        new_pos.created_at = candle_time
                                        new_pos.updated_at = candle_time
                                    except Exception:
                                        pass
                                    db.add(new_pos)
                                    await db.flush()
                                    position_id = new_pos.id

                                account.cash_balance = float(account.cash_balance) - float(cost)

                                try:
                                    tx = PaperTransaction(
                                        account_id=account_id,
                                        timestamp=candle_time,
                                        symbol=symbol,
                                        action="BUY",
                                        qty=int(order.qty),
                                        price=float(fill_price),
                                        amount=-float(fill_price) * int(order.qty),
                                        balance_after=float(account.cash_balance),
                                    )
                                    db.add(tx)
                                except Exception:
                                    logger.exception(
                                        "[GAP_REPLAY] Failed to add BUY transaction for %s", symbol
                                    )

                                db.add(
                                    ExecutionEvent(
                                        event_type="REPLAY_ENTRY_FILLED",
                                        symbol=symbol,
                                        order_id=order.id,
                                        position_id=position_id,
                                        from_state="PENDING_ENTRY",
                                        to_state="ENTRY_FILLED",
                                        price=fill_price,
                                        message=f"Replay fill in session {replay_key}",
                                        dedupe_key=fill_dedupe,
                                    )
                                )

                                msg = (
                                    f"OFFLINE_FILL | symbol={symbol} | "
                                    f"side=BUY | qty={order.qty} | fill_price={fill_price} | "
                                    f"candle_time={candle_time.isoformat()}"
                                )
                                summary["orders_filled"].append(msg)
                                logger.info("[GAP_REPLAY] %s", msg)
                                open_positions = list(
                                    (
                                        await db.scalars(
                                            select(PaperPosition).where(
                                                PaperPosition.account_id == account_id,
                                                PaperPosition.status == "OPEN",
                                            )
                                        )
                                    ).all()
                                )
                            else:
                                order.status = "REJECTED"
                                logger.warning(
                                    "[GAP_REPLAY] %s: Offline fill rejected — insufficient funds",
                                    symbol,
                                )
                            break

                # Replay open positions for target/stop hits
                for pos in [p for p in open_positions if p.symbol == symbol]:
                    target_hit = None
                    stop_hit = None
                    for candle in market_candles:
                        c_high = float(candle.high)
                        c_low = float(candle.low)
                        c_time = candle.timestamp
                        if pos.target and target_hit is None and c_high >= float(pos.target):
                            target_hit = (c_time, float(pos.target))
                        if pos.stop_loss and stop_hit is None and c_low <= float(pos.stop_loss):
                            stop_hit = (c_time, float(pos.stop_loss))

                    exit_time = None
                    exit_price = None
                    exit_reason = None

                    if target_hit and stop_hit:
                        if target_hit[0] <= stop_hit[0]:
                            exit_time, exit_price, exit_reason = (
                                target_hit[0],
                                target_hit[1],
                                "TARGET_HIT",
                            )
                        else:
                            exit_time, exit_price, exit_reason = (
                                stop_hit[0],
                                stop_hit[1],
                                "STOPLOSS_HIT",
                            )
                    elif target_hit:
                        exit_time, exit_price, exit_reason = (
                            target_hit[0],
                            target_hit[1],
                            "TARGET_HIT",
                        )
                    elif stop_hit:
                        exit_time, exit_price, exit_reason = (
                            stop_hit[0],
                            stop_hit[1],
                            "STOPLOSS_HIT",
                        )

                    if exit_price is not None:
                        exit_dedupe = f"replay-exit:{replay_key}:{pos.id}:{exit_reason}"
                        if (
                            await db.scalars(
                                select(ExecutionEvent).where(
                                    ExecutionEvent.dedupe_key == exit_dedupe
                                )
                            )
                        ).first():
                            continue
                        entry_price = float(pos.avg_entry_price)
                        qty = float(pos.qty)
                        pnl = (float(exit_price) - entry_price) * qty
                        exit_order = None
                        try:
                            exit_order = PaperOrder(
                                account_id=account_id,
                                symbol=pos.symbol,
                                side="SELL",
                                order_type="MARKET",
                                product_type="CNC",
                                qty=pos.qty,
                                order_price=exit_price,
                                status="FILLED",
                                notes=f"Offline auto-exit: {exit_reason}",
                                filled_price=exit_price,
                                filled_at=exit_time,
                            )
                            db.add(exit_order)
                            await db.flush()
                        except Exception:
                            logger.exception(
                                "[GAP_REPLAY] Failed to add exit order for %s",
                                pos.symbol,
                            )
                            await _safe_rollback(db)
                            continue

                        try:
                            trade = PaperTradeHistory(
                                account_id=account_id,
                                symbol=pos.symbol,
                                qty=pos.qty,
                                entry_price=entry_price,
                                exit_price=exit_price,
                                pnl=pnl,
                                pnl_percent=(
                                    ((float(exit_price) - entry_price) / entry_price * 100)
                                    if entry_price
                                    else 0.0
                                ),
                                notes=pos.notes,
                                source_signal=pos.source_signal,
                                source_score=pos.source_score,
                                source_confidence=pos.source_confidence,
                                opened_at=pos.created_at,
                                closed_at=exit_time,
                                exit_reason=exit_reason,
                            )
                            db.add(trade)
                        except Exception:
                            logger.exception(
                                "[GAP_REPLAY] Failed to add trade history for %s", pos.symbol
                            )

                        try:
                            account.cash_balance = float(account.cash_balance) + float(
                                exit_price
                            ) * int(pos.qty)
                        except Exception:
                            logger.exception(
                                "[GAP_REPLAY] Failed to credit account for %s", pos.symbol
                            )

                        try:
                            tx = PaperTransaction(
                                account_id=account_id,
                                timestamp=exit_time,
                                symbol=pos.symbol,
                                action="AUTO_EXIT",
                                qty=int(pos.qty),
                                price=float(exit_price),
                                amount=float(exit_price) * int(pos.qty),
                                balance_after=float(account.cash_balance),
                            )
                            db.add(tx)
                        except Exception:
                            logger.exception(
                                "[GAP_REPLAY] Failed to add AUTO_EXIT transaction for %s",
                                pos.symbol,
                            )

                        try:
                            db.add(
                                ExecutionEvent(
                                    event_type="REPLAY_EXIT_FILLED",
                                    symbol=pos.symbol,
                                    order_id=getattr(exit_order, "id", None),
                                    position_id=pos.id,
                                    from_state="OPEN_POSITION",
                                    to_state="EXIT_FILLED",
                                    price=exit_price,
                                    message=f"Replay exit in session {replay_key}",
                                    dedupe_key=exit_dedupe,
                                )
                            )
                            await db.delete(pos)
                        except Exception:
                            logger.exception(
                                "[GAP_REPLAY] Failed to delete position %s after offline exit",
                                pos.symbol,
                            )

                        msg = (
                            f"OFFLINE_EXIT | symbol={pos.symbol} | "
                            f"exit_price={exit_price} | reason={exit_reason} | "
                            f"pnl={round(pnl, 2)} | hit_at={exit_time.isoformat()}"
                        )
                        summary["positions_exited"].append(msg)
                        logger.info("[GAP_REPLAY] %s", msg)

            except Exception as e:
                await _safe_rollback(db)
                warning = f"{symbol}: Gap replay failed — {e}"
                summary["warnings"].append(warning)
                logger.error("[GAP_REPLAY] ERROR for %s: %s", symbol, e)
                # Reload account + working sets after rollback so later symbols can proceed
                try:
                    reloaded = (
                        await db.scalars(
                            select(PaperTradingAccount).where(
                                PaperTradingAccount.id == account_id
                            )
                        )
                    ).first()
                    if reloaded is not None:
                        account = reloaded
                    open_positions = list(
                        (
                            await db.scalars(
                                select(PaperPosition).where(
                                    PaperPosition.account_id == account_id,
                                    PaperPosition.status == "OPEN",
                                )
                            )
                        ).all()
                    )
                    pending_orders = list(
                        (
                            await db.scalars(
                                select(PaperOrder).where(
                                    PaperOrder.account_id == account_id,
                                    PaperOrder.status.in_(
                                        (
                                            "PENDING",
                                            "WAITING_FOR_MARKET",
                                            "PENDING_MARKET_OPEN",
                                            "READY_TO_EXECUTE",
                                            "FAILED",
                                            "OPEN",
                                            "PARTIALLY_EXECUTED",
                                        )
                                    ),
                                )
                            )
                        ).all()
                    )
                except Exception:
                    logger.exception(
                        "[GAP_REPLAY] Failed to reload account %s after error", account_id
                    )
                    break
            finally:
                try:
                    existing_replay.checkpoint_symbol = symbol
                    existing_replay.updated_at = datetime.now(timezone.utc)
                    await db.flush()
                except Exception:
                    await _safe_rollback(db)

    try:
        existing_replay.status = "COMPLETED"
        existing_replay.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(
            "[GAP_REPLAY] Committed. Filled=%s Exited=%s Warnings=%s",
            len(summary["orders_filled"]),
            len(summary["positions_exited"]),
            len(summary["warnings"]),
        )
    except Exception as e:
        await _safe_rollback(db)
        try:
            retry_replay = (
                await db.scalars(
                    select(ReplaySession).where(ReplaySession.replay_key == replay_key)
                )
            ).first()
            if retry_replay:
                retry_replay.status = "FAILED"
                retry_replay.error_message = str(e)[:2000]
                await db.commit()
        except Exception:
            await _safe_rollback(db)
        logger.error("[GAP_REPLAY] Commit failed: %s", e)
        summary["warnings"].append(f"Commit failed: {e}")

    write_startup_time()
    return summary


async def wait_for_fyers_token(
    fyers_service: Any,
    *,
    timeout_sec: float = _TOKEN_WAIT_TIMEOUT_SEC,
    poll_sec: float = _TOKEN_WAIT_POLL_SEC,
) -> bool:
    """Poll until FYERS has a usable access token, or the timeout elapses."""
    if _fyers_ready(fyers_service):
        return True
    logger.info(
        "[GAP_REPLAY] Waiting for FYERS token before replay | timeout_sec=%s",
        timeout_sec,
    )
    deadline = time.monotonic() + max(0.0, float(timeout_sec))
    interval = max(0.05, float(poll_sec))
    while time.monotonic() < deadline:
        await asyncio.sleep(interval)
        if _fyers_ready(fyers_service):
            logger.info("[GAP_REPLAY] FYERS token ready — starting replay")
            return True
    logger.warning(
        "[GAP_REPLAY] Timed out waiting for FYERS token | timeout_sec=%s",
        timeout_sec,
    )
    return False


async def run_startup_gap_replay(
    session_factory: Callable[[], Any],
    fyers_service: Any,
    *,
    token_timeout_sec: float = _TOKEN_WAIT_TIMEOUT_SEC,
    token_poll_sec: float = _TOKEN_WAIT_POLL_SEC,
    candle_retries: int = _CANDLE_RETRIES,
    candle_retry_delay_sec: float = _CANDLE_RETRY_DELAY_SEC,
) -> Dict:
    """Startup entry: wait for FYERS auth, then replay, retrying empty fetches.

    Gap replay must not run (or complete) before the daily access token exists.
    Completing with empty candles permanently skips fills/exits for that process.
    """
    token_ok = await wait_for_fyers_token(
        fyers_service,
        timeout_sec=token_timeout_sec,
        poll_sec=token_poll_sec,
    )

    last_summary: Dict = {
        "gap_start": None,
        "gap_end": None,
        "orders_filled": [],
        "positions_exited": [],
        "warnings": [],
        "skipped_reason": SKIP_TOKEN_NOT_READY,
    }
    attempts = max(1, int(candle_retries))
    for attempt in range(1, attempts + 1):
        try:
            async with session_factory() as db:
                last_summary = await run_gap_replay(db, fyers_service)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Bind/port-in-use shutdown cancels this job while the session is
            # still open; SQLAlchemy then raises InterfaceError on rollback.
            if not is_db_connection_error(exc):
                raise
            logger.warning(
                "[GAP_REPLAY] DB connection closed during replay | attempt=%s/%s | err=%s",
                attempt,
                attempts,
                exc,
            )
            if _task_is_cancelling():
                raise asyncio.CancelledError from exc
            last_summary = {
                **last_summary,
                "skipped_reason": SKIP_DB_CONNECTION_CLOSED,
                "warnings": list(last_summary.get("warnings") or []) + [str(exc)],
            }
            return last_summary

        reason = last_summary.get("skipped_reason")
        if reason == SKIP_TOKEN_NOT_READY:
            if not token_ok:
                return last_summary
            token_ok = await wait_for_fyers_token(
                fyers_service,
                timeout_sec=token_timeout_sec,
                poll_sec=token_poll_sec,
            )
            if not token_ok:
                return last_summary
            continue
        if reason == SKIP_NO_CANDLE_DATA and attempt < attempts:
            logger.warning(
                "[GAP_REPLAY] Candle fetch empty — retry %s/%s after %.1fs",
                attempt + 1,
                attempts,
                candle_retry_delay_sec,
            )
            await asyncio.sleep(max(0.0, float(candle_retry_delay_sec)))
            continue
        return last_summary
    return last_summary
