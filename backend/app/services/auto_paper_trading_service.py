"""Automated Paper Trading from Recommendation Engine BUY signals.

When Production / RE-001 / RE-002 emits BUY, place an independent paper order
tagged with that recommendation engine. Engines never share positions.

Design (brownfield):
- Reuses PaperTradingService.place_order (order → fill → position → portfolio)
- Fail-open: never aborts recommendation / scanner pipeline
- Duplicate prevention: skip if OPEN position or open BUY already exists for
  (account, symbol, recommendation_engine)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models.paper_trading import (
    OPEN_ORDER_STATUSES,
    PaperOrder,
    PaperPosition,
    PaperTradingAccount,
)
from ..schemas.paper_trading import PaperOrderCreateRequest
from ..utils.symbol import canonical_symbol
from .paper_trading_service import PaperTradingService
from .recommendation_engine_ids import (
    PRODUCTION,
    RE_001,
    RE_002,
    normalize_recommendation_engine,
)

logger = logging.getLogger("app.auto_paper_trading")


def _lab_auto_allowed(engine: str) -> bool:
    """RE lab engines auto-trade only when PAPER_LINKED (unless force)."""
    eng = normalize_recommendation_engine(engine)
    if eng == PRODUCTION:
        return True
    if bool(getattr(settings, "auto_paper_trading_force_lab", False)):
        return True
    if not bool(getattr(settings, "auto_paper_trading_lab_requires_paper_linked", False)):
        return True
    if eng == RE_001:
        stage = str(getattr(settings, "re001_stage", "OFF") or "OFF").strip().upper()
        return stage == "PAPER_LINKED"
    if eng == RE_002:
        stage = str(getattr(settings, "re002_stage", "OFF") or "OFF").strip().upper()
        return stage == "PAPER_LINKED"
    return False


def _resolve_user_ids(db: Session, explicit_user_id: str | uuid.UUID | None) -> list[uuid.UUID]:
    """Resolve which paper accounts receive auto BUY orders."""
    if explicit_user_id:
        try:
            return [uuid.UUID(str(explicit_user_id))]
        except (ValueError, TypeError):
            logger.warning("auto paper: invalid user_id=%s", explicit_user_id)
            return []

    configured = getattr(settings, "auto_paper_trading_user_id", None)
    if configured:
        try:
            return [uuid.UUID(str(configured))]
        except (ValueError, TypeError):
            logger.warning("auto paper: invalid AUTO_PAPER_TRADING_USER_ID=%s", configured)

    scope = str(getattr(settings, "auto_paper_trading_system_scope", "all") or "all").strip().lower()
    if scope in {"none", "off", "disabled"}:
        return []

    # Default system scope: all paper accounts with a bound user
    rows = db.scalars(
        select(PaperTradingAccount.user_id).where(PaperTradingAccount.user_id.is_not(None))
    ).all()
    return [uid for uid in rows if uid is not None]


def _has_open_position(
    db: Session, account_id: int, symbol: str, engine: str
) -> bool:
    eng = normalize_recommendation_engine(engine)
    row = db.scalar(
        select(PaperPosition.id).where(
            PaperPosition.account_id == account_id,
            PaperPosition.symbol == symbol,
            PaperPosition.status == "OPEN",
            PaperPosition.source_engine_id == eng,
        )
    )
    return row is not None


def _has_open_buy_order(
    db: Session, account_id: int, symbol: str, engine: str
) -> bool:
    eng = normalize_recommendation_engine(engine)
    row = db.scalar(
        select(PaperOrder.id).where(
            PaperOrder.account_id == account_id,
            PaperOrder.symbol == symbol,
            PaperOrder.side == "BUY",
            PaperOrder.status.in_(tuple(OPEN_ORDER_STATUSES)),
            PaperOrder.source_engine_id == eng,
        )
    )
    return row is not None


def _default_qty(available_cash: float, price: float) -> int:
    if price <= 0:
        return 1
    alloc = float(getattr(settings, "auto_paper_trading_allocation_pct", 0.05) or 0.05)
    budget = max(0.0, available_cash) * alloc
    qty = int(budget // price)
    return max(1, qty)


def place_auto_paper_buy(
    db: Session,
    *,
    symbol: str,
    recommendation_engine: str,
    signal: str = "BUY",
    score: float | None = None,
    confidence: float | None = None,
    engine_version: str | None = None,
    recommendation_id: str | None = None,
    experiment_id: str | None = None,
    stop_loss: float | None = None,
    target: float | None = None,
    limit_price: float | None = None,
    qty: int | None = None,
    user_id: str | uuid.UUID | None = None,
    notes: str | None = None,
) -> list[dict[str, Any]]:
    """Place auto paper BUY(s) for the given recommendation engine.

    Returns a list of result dicts (one per target account). Never raises.
    """
    results: list[dict[str, Any]] = []
    try:
        if not bool(getattr(settings, "auto_paper_trading_enabled", True)):
            return [{"skipped": True, "reason": "auto_paper_trading_disabled"}]

        state = (signal or "").strip().upper()
        if state != "BUY":
            return [{"skipped": True, "reason": f"signal_not_buy:{state or 'empty'}"}]

        engine = normalize_recommendation_engine(recommendation_engine)
        if not _lab_auto_allowed(engine):
            return [
                {
                    "skipped": True,
                    "reason": "lab_stage_not_paper_linked",
                    "engine": engine,
                }
            ]

        sym = canonical_symbol(symbol)
        if not sym:
            return [{"skipped": True, "reason": "invalid_symbol"}]

        user_ids = _resolve_user_ids(db, user_id)
        if not user_ids:
            return [{"skipped": True, "reason": "no_target_users"}]

        for uid in user_ids:
            result = _place_for_user(
                db,
                user_id=uid,
                symbol=sym,
                engine=engine,
                score=score,
                confidence=confidence,
                engine_version=engine_version,
                recommendation_id=recommendation_id,
                experiment_id=experiment_id,
                stop_loss=stop_loss,
                target=target,
                limit_price=limit_price,
                qty=qty,
                notes=notes,
            )
            results.append(result)
        return results
    except Exception as exc:
        logger.warning(
            "AUTO_PAPER_BUY_FAILED | symbol=%s | engine=%s | err=%s",
            symbol,
            recommendation_engine,
            exc,
            exc_info=True,
        )
        return [{"skipped": True, "reason": f"error:{exc}"}]


def _place_for_user(
    db: Session,
    *,
    user_id: uuid.UUID,
    symbol: str,
    engine: str,
    score: float | None,
    confidence: float | None,
    engine_version: str | None,
    recommendation_id: str | None,
    experiment_id: str | None,
    stop_loss: float | None,
    target: float | None,
    limit_price: float | None,
    qty: int | None,
    notes: str | None,
) -> dict[str, Any]:
    service = PaperTradingService(db, user_id=user_id)
    try:
        account = service._get_or_create_account(for_update=True)
    except Exception as exc:
        return {"user_id": str(user_id), "skipped": True, "reason": f"account_error:{exc}"}

    if _has_open_position(db, account.id, symbol, engine):
        logger.info(
            "AUTO_PAPER_SKIP_DUPLICATE_POSITION | user=%s | account=%s | symbol=%s | engine=%s",
            user_id,
            account.id,
            symbol,
            engine,
        )
        return {
            "user_id": str(user_id),
            "skipped": True,
            "reason": "open_position_exists",
            "symbol": symbol,
            "engine": engine,
        }

    if _has_open_buy_order(db, account.id, symbol, engine):
        logger.info(
            "AUTO_PAPER_SKIP_DUPLICATE_ORDER | user=%s | account=%s | symbol=%s | engine=%s",
            user_id,
            account.id,
            symbol,
            engine,
        )
        return {
            "user_id": str(user_id),
            "skipped": True,
            "reason": "open_buy_order_exists",
            "symbol": symbol,
            "engine": engine,
        }

    try:
        # Use LTP path for sizing; place MARKET so fill runs when session open
        price_snap = service._price_for_execution(symbol)
        price = float(price_snap.current_price or 0.0)
        available = float(service._available_cash_fast(account))
        order_qty = int(qty) if qty and int(qty) >= 1 else _default_qty(available, price if price > 0 else 100.0)

        # Deterministic idempotency for same recommendation → same order
        if recommendation_id:
            idem = f"auto-paper:{engine}:{recommendation_id}:{user_id}"
        else:
            idem = f"auto-paper:{engine}:{symbol}:{user_id}:{uuid.uuid4().hex[:12]}"
        # Cap to 128 chars (schema limit)
        idem = idem[:128]

        note = notes or (
            f"Auto paper trade from {engine} BUY | symbol={symbol}"
            + (f" | rec_id={recommendation_id}" if recommendation_id else "")
        )

        payload = PaperOrderCreateRequest(
            idempotency_key=idem,
            symbol=symbol,
            side="BUY",
            type="MARKET",
            product_type="CNC",
            qty=order_qty,
            limit_price=limit_price,
            stop_loss=stop_loss,
            target=target,
            notes=note[:1000] if note else None,
            source_signal="BUY",
            source_score=score,
            source_confidence=confidence,
            source_engine_id=engine,
            source_engine_version=engine_version,
            source_recommendation_id=recommendation_id,
            experiment_id=experiment_id,
            recommendation_engine=engine,
        )
        response = service.place_order(payload)
        order = response.order
        position = response.position
        logger.info(
            "AUTO_PAPER_BUY_PLACED | user=%s | account=%s | symbol=%s | engine=%s | "
            "order_id=%s | status=%s | position_id=%s | qty=%s",
            user_id,
            account.id,
            symbol,
            engine,
            getattr(order, "id", None) if order else None,
            getattr(order, "status", None) if order else None,
            getattr(position, "id", None) if position else None,
            order_qty,
        )
        return {
            "user_id": str(user_id),
            "skipped": False,
            "symbol": symbol,
            "engine": engine,
            "order_id": getattr(order, "id", None) if order else None,
            "order_status": getattr(order, "status", None) if order else None,
            "position_id": getattr(position, "id", None) if position else None,
            "message": response.message,
        }
    except Exception as exc:
        logger.warning(
            "AUTO_PAPER_BUY_PLACE_ERROR | user=%s | symbol=%s | engine=%s | err=%s",
            user_id,
            symbol,
            engine,
            exc,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "user_id": str(user_id),
            "skipped": True,
            "reason": f"place_error:{exc}",
            "symbol": symbol,
            "engine": engine,
        }


def maybe_auto_paper_from_lab_decision(
    db: Session,
    decision: Any,
    *,
    user_id: str | uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Hook after RE-001 / RE-002 decision persist. Fail-open."""
    try:
        state = str(getattr(decision, "recommendation_state", None) or "").strip().upper()
        if state != "BUY":
            return [{"skipped": True, "reason": f"state_{state or 'empty'}"}]

        engine = normalize_recommendation_engine(
            getattr(decision, "engine_id", None) or RE_001
        )
        symbol = getattr(decision, "symbol", None)
        stop = target = entry = None
        tg = getattr(decision, "trade_guidance", None)
        if tg is not None:
            if hasattr(tg, "stop_loss"):
                stop = getattr(tg, "stop_loss", None)
                target = getattr(tg, "target_1", None)
                entry = getattr(tg, "entry_high", None) or getattr(tg, "entry_low", None)
            elif isinstance(tg, dict):
                stop = tg.get("stop_loss")
                target = tg.get("target_1")
                entry = tg.get("entry_high") or tg.get("entry_low")

        # Prefer scan-context user when not passed
        if user_id is None:
            try:
                from .re001.scan_context import get_user_id as _get_lab_user

                user_id = _get_lab_user()
            except Exception:
                user_id = None

        return place_auto_paper_buy(
            db,
            symbol=str(symbol or ""),
            recommendation_engine=engine,
            signal="BUY",
            score=None,
            confidence=float(getattr(decision, "confidence_score", 0) or 0) or None,
            engine_version=str(getattr(decision, "engine_version", None) or "") or None,
            recommendation_id=str(getattr(decision, "recommendation_id", None) or "") or None,
            experiment_id=getattr(decision, "experiment_id", None),
            stop_loss=float(stop) if stop else None,
            target=float(target) if target else None,
            limit_price=float(entry) if entry else None,
            user_id=user_id,
        )
    except Exception as exc:
        logger.warning("maybe_auto_paper_from_lab_decision failed | %s", exc, exc_info=True)
        return [{"skipped": True, "reason": f"hook_error:{exc}"}]


def maybe_auto_paper_from_production(
    db: Session,
    *,
    symbol: str,
    action: str,
    score: float | None = None,
    confidence: float | None = None,
    stop_loss: float | None = None,
    target: float | None = None,
    entry: float | None = None,
    user_id: str | uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Hook after production recommendation BUY. Fail-open."""
    try:
        if user_id is None:
            try:
                from .re001.scan_context import get_user_id as _get_lab_user

                user_id = _get_lab_user()
            except Exception:
                user_id = None
        return place_auto_paper_buy(
            db,
            symbol=symbol,
            recommendation_engine=PRODUCTION,
            signal=action,
            score=score,
            confidence=confidence,
            engine_version="production",
            recommendation_id=None,
            stop_loss=stop_loss,
            target=target,
            limit_price=entry,
            user_id=user_id,
            notes=f"Auto paper trade from Production BUY | symbol={canonical_symbol(symbol)}",
        )
    except Exception as exc:
        logger.warning("maybe_auto_paper_from_production failed | %s", exc, exc_info=True)
        return [{"skipped": True, "reason": f"hook_error:{exc}"}]
