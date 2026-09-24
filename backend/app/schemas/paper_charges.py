from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChargeItemBreakdown(BaseModel):
    turnover: float
    brokerage: float
    stt: float
    exchange_charges: float
    sebi_charges: float
    clearing_charges: float
    gst: float
    stamp_duty: float
    dp_charges: float
    total_charges: float


class ChargePreviewRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: int = Field(gt=0)
    price: float = Field(ge=0.0)
    type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT", "GTT"] = "MARKET"
    product_type: str = "CNC"
    exchange: str = "NSE"
    broker_id: str = "DEFAULT"


class ChargePreviewResponse(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: int
    price: float
    turnover: float
    charges: ChargeItemBreakdown
    estimated_order_cost: float
    estimated_net_proceeds: float
    effective_price_per_share: float
    break_even_price: float | None = None
    profile_version: int
    profile_name: str
    assumptions: dict[str, Any]


class ChargeProfileResponse(BaseModel):
    id: int
    profile_name: str
    broker_id: str
    exchange: str
    segment: str
    currency: str
    is_active: bool
    is_default: bool
    version: int
    rounding_mode: str
    money_decimal_places: int
    brokerage_type: str
    brokerage_rate_pct: float
    brokerage_flat_per_executed_order: float
    brokerage_order_cap: float
    stt_buy_rate_pct: float
    stt_sell_rate_pct: float
    exchange_transaction_charge_buy_rate_pct: float
    exchange_transaction_charge_sell_rate_pct: float
    sebi_turnover_fee_rate_pct: float
    clearing_charge_buy_rate_pct: float
    clearing_charge_sell_rate_pct: float
    gst_rate_pct: float
    stamp_duty_buy_rate_pct: float
    stamp_duty_sell_rate_pct: float
    dp_charge_on_delivery_sell: float
    dp_charge_scope: str
    include_estimated_exit_charges_in_unrealised_pnl: bool
    notes: str | None = None
    effective_from: datetime
    created_at: datetime


class ChargeProfileCreateRequest(BaseModel):
    profile_name: str
    broker_id: str = "DEFAULT"
    exchange: str = "NSE"
    segment: str = "EQUITY_DELIVERY"
    currency: str = "INR"
    is_active: bool = True
    is_default: bool = False
    rounding_mode: str = "ROUND_HALF_UP"
    money_decimal_places: int = 2
    brokerage_type: Literal["ZERO", "PERCENTAGE", "FLAT_PER_EXECUTED_ORDER", "MIN_OF_PERCENTAGE_OR_FLAT_CAP"] = "ZERO"
    brokerage_rate_pct: float = 0.0
    brokerage_flat_per_executed_order: float = 0.0
    brokerage_order_cap: float = 0.0
    stt_buy_rate_pct: float = 0.10
    stt_sell_rate_pct: float = 0.10
    exchange_transaction_charge_buy_rate_pct: float = 0.00307
    exchange_transaction_charge_sell_rate_pct: float = 0.00307
    sebi_turnover_fee_rate_pct: float = 0.00010
    clearing_charge_buy_rate_pct: float = 0.0
    clearing_charge_sell_rate_pct: float = 0.0
    gst_rate_pct: float = 18.0
    stamp_duty_buy_rate_pct: float = 0.015
    stamp_duty_sell_rate_pct: float = 0.0
    dp_charge_on_delivery_sell: float = 0.0
    dp_charge_scope: Literal["PER_SELL_ORDER", "PER_ISIN_PER_DAY"] = "PER_SELL_ORDER"
    include_estimated_exit_charges_in_unrealised_pnl: bool = False
    notes: str | None = None


class PositionPnLResponse(BaseModel):
    position_id: int
    symbol: str
    qty: int
    avg_entry_price: float
    current_price: float
    invested_value: float
    total_buy_charges: float
    gross_unrealized_pnl: float
    estimated_exit_charges: float
    net_unrealized_pnl: float
    net_return_percent: float
    break_even_price: float
    include_exit_charges: bool
    charges_breakdown: ChargeItemBreakdown | None = None


class OrderChargeBreakdownResponse(BaseModel):
    order_id: int | None
    trade_id: int | None
    symbol: str
    side: str
    executed_qty: float
    executed_price: float
    turnover: float
    charges: ChargeItemBreakdown
    created_at: datetime

