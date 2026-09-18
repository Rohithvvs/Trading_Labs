"""Published NSE delivery fee breakdown for 52W replay."""

from __future__ import annotations


def buy_cost(turnover: float) -> float:
    if turnover <= 0:
        return 0.0
    brokerage = min(turnover * 0.0003, 20.0)
    exchange = turnover * 0.0000345
    sebi = turnover * 0.000001
    stamp = turnover * 0.00015
    gst = (brokerage + exchange) * 0.18
    return brokerage + exchange + sebi + stamp + gst


def sell_cost(turnover: float) -> float:
    if turnover <= 0:
        return 0.0
    brokerage = min(turnover * 0.0003, 20.0)
    exchange = turnover * 0.0000345
    sebi = turnover * 0.000001
    stt = turnover * 0.001
    gst = (brokerage + exchange) * 0.18
    dp = 15.93
    return brokerage + exchange + sebi + stt + gst + dp


def apply_buy(cash: float, turnover: float) -> float:
    return cash - turnover - buy_cost(turnover)


def apply_sell(cash: float, turnover: float) -> float:
    return cash + turnover - sell_cost(turnover)
