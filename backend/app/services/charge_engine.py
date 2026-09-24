from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Literal
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.paper_charges import ChargeProfile, TradeChargeBreakdown
from ..utils import get_logger

logger = get_logger("app.charge_engine")

# Thread-safe in-memory cache for the active charge profiles
_profile_cache: dict[str, tuple[ChargeProfile, float]] = {}
_profile_cache_lock = threading.Lock()
_PROFILE_CACHE_TTL_SEC = 30.0

DEFAULT_PROFILE_DATA = {
    "profile_name": "Default NSE Equity Delivery",
    "broker_id": "DEFAULT",
    "exchange": "NSE",
    "segment": "EQUITY_DELIVERY",
    "currency": "INR",
    "is_active": True,
    "is_default": True,
    "version": 1,
    "rounding_mode": "ROUND_HALF_UP",
    "money_decimal_places": 2,
    "brokerage_type": "ZERO",
    "brokerage_rate_pct": Decimal("0"),
    "brokerage_flat_per_executed_order": Decimal("0"),
    "brokerage_order_cap": Decimal("0"),
    "stt_buy_rate_pct": Decimal("0.10"),
    "stt_sell_rate_pct": Decimal("0.10"),
    "exchange_transaction_charge_buy_rate_pct": Decimal("0.00307"),
    "exchange_transaction_charge_sell_rate_pct": Decimal("0.00307"),
    "sebi_turnover_fee_rate_pct": Decimal("0.00010"),
    "clearing_charge_buy_rate_pct": Decimal("0"),
    "clearing_charge_sell_rate_pct": Decimal("0"),
    "gst_rate_pct": Decimal("18.0"),
    "stamp_duty_buy_rate_pct": Decimal("0.015"),
    "stamp_duty_sell_rate_pct": Decimal("0"),
    "dp_charge_on_delivery_sell": Decimal("0"),
    "dp_charge_scope": "PER_SELL_ORDER",
    "include_estimated_exit_charges_in_unrealised_pnl": False,
    "notes": "Default statutory charges for Indian cash equity delivery swing trading.",
}


@dataclass(slots=True)
class ChargeCalculationResult:
    side: str
    qty: Decimal
    price: Decimal
    turnover: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_charges: Decimal
    sebi_charges: Decimal
    clearing_charges: Decimal
    gst: Decimal
    stamp_duty: Decimal
    dp_charges: Decimal
    total_charges: Decimal
    effective_rate_per_share: Decimal
    effective_total: Decimal
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "qty": float(self.qty),
            "price": float(self.price),
            "turnover": float(self.turnover),
            "brokerage": float(self.brokerage),
            "stt": float(self.stt),
            "exchange_charges": float(self.exchange_charges),
            "sebi_charges": float(self.sebi_charges),
            "clearing_charges": float(self.clearing_charges),
            "gst": float(self.gst),
            "stamp_duty": float(self.stamp_duty),
            "dp_charges": float(self.dp_charges),
            "total_charges": float(self.total_charges),
            "effective_rate_per_share": float(self.effective_rate_per_share),
            "effective_total": float(self.effective_total),
            "metadata": self.metadata,
        }


def to_decimal(val: Any, default: str = "0") -> Decimal:
    if val is None:
        return Decimal(default)
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val).strip())
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def get_rounding_mode(mode_str: str) -> str:
    # Python decimal supports ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING, etc.
    valid_modes = {
        "ROUND_HALF_UP": ROUND_HALF_UP,
        "ROUND_HALF_EVEN": "ROUND_HALF_EVEN",
    }
    return valid_modes.get(mode_str, ROUND_HALF_UP)


def calculate_delivery_charges(
    side: str,
    qty: int | float | Decimal,
    price: int | float | Decimal,
    profile: ChargeProfile | None = None,
    *,
    apply_dp_charge: bool = True,
) -> ChargeCalculationResult:
    """Calculate deterministic transaction costs for an Indian cash-equity delivery trade.

    Strict statutory and broker rules:
    - Brokerage: calculated according to configured brokerage type.
    - STT: applied on buy and sell delivery turnover.
    - Stamp duty: applied strictly on buy delivery turnover only.
    - Exchange transaction charges: applied on both buy and sell turnover.
    - SEBI turnover charges: applied on both buy and sell turnover.
    - Clearing charges: applied on both sides if non-zero.
    - GST: 18% applied strictly on taxable services: (brokerage + exchange charges + sebi charges + clearing charges).
    - DP charges: applied on delivery sell only if apply_dp_charge is True.
    - Component rounding: rounded to profile.money_decimal_places using ROUND_HALF_UP.
    """
    clean_side = str(side).upper().strip()
    if clean_side not in {"BUY", "SELL"}:
        raise ValueError(f"Invalid transaction side: {side}. Must be BUY or SELL.")

    d_qty = to_decimal(qty)
    d_price = to_decimal(price)
    if d_qty <= Decimal("0"):
        raise ValueError(f"Quantity must be positive, got {qty}")
    if d_price < Decimal("0"):
        raise ValueError(f"Price must be non-negative, got {price}")

    # Fallback to default in-memory profile if none provided
    p_name = profile.profile_name if profile else DEFAULT_PROFILE_DATA["profile_name"]
    p_ver = profile.version if profile else int(DEFAULT_PROFILE_DATA["version"])
    places = int(profile.money_decimal_places if profile else DEFAULT_PROFILE_DATA["money_decimal_places"])
    round_mode = str(profile.rounding_mode if profile else DEFAULT_PROFILE_DATA["rounding_mode"])
    quantize_target = Decimal("10") ** -places

    brok_type = str(profile.brokerage_type if profile else DEFAULT_PROFILE_DATA["brokerage_type"]).upper()
    brok_rate = to_decimal(profile.brokerage_rate_pct if profile else DEFAULT_PROFILE_DATA["brokerage_rate_pct"])
    brok_flat = to_decimal(profile.brokerage_flat_per_executed_order if profile else DEFAULT_PROFILE_DATA["brokerage_flat_per_executed_order"])
    brok_cap = to_decimal(profile.brokerage_order_cap if profile else DEFAULT_PROFILE_DATA["brokerage_order_cap"])

    if profile:
        stt_rate = to_decimal(profile.stt_buy_rate_pct if clean_side == "BUY" else profile.stt_sell_rate_pct)
        exch_rate = to_decimal(profile.exchange_transaction_charge_buy_rate_pct if clean_side == "BUY" else profile.exchange_transaction_charge_sell_rate_pct)
        sebi_rate = to_decimal(profile.sebi_turnover_fee_rate_pct)
        clear_rate = to_decimal(profile.clearing_charge_buy_rate_pct if clean_side == "BUY" else profile.clearing_charge_sell_rate_pct)
        gst_rate = to_decimal(profile.gst_rate_pct)
        stamp_rate = to_decimal(profile.stamp_duty_buy_rate_pct if clean_side == "BUY" else profile.stamp_duty_sell_rate_pct)
        dp_amt = to_decimal(profile.dp_charge_on_delivery_sell)
    else:
        stt_rate = to_decimal(DEFAULT_PROFILE_DATA["stt_buy_rate_pct"] if clean_side == "BUY" else DEFAULT_PROFILE_DATA["stt_sell_rate_pct"])
        exch_rate = to_decimal(DEFAULT_PROFILE_DATA["exchange_transaction_charge_buy_rate_pct"] if clean_side == "BUY" else DEFAULT_PROFILE_DATA["exchange_transaction_charge_sell_rate_pct"])
        sebi_rate = to_decimal(DEFAULT_PROFILE_DATA["sebi_turnover_fee_rate_pct"])
        clear_rate = to_decimal(DEFAULT_PROFILE_DATA["clearing_charge_buy_rate_pct"] if clean_side == "BUY" else DEFAULT_PROFILE_DATA["clearing_charge_sell_rate_pct"])
        gst_rate = to_decimal(DEFAULT_PROFILE_DATA["gst_rate_pct"])
        stamp_rate = to_decimal(DEFAULT_PROFILE_DATA["stamp_duty_buy_rate_pct"] if clean_side == "BUY" else DEFAULT_PROFILE_DATA["stamp_duty_sell_rate_pct"])
        dp_amt = to_decimal(DEFAULT_PROFILE_DATA["dp_charge_on_delivery_sell"])

    # 1. Nominal Turnover
    turnover = (d_qty * d_price).quantize(quantize_target, rounding=ROUND_HALF_UP)

    # 2. Brokerage calculation
    raw_brokerage = Decimal("0")
    if brok_type == "ZERO":
        raw_brokerage = Decimal("0")
    elif brok_type == "PERCENTAGE":
        raw_brokerage = turnover * (brok_rate / Decimal("100"))
    elif brok_type == "FLAT_PER_EXECUTED_ORDER":
        raw_brokerage = brok_flat
    elif brok_type == "MIN_OF_PERCENTAGE_OR_FLAT_CAP":
        pct_fee = turnover * (brok_rate / Decimal("100"))
        raw_brokerage = min(pct_fee, brok_cap) if brok_cap > 0 else pct_fee
    else:
        raw_brokerage = Decimal("0")
    brokerage = max(Decimal("0"), raw_brokerage.quantize(quantize_target, rounding=ROUND_HALF_UP))

    # 3. STT (Securities Transaction Tax)
    # Applied on turnover for both buy and sell delivery
    stt = max(Decimal("0"), (turnover * (stt_rate / Decimal("100"))).quantize(quantize_target, rounding=ROUND_HALF_UP))

    # 4. Exchange Transaction Charges
    exch_charge = max(Decimal("0"), (turnover * (exch_rate / Decimal("100"))).quantize(quantize_target, rounding=ROUND_HALF_UP))

    # 5. SEBI Turnover Fee
    sebi_charge = max(Decimal("0"), (turnover * (sebi_rate / Decimal("100"))).quantize(quantize_target, rounding=ROUND_HALF_UP))

    # 6. Clearing Charges
    clearing_charge = max(Decimal("0"), (turnover * (clear_rate / Decimal("100"))).quantize(quantize_target, rounding=ROUND_HALF_UP))

    # 7. GST (18% applied strictly on taxable services)
    # Taxable Services = Brokerage + Exchange Charges + SEBI Charges + Clearing Charges
    taxable_services = brokerage + exch_charge + sebi_charge + clearing_charge
    gst = max(Decimal("0"), (taxable_services * (gst_rate / Decimal("100"))).quantize(quantize_target, rounding=ROUND_HALF_UP))

    # 8. Stamp Duty (Buy side only for delivery)
    if clean_side == "BUY":
        stamp_duty = max(Decimal("0"), (turnover * (stamp_rate / Decimal("100"))).quantize(quantize_target, rounding=ROUND_HALF_UP))
    else:
        stamp_duty = max(Decimal("0"), (turnover * (stamp_rate / Decimal("100"))).quantize(quantize_target, rounding=ROUND_HALF_UP))

    # 9. Depository Participant (DP) Charge (Sell side only)
    if clean_side == "SELL" and apply_dp_charge and dp_amt > Decimal("0"):
        dp_charge = dp_amt.quantize(quantize_target, rounding=ROUND_HALF_UP)
    else:
        dp_charge = Decimal("0.00")

    # 10. Total charges
    total_charges = (
        brokerage
        + stt
        + exch_charge
        + sebi_charge
        + clearing_charge
        + gst
        + stamp_duty
        + dp_charge
    ).quantize(quantize_target, rounding=ROUND_HALF_UP)

    # 11. Effective price and effective total
    if clean_side == "BUY":
        effective_total = (turnover + total_charges).quantize(quantize_target, rounding=ROUND_HALF_UP)
        effective_rate = (effective_total / d_qty).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    else:
        effective_total = max(Decimal("0"), (turnover - total_charges).quantize(quantize_target, rounding=ROUND_HALF_UP))
        effective_rate = (effective_total / d_qty).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    metadata = {
        "profile_name": p_name,
        "profile_version": p_ver,
        "brokerage_type": brok_type,
        "taxable_services_base": float(taxable_services),
        "rates_applied": {
            "brokerage_rate_pct": float(brok_rate),
            "stt_rate_pct": float(stt_rate),
            "exchange_rate_pct": float(exch_rate),
            "sebi_rate_pct": float(sebi_rate),
            "clearing_rate_pct": float(clear_rate),
            "gst_rate_pct": float(gst_rate),
            "stamp_duty_rate_pct": float(stamp_rate),
            "dp_charge_applied": float(dp_charge),
        },
        "rounding": {
            "mode": round_mode,
            "decimal_places": places,
        },
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }

    return ChargeCalculationResult(
        side=clean_side,
        qty=d_qty,
        price=d_price,
        turnover=turnover,
        brokerage=brokerage,
        stt=stt,
        exchange_charges=exch_charge,
        sebi_charges=sebi_charge,
        clearing_charges=clearing_charge,
        gst=gst,
        stamp_duty=stamp_duty,
        dp_charges=dp_charge,
        total_charges=total_charges,
        effective_rate_per_share=effective_rate,
        effective_total=effective_total,
        metadata=metadata,
    )


def calculate_break_even_sell_price(
    qty: int | float | Decimal,
    avg_entry_price: int | float | Decimal,
    total_buy_charges: int | float | Decimal,
    profile: ChargeProfile | None = None,
) -> Decimal:
    """Calculate the exact exit price per share such that Net P&L = 0 after all buy & sell charges.

    Solves:
        Net Proceeds(P) = P * qty - SellCharges(P, qty)
        Net P&L = Net Proceeds(P) - Total Invested = 0
        where Total Invested = (qty * avg_entry_price) + total_buy_charges

    Using fixed-point algebra with statutory rates, then verifies with component rounding.
    """
    d_qty = to_decimal(qty)
    d_entry = to_decimal(avg_entry_price)
    d_buy_charges = to_decimal(total_buy_charges)

    if d_qty <= Decimal("0") or d_entry <= Decimal("0"):
        return Decimal("0.00")

    total_invested = (d_qty * d_entry) + d_buy_charges

    stt_rate = to_decimal(profile.stt_sell_rate_pct if profile else DEFAULT_PROFILE_DATA["stt_sell_rate_pct"]) / Decimal("100")
    exch_rate = to_decimal(profile.exchange_transaction_charge_sell_rate_pct if profile else DEFAULT_PROFILE_DATA["exchange_transaction_charge_sell_rate_pct"]) / Decimal("100")
    sebi_rate = to_decimal(profile.sebi_turnover_fee_rate_pct if profile else DEFAULT_PROFILE_DATA["sebi_turnover_fee_rate_pct"]) / Decimal("100")
    clear_rate = to_decimal(profile.clearing_charge_sell_rate_pct if profile else DEFAULT_PROFILE_DATA["clearing_charge_sell_rate_pct"]) / Decimal("100")
    gst_rate = to_decimal(profile.gst_rate_pct if profile else DEFAULT_PROFILE_DATA["gst_rate_pct"]) / Decimal("100")
    dp_amt = to_decimal(profile.dp_charge_on_delivery_sell if profile else DEFAULT_PROFILE_DATA["dp_charge_on_delivery_sell"])

    brok_type = str(profile.brokerage_type if profile else DEFAULT_PROFILE_DATA["brokerage_type"]).upper()
    brok_pct = Decimal("0")
    fixed_fees = dp_amt
    if brok_type == "PERCENTAGE":
        brok_pct = to_decimal(profile.brokerage_rate_pct if profile else DEFAULT_PROFILE_DATA["brokerage_rate_pct"]) / Decimal("100")
    elif brok_type == "FLAT_PER_EXECUTED_ORDER":
        flat = to_decimal(profile.brokerage_flat_per_executed_order if profile else DEFAULT_PROFILE_DATA["brokerage_flat_per_executed_order"])
        fixed_fees += flat + (flat * gst_rate)

    # Taxable rate on variable turnover
    taxable_rate = brok_pct + exch_rate + sebi_rate + clear_rate
    gst_variable_rate = taxable_rate * gst_rate
    total_variable_rate = stt_rate + exch_rate + sebi_rate + clear_rate + brok_pct + gst_variable_rate

    # If variable rate >= 1.0 (impossible in practice), guard against divide by zero
    if total_variable_rate >= Decimal("0.99"):
        total_variable_rate = Decimal("0.99")

    # Initial algebraic guess: P * qty * (1 - total_variable_rate) = total_invested + fixed_fees
    net_turnover_needed = total_invested + fixed_fees
    raw_p = net_turnover_needed / (d_qty * (Decimal("1") - total_variable_rate))

    # Refine guess with component rounding to guarantee Net P&L >= 0
    p_guess = raw_p.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    for _ in range(20):
        res = calculate_delivery_charges("SELL", d_qty, p_guess, profile, apply_dp_charge=True)
        net_proceeds = res.turnover - res.total_charges
        if net_proceeds >= total_invested:
            break
        p_guess += Decimal("0.01")

    return p_guess.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_or_create_default_profile(db: Session) -> ChargeProfile:
    """Ensure the system default profile exists in the database and return it."""
    profile = db.scalar(
        select(ChargeProfile).where(
            ChargeProfile.broker_id == "DEFAULT",
            ChargeProfile.exchange == "NSE",
            ChargeProfile.segment == "EQUITY_DELIVERY",
            ChargeProfile.is_default == True,
            ChargeProfile.is_active == True,
        ).order_by(ChargeProfile.version.desc())
    )
    if profile:
        return profile

    profile = ChargeProfile(
        profile_name=DEFAULT_PROFILE_DATA["profile_name"],
        broker_id=DEFAULT_PROFILE_DATA["broker_id"],
        exchange=DEFAULT_PROFILE_DATA["exchange"],
        segment=DEFAULT_PROFILE_DATA["segment"],
        currency=DEFAULT_PROFILE_DATA["currency"],
        is_active=DEFAULT_PROFILE_DATA["is_active"],
        is_default=DEFAULT_PROFILE_DATA["is_default"],
        version=int(DEFAULT_PROFILE_DATA["version"]),
        rounding_mode=DEFAULT_PROFILE_DATA["rounding_mode"],
        money_decimal_places=int(DEFAULT_PROFILE_DATA["money_decimal_places"]),
        brokerage_type=DEFAULT_PROFILE_DATA["brokerage_type"],
        brokerage_rate_pct=DEFAULT_PROFILE_DATA["brokerage_rate_pct"],
        brokerage_flat_per_executed_order=DEFAULT_PROFILE_DATA["brokerage_flat_per_executed_order"],
        brokerage_order_cap=DEFAULT_PROFILE_DATA["brokerage_order_cap"],
        stt_buy_rate_pct=DEFAULT_PROFILE_DATA["stt_buy_rate_pct"],
        stt_sell_rate_pct=DEFAULT_PROFILE_DATA["stt_sell_rate_pct"],
        exchange_transaction_charge_buy_rate_pct=DEFAULT_PROFILE_DATA["exchange_transaction_charge_buy_rate_pct"],
        exchange_transaction_charge_sell_rate_pct=DEFAULT_PROFILE_DATA["exchange_transaction_charge_sell_rate_pct"],
        sebi_turnover_fee_rate_pct=DEFAULT_PROFILE_DATA["sebi_turnover_fee_rate_pct"],
        clearing_charge_buy_rate_pct=DEFAULT_PROFILE_DATA["clearing_charge_buy_rate_pct"],
        clearing_charge_sell_rate_pct=DEFAULT_PROFILE_DATA["clearing_charge_sell_rate_pct"],
        gst_rate_pct=DEFAULT_PROFILE_DATA["gst_rate_pct"],
        stamp_duty_buy_rate_pct=DEFAULT_PROFILE_DATA["stamp_duty_buy_rate_pct"],
        stamp_duty_sell_rate_pct=DEFAULT_PROFILE_DATA["stamp_duty_sell_rate_pct"],
        dp_charge_on_delivery_sell=DEFAULT_PROFILE_DATA["dp_charge_on_delivery_sell"],
        dp_charge_scope=DEFAULT_PROFILE_DATA["dp_charge_scope"],
        include_estimated_exit_charges_in_unrealised_pnl=DEFAULT_PROFILE_DATA["include_estimated_exit_charges_in_unrealised_pnl"],
        notes=DEFAULT_PROFILE_DATA["notes"],
    )
    db.add(profile)
    try:
        db.flush()
    except Exception:
        db.rollback()
        # Retry query in case of concurrent insert
        existing = db.scalar(
            select(ChargeProfile).where(
                ChargeProfile.broker_id == "DEFAULT",
                ChargeProfile.exchange == "NSE",
                ChargeProfile.segment == "EQUITY_DELIVERY",
            ).order_by(ChargeProfile.version.desc())
        )
        if existing:
            return existing
        raise
    return profile


def get_active_profile(
    db: Session,
    broker_id: str = "DEFAULT",
    exchange: str = "NSE",
    segment: str = "EQUITY_DELIVERY",
) -> ChargeProfile:
    """Retrieve active profile for the specified broker/exchange/segment with fallback to default."""
    cache_key = f"{broker_id}:{exchange}:{segment}"
    import time
    now_ts = time.time()

    with _profile_cache_lock:
        if cache_key in _profile_cache:
            p, exp = _profile_cache[cache_key]
            if now_ts < exp:
                return p

    profile = db.scalar(
        select(ChargeProfile).where(
            ChargeProfile.broker_id == broker_id,
            ChargeProfile.exchange == exchange,
            ChargeProfile.segment == segment,
            ChargeProfile.is_active == True,
        ).order_by(ChargeProfile.version.desc())
    )

    if not profile:
        profile = get_or_create_default_profile(db)

    with _profile_cache_lock:
        _profile_cache[cache_key] = (profile, now_ts + _PROFILE_CACHE_TTL_SEC)

    return profile


def invalidate_charge_profile_cache() -> None:
    with _profile_cache_lock:
        _profile_cache.clear()
