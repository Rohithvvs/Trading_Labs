"""NSE cash-equity delivery costs — copied exactly from Trading-main transaction_costs.py."""

from __future__ import annotations


class TransactionCosts:
    def __init__(
        self,
        brokerage_pct=0.0003,
        brokerage_cap=20.0,
        stt_sell_pct=0.001,  # STT on delivery SELL only
        exchange_txn_pct=0.0000345,  # NSE txn charge (approx)
        sebi_pct=0.000001,
        stamp_buy_pct=0.00015,  # stamp duty on BUY only
        gst_pct=0.18,  # on (brokerage + exchange txn)
        dp_charge_flat=15.93,  # per scrip per SELL day (CDSL/NSDL + GST)
    ):
        self.brokerage_pct = brokerage_pct
        self.brokerage_cap = brokerage_cap
        self.stt_sell_pct = stt_sell_pct
        self.exchange_txn_pct = exchange_txn_pct
        self.sebi_pct = sebi_pct
        self.stamp_buy_pct = stamp_buy_pct
        self.gst_pct = gst_pct
        self.dp_charge_flat = dp_charge_flat

    def buy_cost(self, turnover):
        brokerage = min(turnover * self.brokerage_pct, self.brokerage_cap)
        exch = turnover * self.exchange_txn_pct
        sebi = turnover * self.sebi_pct
        stamp = turnover * self.stamp_buy_pct
        gst = (brokerage + exch) * self.gst_pct
        return brokerage + exch + sebi + stamp + gst

    def sell_cost(self, turnover, include_dp=True):
        brokerage = min(turnover * self.brokerage_pct, self.brokerage_cap)
        exch = turnover * self.exchange_txn_pct
        sebi = turnover * self.sebi_pct
        stt = turnover * self.stt_sell_pct
        gst = (brokerage + exch) * self.gst_pct
        dp = self.dp_charge_flat if include_dp else 0.0
        return brokerage + exch + sebi + stt + gst + dp
