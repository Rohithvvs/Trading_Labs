from decimal import Decimal
import pytest

from app.models.paper_charges import ChargeProfile
from app.services.charge_engine import (
    calculate_delivery_charges,
    calculate_break_even_sell_price,
    DEFAULT_PROFILE_DATA,
)


def test_default_buy_delivery_charges():
    # 100 shares @ Rs 500 = Turnover Rs 50,000
    res = calculate_delivery_charges(
        side="BUY",
        qty=100,
        price=500,
    )
    assert res.turnover == Decimal("50000.00")
    assert res.brokerage == Decimal("0.00")
    # STT: 0.10% of 50000 = 50.00
    assert res.stt == Decimal("50.00")
    # NSE Exchange fee: 0.00307% of 50000 = 1.535 -> 1.54
    assert res.exchange_charges == Decimal("1.54")
    # SEBI fee: 0.00010% of 50000 = 0.05
    assert res.sebi_charges == Decimal("0.05")
    # Clearing charges: 0
    assert res.clearing_charges == Decimal("0.00")
    # Taxable base: 0 + 1.54 + 0.05 = 1.59
    # GST: 18% of 1.59 = 0.2862 -> 0.29
    assert res.gst == Decimal("0.29")
    # Stamp duty: 0.015% of 50000 = 7.50
    assert res.stamp_duty == Decimal("7.50")
    # DP charges on BUY: 0
    assert res.dp_charges == Decimal("0.00")
    # Total charges: 50.00 + 1.54 + 0.05 + 0.29 + 7.50 = 59.38
    assert res.total_charges == Decimal("59.38")
    assert res.effective_total == Decimal("50059.38")


def test_default_sell_delivery_charges():
    # 100 shares @ Rs 550 = Turnover Rs 55,000
    res = calculate_delivery_charges(
        side="SELL",
        qty=100,
        price=550,
    )
    assert res.turnover == Decimal("55000.00")
    assert res.brokerage == Decimal("0.00")
    # STT: 0.10% of 55000 = 55.00
    assert res.stt == Decimal("55.00")
    # NSE Exchange fee: 0.00307% of 55000 = 1.6885 -> 1.69
    assert res.exchange_charges == Decimal("1.69")
    # SEBI fee: 0.00010% of 55000 = 0.055 -> 0.06
    assert res.sebi_charges == Decimal("0.06")
    # GST base: 1.69 + 0.06 = 1.75
    # GST: 18% of 1.75 = 0.315 -> 0.32
    assert res.gst == Decimal("0.32")
    # Stamp duty on SELL: 0
    assert res.stamp_duty == Decimal("0.00")
    # Default profile DP charges = 0
    assert res.dp_charges == Decimal("0.00")
    # Total charges: 55.00 + 1.69 + 0.06 + 0.32 = 57.07
    assert res.total_charges == Decimal("57.07")
    assert res.effective_total == Decimal("54942.93")


def test_flat_brokerage_with_dp_charges():
    # Custom profile: Rs 20 flat brokerage, Rs 15.93 DP charge
    profile = ChargeProfile(
        profile_name="Flat Broker",
        broker_id="DISCOUNT",
        exchange="NSE",
        segment="EQUITY_DELIVERY",
        currency="INR",
        is_active=True,
        is_default=False,
        version=1,
        rounding_mode="ROUND_HALF_UP",
        money_decimal_places=2,
        brokerage_type="FLAT_PER_EXECUTED_ORDER",
        brokerage_rate_pct=Decimal("0"),
        brokerage_flat_per_executed_order=Decimal("20.00"),
        brokerage_order_cap=Decimal("20.00"),
        stt_buy_rate_pct=Decimal("0.10"),
        stt_sell_rate_pct=Decimal("0.10"),
        exchange_transaction_charge_buy_rate_pct=Decimal("0.00307"),
        exchange_transaction_charge_sell_rate_pct=Decimal("0.00307"),
        sebi_turnover_fee_rate_pct=Decimal("0.00010"),
        clearing_charge_buy_rate_pct=Decimal("0"),
        clearing_charge_sell_rate_pct=Decimal("0"),
        gst_rate_pct=Decimal("18.0"),
        stamp_duty_buy_rate_pct=Decimal("0.015"),
        stamp_duty_sell_rate_pct=Decimal("0"),
        dp_charge_on_delivery_sell=Decimal("15.93"),
        dp_charge_scope="PER_SELL_ORDER",
        include_estimated_exit_charges_in_unrealised_pnl=False,
    )

    # SELL: 50 shares @ Rs 1,000 = Turnover Rs 50,000
    res = calculate_delivery_charges(
        side="SELL",
        qty=50,
        price=1000,
        profile=profile,
        apply_dp_charge=True,
    )
    assert res.brokerage == Decimal("20.00")
    # Taxable base = Brokerage (20.00) + Exch (1.54) + SEBI (0.05) = 21.59
    # GST = 18% of 21.59 = 3.8862 -> 3.89
    assert res.gst == Decimal("3.89")
    # DP charges = 15.93
    assert res.dp_charges == Decimal("15.93")
    # Total charges: 20 + 50 (STT) + 1.54 + 0.05 + 3.89 + 15.93 = 91.41
    assert res.total_charges == Decimal("91.41")


def test_percentage_capped_brokerage():
    # 0.05% brokerage capped at Rs 20
    profile = ChargeProfile(
        profile_name="Capped Broker",
        broker_id="DISCOUNT_CAPPED",
        exchange="NSE",
        segment="EQUITY_DELIVERY",
        currency="INR",
        is_active=True,
        is_default=False,
        version=1,
        rounding_mode="ROUND_HALF_UP",
        money_decimal_places=2,
        brokerage_type="MIN_OF_PERCENTAGE_OR_FLAT_CAP",
        brokerage_rate_pct=Decimal("0.05"),
        brokerage_flat_per_executed_order=Decimal("0"),
        brokerage_order_cap=Decimal("20.00"),
        stt_buy_rate_pct=Decimal("0.10"),
        stt_sell_rate_pct=Decimal("0.10"),
        exchange_transaction_charge_buy_rate_pct=Decimal("0.00307"),
        exchange_transaction_charge_sell_rate_pct=Decimal("0.00307"),
        sebi_turnover_fee_rate_pct=Decimal("0.00010"),
        clearing_charge_buy_rate_pct=Decimal("0"),
        clearing_charge_sell_rate_pct=Decimal("0"),
        gst_rate_pct=Decimal("18.0"),
        stamp_duty_buy_rate_pct=Decimal("0.015"),
        stamp_duty_sell_rate_pct=Decimal("0"),
        dp_charge_on_delivery_sell=Decimal("0"),
        dp_charge_scope="PER_SELL_ORDER",
        include_estimated_exit_charges_in_unrealised_pnl=False,
    )

    # 10 shares @ Rs 100 = Rs 1,000 turnover -> 0.05% = Rs 0.50 (< 20 cap)
    res_small = calculate_delivery_charges("BUY", 10, 100, profile=profile)
    assert res_small.brokerage == Decimal("0.50")

    # 1,000 shares @ Rs 500 = Rs 500,000 turnover -> 0.05% = Rs 250 -> capped at Rs 20.00
    res_large = calculate_delivery_charges("BUY", 1000, 500, profile=profile)
    assert res_large.brokerage == Decimal("20.00")


def test_break_even_sell_price_guarantee():
    # Buy 100 shares @ Rs 500
    buy_res = calculate_delivery_charges("BUY", 100, 500)
    be_price = calculate_break_even_sell_price(
        qty=100,
        avg_entry_price=500,
        total_buy_charges=buy_res.total_charges,
    )

    # If we sell 100 shares at be_price:
    sell_res = calculate_delivery_charges("SELL", 100, be_price)
    total_proceeds = sell_res.turnover - sell_res.total_charges
    total_cost = Decimal("50000.00") + buy_res.total_charges
    net_pnl = total_proceeds - total_cost

    # Must be non-negative and within 1 paisa per share (Rs 1.00 for 100 shares) due to currency quantization
    assert net_pnl >= Decimal("0.00")
    assert net_pnl < Decimal("1.00")
