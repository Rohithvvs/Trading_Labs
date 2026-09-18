"""Baseline reporting helpers copied from Trading-main run_all_baseline.py."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from .catalog import INITIAL_CAPITAL
from .signals_types import MarketData

W_WIN_RATE = 0.20
W_PROFIT_FACTOR = 0.20
W_RISK = 0.20
W_AVG_TRADE = 0.15
W_CALMAR = 0.10
BASE_CREDIT = 15.0
CAGR_PENALTY_MULT = 1.5


def _pf(wins: pd.Series, losses: pd.Series) -> float:
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = abs(float(losses.sum())) if len(losses) else 0.0
    if gl <= 0:
        return np.inf if gp > 0 else 0.0
    return gp / gl


def grade_of(score: float) -> Tuple[str, str]:
    if score >= 80:
        return "A", "Strong"
    if score >= 70:
        return "B", "Good"
    if score >= 60:
        return "C", "Average"
    if score >= 50:
        return "D", "Below average"
    return "F", "Poor as a standalone portfolio"


def strategy_score(
    win_rate: float,
    profit_factor: float,
    mdd_pct: float,
    avg_trade: float,
    calmar: float,
    cagr: float,
    bench_cagr: float,
) -> Tuple[float, dict]:
    wr_s = float(np.clip(win_rate, 0.0, 100.0))
    if not np.isfinite(profit_factor):
        pf_s = 100.0 if profit_factor == np.inf else 0.0
    else:
        pf_s = float(np.clip(profit_factor / 3.0 * 100.0, 0.0, 100.0))
    risk_s = float(np.clip(100.0 - 4.0 * abs(mdd_pct), 0.0, 100.0))
    avg_s = float(np.clip(30.0 + 10.875 * avg_trade, 0.0, 100.0))
    calmar_s = float(np.clip(calmar * 200.0, 0.0, 100.0))
    penalty = 0.0
    if np.isfinite(bench_cagr) and bench_cagr > cagr:
        penalty = -CAGR_PENALTY_MULT * (bench_cagr - cagr)
    total = (
        W_WIN_RATE * wr_s
        + W_PROFIT_FACTOR * pf_s
        + W_RISK * risk_s
        + W_AVG_TRADE * avg_s
        + W_CALMAR * calmar_s
        + BASE_CREDIT
        + penalty
    )
    total = float(np.clip(total, 0.0, 100.0))
    parts = {
        "win_rate_score": wr_s,
        "profit_factor_score": pf_s,
        "risk_score": risk_s,
        "avg_trade_score": avg_s,
        "calmar_score": calmar_s,
        "base_credit": BASE_CREDIT,
        "cagr_penalty": penalty,
    }
    return total, parts


def summarize(md: MarketData, trades_df: pd.DataFrame, equity_df: pd.DataFrame) -> dict:
    closed = trades_df[trades_df["status"] == "CLOSED"] if not trades_df.empty else trades_df
    n_closed = len(closed)
    wins = closed[closed["return_pct"] > 0]["return_pct"] if n_closed else pd.Series(dtype=float)
    losses = closed[closed["return_pct"] <= 0]["return_pct"] if n_closed else pd.Series(dtype=float)

    eq = equity_df["equity"]
    peak = eq.cummax()
    dd = eq / peak - 1.0
    max_dd = float(dd.min()) if len(dd) else 0.0
    final_eq = float(eq.iloc[-1]) if len(eq) else INITIAL_CAPITAL
    years = (eq.index[-1] - eq.index[0]).days / 365.25 if len(eq) > 1 else 0.0
    cagr = (final_eq / INITIAL_CAPITAL) ** (1.0 / years) - 1.0 if years > 0 and final_eq > 0 else 0.0

    bench = md.bench.reindex(eq.index).dropna()
    if len(bench) > 1:
        b_years = (bench.index[-1] - bench.index[0]).days / 365.25
        bench_cagr = (float(bench.iloc[-1]) / float(bench.iloc[0])) ** (1.0 / b_years) - 1.0 if b_years > 0 else np.nan
        bench_dd = float((bench / bench.cummax() - 1.0).min())
    else:
        bench_cagr = np.nan
        bench_dd = np.nan

    win_rate = 100.0 * len(wins) / n_closed if n_closed else 0.0
    avg_ret = float(closed["return_pct"].mean()) if n_closed else 0.0
    pf = _pf(wins, losses)
    calmar = (cagr / abs(max_dd)) if max_dd < 0 else (np.inf if cagr > 0 else 0.0)
    score, parts = strategy_score(win_rate, pf, max_dd * 100.0, avg_ret, calmar if np.isfinite(calmar) else 0.0, cagr, bench_cagr)
    grade, label = grade_of(score)
    return {
        "trades": n_closed,
        "win_rate": win_rate,
        "profit_factor": pf,
        "avg_trade": avg_ret,
        "cagr": cagr,
        "total_return": final_eq / INITIAL_CAPITAL - 1.0,
        "max_dd": max_dd,
        "calmar": calmar,
        "final_equity": final_eq,
        "bench_cagr": bench_cagr,
        "bench_dd": bench_dd,
        "score": score,
        "grade": grade,
        "grade_label": label,
        "score_parts": parts,
    }
