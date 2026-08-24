"""Search GLAXO daily series for rule-sets that reproduce the TV report.

Does not change strategy code. Target (1 share, 0% commission):
  trades=241 winners=118 pf=1.126 pnl=701.40 maxW=230.00 maxL=-232.80
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))

from app.services.market_data_ingestion.repository import fetch_equity_history

SYMBOL = "GLAXO-EQ"
START = date(2023, 8, 19)
END = date(2026, 8, 19)
TARGET_N = 241
TARGET_W = 118
TARGET_PNL = 701.40
TARGET_MAXW = 230.00
TARGET_MAXL = -232.80


def prior_max(arr, t, lb):
    if t < lb:
        return None
    return max(arr[t - lb : t])


def prior_min(arr, t, lb):
    if t < lb:
        return None
    return min(arr[t - lb : t])


def summarize(pnls, label, extra=""):
    n = len(pnls)
    if n == 0:
        return
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp = sum(wins)
    gl = abs(sum(losses)) or 1e-12
    wr = 100.0 * len(wins) / n
    pf = gp / gl
    pnl = sum(pnls)
    mx = max(pnls)
    mn = min(pnls)
    score = (
        abs(n - TARGET_N)
        + abs(len(wins) - TARGET_W)
        + min(abs(mx - TARGET_MAXW), abs(mx - 230))
        + min(abs(mn - TARGET_MAXL), abs(mn + 232.8))
        + abs(pnl - TARGET_PNL) / 50.0
    )
    flag = ""
    if abs(n - TARGET_N) <= 15:
        flag = " <<<"
    if abs(n - TARGET_N) <= 5 and abs(mx - TARGET_MAXW) < 1:
        flag = " *** CLOSE"
    print(
        f"{label}: n={n} W={len(wins)} wr={wr:.2f}% pf={pf:.3f} pnl={pnl:.2f} "
        f"maxW={mx:.2f} maxL={mn:.2f} score={score:.1f}{flag} {extra}"
    )


async def main():
    eq = await fetch_equity_history(SYMBOL)
    days = [
        r["trade_date"] if isinstance(r["trade_date"], date) else date.fromisoformat(str(r["trade_date"])[:10])
        for r in eq
    ]
    O = [float(r["open"]) for r in eq]
    H = [float(r["high"]) for r in eq]
    L = [float(r["low"]) for r in eq]
    C = [float(r["close"]) for r in eq]
    V = [float(r.get("volume") or 0) for r in eq]
    idx = [i for i, d in enumerate(days) if START <= d <= END]
    print("window bars", len(idx), days[idx[0]], days[idx[-1]])

    # proximity to 52w high
    print("\n=== days close within X% of prior-252 high ===")
    for pct in (0.0, 0.5, 1.0, 1.25, 1.28, 2.0, 3.0, 5.0, 8.0, 10.0):
        n = 0
        for t in idx:
            ph = prior_max(H, t, 252)
            if ph and C[t] >= ph * (1 - pct / 100.0):
                n += 1
        print(f"  within {pct:5.2f}%: {n}")

    print("\n=== days HIGH within X% of prior-252 high ===")
    for pct in (0.0, 0.5, 1.0, 2.0, 3.0, 5.0):
        n = 0
        for t in idx:
            ph = prior_max(H, t, 252)
            if ph and H[t] >= ph * (1 - pct / 100.0):
                n += 1
        print(f"  within {pct:5.2f}%: {n}")

    # 1-share long: enter when close within band of 52w high, exit on pct stop using LOW (intrabar) or close
    print("\n=== near-52w + % stop (1 share, re-enter next bar) ===")
    for band in (0.0, 1.0, 2.0, 3.0, 5.0, 10.0):
        for stop_pct in (0.8, 1.0, 1.25, 1.28, 1.5, 2.0, 2.5):
            for use_low in (False, True):
                pnls = []
                held = False
                entry = None
                for t in idx:
                    ph = prior_max(H, t, 252)
                    near = ph is not None and C[t] >= ph * (1 - band / 100.0)
                    if held:
                        stop = entry * (1 - stop_pct / 100.0)
                        hit = (L[t] <= stop) if use_low else (C[t] <= stop)
                        if hit:
                            px = stop if use_low else C[t]
                            pnls.append(px - entry)
                            held = False
                        elif not near:
                            pnls.append(C[t] - entry)
                            held = False
                    if not held and near:
                        held = True
                        entry = C[t]
                if held:
                    pnls.append(C[idx[-1]] - entry)
                summarize(
                    pnls,
                    f"band={band}% stop={stop_pct}% {'LOW' if use_low else 'CLOSE'}",
                )

    # Donchian N, long only, 1-bar hold at close, high>=prior
    print("\n=== Donchian high>=priorN 1-bar close-to-close ===")
    for lb in range(2, 21):
        pnls = []
        pending = None
        for t in idx:
            if pending is not None:
                pnls.append(C[t] - pending)
                pending = None
            ph = prior_max(H, t, lb)
            if ph is not None and H[t] >= ph:
                pending = C[t]
        summarize(pnls, f"lb={lb}")

    # close >= prior N, 1-bar
    print("\n=== close>=priorN 1-bar close-to-close ===")
    for lb in range(2, 21):
        pnls = []
        pending = None
        for t in idx:
            if pending is not None:
                pnls.append(C[t] - pending)
                pending = None
            ph = prior_max(H, t, lb)
            if ph is not None and C[t] >= ph:
                pending = C[t]
        summarize(pnls, f"c>=ph lb={lb}")

    # Always long: exit when close < entry*(1-s) or trail from HWM by s, re-enter next day always
    print("\n=== always-in long, trail pct from HWM (close) ===")
    for s in (0.5, 0.8, 1.0, 1.25, 1.28, 1.5, 2.0, 2.5, 3.0):
        pnls = []
        held = False
        entry = hwm = None
        for t in idx:
            if not held:
                held = True
                entry = C[t]
                hwm = C[t]
                continue
            hwm = max(hwm, C[t])
            stop = hwm * (1 - s / 100.0)
            if C[t] < stop:
                pnls.append(C[t] - entry)
                held = False
        if held:
            pnls.append(C[idx[-1]] - entry)
        summarize(pnls, f"always trail {s}% close")

    print("\n=== always-in long, trail pct from HWM (intrabar low fill at stop) ===")
    for s in (0.5, 0.8, 1.0, 1.25, 1.28, 1.5, 2.0, 2.5, 3.0):
        pnls = []
        held = False
        entry = hwm = None
        for t in idx:
            if not held:
                held = True
                entry = C[t]
                hwm = C[t]
                continue
            hwm = max(hwm, H[t])
            stop = hwm * (1 - s / 100.0)
            if L[t] <= stop:
                pnls.append(stop - entry)
                held = False
        if held:
            pnls.append(C[idx[-1]] - entry)
        summarize(pnls, f"always trail {s}% low-fill")

    # Supertrend-like: ATR SMA * mult trail from close, always in long, re-enter next bar
    def sma_atr(t, n=14):
        if t < n:
            return None
        trs = []
        for i in range(t - n + 1, t + 1):
            prev = C[i - 1] if i else C[i]
            trs.append(max(H[i] - L[i], abs(H[i] - prev), abs(L[i] - prev)))
        return sum(trs) / n

    print("\n=== always-in long, ATR*k trail from close (close exit) ===")
    for k in (0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
        pnls = []
        held = False
        entry = tsl = None
        for t in idx:
            atr = sma_atr(t)
            if atr is None:
                continue
            if not held:
                held = True
                entry = C[t]
                tsl = C[t] - k * atr
                continue
            tsl = max(tsl, C[t] - k * atr)
            if C[t] < tsl:
                pnls.append(C[t] - entry)
                held = False
        if held:
            pnls.append(C[idx[-1]] - entry)
        summarize(pnls, f"ATR*{k} close")

    print("\n=== always-in long, ATR*k trail (low fills stop), re-enter next close ===")
    for k in (0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
        pnls = []
        held = False
        entry = tsl = None
        skip = False
        for t in idx:
            atr = sma_atr(t)
            if atr is None:
                continue
            if skip:
                skip = False
                held = True
                entry = C[t]
                tsl = C[t] - k * atr
                continue
            if not held:
                held = True
                entry = C[t]
                tsl = C[t] - k * atr
                continue
            tsl = max(tsl, C[t] - k * atr)
            if L[t] <= tsl:
                pnls.append(tsl - entry)
                held = False
                skip = True  # re-enter next bar
        if held:
            pnls.append(C[idx[-1]] - entry)
        summarize(pnls, f"ATR*{k} low-fill next-reentry")

    # long+short 1-bar when close > open / close < open
    print("\n=== 1-bar long on green, short on red (close-to-next-close) ===")
    pnls = []
    for j, t in enumerate(idx[:-1]):
        nxt = idx[j + 1]
        if C[t] > O[t]:
            pnls.append(C[nxt] - C[t])
        elif C[t] < O[t]:
            pnls.append(C[t] - C[nxt])
    summarize(pnls, "green long / red short 1-bar")

    print("\n=== 1-bar long every bar close-to-next-close ===")
    pnls = [C[idx[j + 1]] - C[idx[j]] for j in range(len(idx) - 1)]
    summarize(pnls, "always 1-bar long")

    # Find any single-bar move of -232.80
    print("\n=== search -232.80 across OHLC combinations ===")
    hits = 0
    for t in idx:
        if t == 0:
            continue
        combos = {
            "C-Cprev": C[t] - C[t - 1],
            "O-Cprev": O[t] - C[t - 1],
            "L-Cprev": L[t] - C[t - 1],
            "C-O": C[t] - O[t],
            "L-O": L[t] - O[t],
            "C-Hprev": C[t] - H[t - 1],
            "L-Hprev": L[t] - H[t - 1],
            "O-Hprev": O[t] - H[t - 1],
        }
        for name, val in combos.items():
            if abs(val - TARGET_MAXL) < 0.051 or abs(val - TARGET_MAXW) < 0.051:
                print(" ", days[t], name, round(val, 2), "O", O[t], "H", H[t], "L", L[t], "C", C[t])
                hits += 1
    print("hits", hits)

    # 52w proximity 1-bar: enter close if within band, pnl = next close - this close
    print("\n=== near 52w, 1-bar next close ===")
    for band in (0, 1, 2, 3, 5, 8, 10, 15, 20, 50, 100):
        pnls = []
        for j, t in enumerate(idx[:-1]):
            ph = prior_max(H, t, 252)
            if ph and C[t] >= ph * (1 - band / 100.0):
                pnls.append(C[idx[j + 1]] - C[t])
        summarize(pnls, f"near{band}% 1-bar")


if __name__ == "__main__":
    asyncio.run(main())
