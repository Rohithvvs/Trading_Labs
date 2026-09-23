"""Pine-subset v1 scan scripts for the 21 research-lab strategies.

Stateful Darvas box formation cannot be expressed without var/loops. Those
scripts still compile and plot the vectorized building blocks; the scanner
overlays the native Darvas last-bar buy when the indicator title matches.
"""

from __future__ import annotations

from .catalog import LAB_BY_ID, LabStrategy
from ..indicator_scanner.template import BREAKOUT_SCAN_SOURCE

_BENCH = """benchmarkSymbol = input.symbol("NSE:CNX500", "Benchmark")
niftyClose = request.security(benchmarkSymbol, timeframe.period, close)
niftySma50 = ta.sma(niftyClose, 50)
niftySma20 = ta.sma(niftyClose, 20)
niftySma10 = ta.sma(niftyClose, 10)
marketOk50 = niftyClose > niftySma50
marketOk20 = niftyClose > niftySma20
marketOk10 = niftyClose >= niftySma10
niftyMom126 = niftyClose / niftyClose[126] - 1
"""

_RSI_SMA = """chg = close - close[1]
gain = math.max(chg, 0)
loss = math.max(-chg, 0)
avgGain = ta.sma(gain, 14)
avgLoss = ta.sma(loss, 14)
rsiSma = avgLoss == 0 ? 100.0 : 100.0 - 100.0 / (1.0 + avgGain / avgLoss)
"""

_ATR_SMA = """prevClose = close[1]
tr = math.max(high - low, math.max(math.abs(high - prevClose), math.abs(low - prevClose)))
atrSma14 = ta.sma(tr, 14)
"""

_MOM = """mom20 = close / close[20] - 1
mom60 = close / close[60] - 1
mom126 = close / close[126] - 1
mom252 = close / close[252] - 1
"""

_MA = """sma10 = ta.sma(close, 10)
sma20 = ta.sma(close, 20)
sma50 = ta.sma(close, 50)
sma200 = ta.sma(close, 200)
ema9 = ta.ema(close, 9)
ema21 = ta.ema(close, 21)
ema20 = ta.ema(close, 20)
volSma20 = ta.sma(volume, 20)
"""


def _script(title: str, body: str, extra_plots: str = "") -> str:
    extra = extra_plots if extra_plots.endswith("\n") or extra_plots == "" else extra_plots + "\n"
    return (
        f'//@version=6\n'
        f'indicator("{title}", overlay=false)\n\n'
        f"{body.rstrip()}\n\n"
        f'plot(scanSignal ? 1 : 0, "Signal")\n'
        f'plot(close, "Close")\n'
        f"{extra}"
        f'plotshape(scanSignal, title="Buy", style=shape.triangleup, location=location.bottom, size=size.tiny, text="BUY")\n'
        f'alertcondition(scanSignal, title="{title}", message="{title} buy")\n'
    )


def _darvas_body(*, vol_mult: int, market: bool, extra_and: str = "") -> str:
    mf = "marketOk50 and " if market else ""
    extra = f" and {extra_and}" if extra_and else ""
    return f"""volMult = input.float({vol_mult}.0, "Volume Multiplier", minval=0.1, step=0.1)
{_BENCH}{_ATR_SMA}volSma20 = ta.sma(volume, 20)
volOK = volume > volMult * volSma20
high252 = ta.highest(high, 252)
lockHigh = high252[3]
topLocked = high[3] == lockHigh and math.max(high[2], math.max(high[1], high)) < high[3]
scanSignal = {mf}volOK and close > lockHigh{extra}
"""


def _ob_low_chain() -> str:
    lines = ["ob1 = close[1] < open[1] ? low[1] : na"]
    for i in range(2, 16):
        prev = f"ob{i-1}"
        cur = f"ob{i}"
        lines.append(
            f"{cur} = not na({prev}) ? {prev} : (close[{i}] < open[{i}] ? low[{i}] : na)"
        )
    lines.append("obLow = ob15")
    return "\n".join(lines)


def pine_source_for(spec: LabStrategy) -> str:
    sid = spec.strategy_id
    title = spec.scan_title
    if sid == "top_01_momentum":
        return _script(
            title,
            _MA
            + _RSI_SMA
            + "scanSignal = close > sma50 and sma50 > sma200 and rsiSma > 55 and volume > volSma20 and not na(close) and close > 0\n",
            'plot(sma50, "SMA 50")\nplot(sma200, "SMA 200")\nplot(rsiSma, "RSI 14")\nplot(volSma20, "Volume SMA 20")\n',
        )
    if sid == "top_02_12_1_mom":
        return _script(
            title,
            _MA
            + """pSkip = close[21]
pStart = close[252]
mom12_1 = not na(pStart) and pStart > 0 ? (pSkip / pStart - 1.0) * 100.0 : na
scanSignal = not na(mom12_1) and mom12_1 > 0 and volume > volSma20 and not na(close) and close > 0
""",
            'plot(mom12_1, "12-1 Momentum %")\nplot(volSma20, "Volume SMA 20")\n',
        )
    if sid == "top_03_52w_breakout":
        return BREAKOUT_SCAN_SOURCE.replace(
            'indicator("52-Week High Breakout [SCAN]"',
            f'indicator("{title}"',
        )
    if sid == "top_04_52w_atr":
        return _script(
            title,
            _BENCH
            + _ATR_SMA
            + _MA
            + """high252Prior = ta.highest(high, 252)[1]
scanSignal = marketOk50 and not na(high252Prior) and close >= high252Prior and volume > volSma20 and not na(close) and close > 0
""",
            'plot(high252Prior, "Prior 252 High")\nplot(atrSma14, "ATR 14")\nplot(volSma20, "Volume SMA 20")\nplot(niftyClose, "NIFTY 500 Close")\nplot(niftySma50, "NIFTY 500 SMA 50")\n',
        )
    if sid == "top_05_minervini_vcp":
        return _script(
            title,
            _MA
            + """sma150 = ta.sma(close, 150)
sma200Prior = sma200[20]
high52w = ta.highest(high, 252)[1]
low52w = ta.lowest(low, 252)[1]

templateOk = not na(sma200) and not na(sma200Prior) and close > sma150 and close > sma200 and sma150 > sma200 and sma200 > sma200Prior and sma50 > sma150 and sma50 > sma200 and close >= (1.25 * low52w) and close >= (0.75 * high52w)

range20d = ta.highest(high, 20) - ta.lowest(low, 20)
range126d = ta.highest(high, 126) - ta.lowest(low, 126)
vcpContracted = not na(range126d) and range126d > 0 and (range20d / range126d) <= 0.40

pivotHigh = ta.highest(high, 15)[1]
scanSignal = templateOk and vcpContracted and not na(pivotHigh) and close > pivotHigh and volume > volSma20 and not na(close) and close > 0
""",
            'plot(sma50, "SMA 50")\nplot(sma150, "SMA 150")\nplot(sma200, "SMA 200")\nplot(pivotHigh, "Pivot High 15")\nplot(volSma20, "Volume SMA 20")\n',
        )
    if sid == "01_darvas_classic":
        return _script(
            title,
            _darvas_body(vol_mult=2, market=False),
            'plot(lockHigh, "Box Top Candidate")\nplot(volSma20, "Volume SMA 20")\nplot(atrSma14, "ATR SMA 14")\n',
        )
    if sid == "02_darvas_atr5_mf50":
        return _script(
            title,
            _darvas_body(vol_mult=5, market=True),
            'plot(lockHigh, "Box Top Candidate")\nplot(niftyClose, "NIFTY 500 Close")\nplot(niftySma50, "NIFTY 500 SMA 50")\nplot(atrSma14, "ATR SMA 14")\n',
        )
    if sid == "03_super_trend_align":
        return _script(
            title,
            _MA + _darvas_body(vol_mult=5, market=True, extra_and="close > sma50 and sma50 > sma200"),
            'plot(sma50, "SMA 50")\nplot(sma200, "SMA 200")\nplot(niftySma50, "NIFTY 500 SMA 50")\n',
        )
    if sid == "04_rs_darvas":
        return _script(
            title,
            _MOM + _darvas_body(vol_mult=5, market=True, extra_and="mom126 > niftyMom126 and mom126 > 0"),
            'plot(mom126, "Mom 126")\nplot(niftyMom126, "Nifty Mom 126")\n',
        )
    if sid == "05_darvas_breakeven":
        return _script(
            title,
            _darvas_body(vol_mult=5, market=True),
            'plot(lockHigh, "Box Top Candidate")\nplot(atrSma14, "ATR SMA 14")\nplot(niftySma50, "NIFTY 500 SMA 50")\n',
        )
    if sid == "06_mean_reversion":
        return _script(
            title,
            _MA + _RSI_SMA + "scanSignal = not na(sma200) and close > sma200 and rsiSma < 30\nrankScore = 30 - rsiSma\n",
            'plot(rsiSma, "RSI SMA 14")\nplot(sma200, "SMA 200")\nplot(rankScore, "Rank")\n',
        )
    if sid == "07_vol_squeeze":
        return _script(
            title,
            _MA
            + _MOM
            + """std20 = ta.stdev(close, 20)
bbUpper = sma20 + 2 * std20
bbLower = sma20 - 2 * std20
bbWidth = (bbUpper - bbLower) / sma20
prevWidth = bbWidth[1]
scanSignal = prevWidth < 0.10 and close > bbUpper and volume > 3 * volSma20
""",
            'plot(bbUpper, "BB Upper")\nplot(bbWidth, "BB Width")\nplot(volSma20, "Volume SMA 20")\nplot(mom60, "Mom 60")\n',
        )
    if sid == "08_golden_cross_20_50":
        return _script(
            title,
            _MA + _MOM + "scanSignal = ta.crossover(sma20, sma50)\n",
            'plot(sma20, "SMA 20")\nplot(sma50, "SMA 50")\nplot(mom60, "Mom 60")\n',
        )
    if sid == "09_52w_breakout":
        return BREAKOUT_SCAN_SOURCE.replace(
            'indicator("52-Week High Breakout [SCAN]"',
            f'indicator("{title}"',
        )
    if sid == "10_ema_9_21":
        return _script(
            title,
            _BENCH + _MA + _ATR_SMA + _MOM + "scanSignal = marketOk50 and ta.crossover(ema9, ema21)\n",
            'plot(ema9, "EMA 9")\nplot(ema21, "EMA 21")\nplot(niftySma50, "NIFTY 500 SMA 50")\nplot(atrSma14, "ATR SMA 14")\n',
        )
    if sid == "11_refined_mean_reversion":
        return _script(
            title,
            _MA
            + _RSI_SMA
            + "scanSignal = rsiSma[1] > 30 and rsiSma < 30 and sma50 > sma200 and close > sma200\nrankScore = 30 - rsiSma\n",
            'plot(rsiSma, "RSI SMA 14")\nplot(sma50, "SMA 50")\nplot(sma200, "SMA 200")\nplot(rankScore, "Rank")\n',
        )
    if sid == "12_golden_cross_50_200":
        return _script(
            title,
            _MA + _MOM + "scanSignal = ta.crossover(sma50, sma200)\n",
            'plot(sma50, "SMA 50")\nplot(sma200, "SMA 200")\nplot(mom252, "Mom 252")\n',
        )
    if sid == "13_trend_pullback":
        return _script(
            title,
            _MA + _MOM + "scanSignal = close > sma200 and close[1] <= sma50[1] and close > sma50\n",
            'plot(sma50, "SMA 50")\nplot(sma200, "SMA 200")\nplot(mom252, "Mom 252")\n',
        )
    if sid == "14_bh_top_momentum":
        return _script(
            title,
            _MOM + "scanSignal = mom252 > 0.50\n",
            'plot(mom252, "First-Year Return")\n',
        )
    if sid == "15_mrs_breakout":
        return _script(
            title,
            _MA
            + _BENCH
            + """baseHigh = ta.highest(high[1], 15)
baseLow = ta.lowest(low[1], 15)
baseMedian = (baseHigh + baseLow) / 2
baseWidth = (baseHigh - baseLow) / baseMedian * 100
niftyRet15 = niftyClose / niftyClose[15] - 1
volOK = volume >= 1.5 * volSma20
breakout = close > baseHigh
quietMarket = niftyRet15 <= 0.02
scanSignal = not na(baseHigh) and quietMarket and baseWidth <= 10 and breakout and volOK
""",
            'plot(baseHigh, "Base High")\nplot(baseLow, "Base Low")\nplot(baseWidth, "Base Width %")\nplot(ema20, "EMA 20")\n',
        )
    if sid == "16_order_block":
        return _script(
            title,
            _BENCH
            + _MA
            + _MOM
            + _ob_low_chain()
            + "\nprior20High = ta.highest(high[1], 20)\n"
            + "scanSignal = marketOk50 and close > sma50 and close > prior20High and not na(obLow)\n",
            'plot(prior20High, "Prior 20 High")\nplot(obLow, "OB Low")\nplot(sma50, "SMA 50")\nplot(mom60, "Mom 60")\n',
        )
    if sid == "17_long_term_mom":
        return _script(
            title,
            _MOM + "scanSignal = mom252 > 0.50\n",
            'plot(mom252, "Mom 252")\n',
        )
    if sid == "18_fast_mom":
        return _script(
            title,
            _MA + _MOM + "scanSignal = close > sma20\n",
            'plot(sma20, "SMA 20")\nplot(mom60, "Mom 60")\n',
        )
    if sid == "19_low_dd_mom":
        return _script(
            title,
            _BENCH + _MA + _MOM + "scanSignal = marketOk20 and close > sma20\n",
            'plot(sma20, "SMA 20")\nplot(mom60, "Mom 60")\nplot(niftySma20, "NIFTY 500 SMA 20")\n',
        )
    if sid == "20_ultra_yield_mom":
        return _script(
            title,
            _BENCH
            + _MA
            + _MOM
            + "rankScore = mom20 + mom60\nscanSignal = marketOk10 and close > sma20 and mom20 > 0 and mom60 > 0\n",
            'plot(sma20, "SMA 20")\nplot(rankScore, "Mom 20+60")\nplot(niftySma10, "NIFTY 500 SMA 10")\n',
        )
    if sid == "21_sma_10_50":
        return _script(
            title,
            _MA + _MOM + "scanSignal = sma10 > sma50\n",
            'plot(sma10, "SMA 10")\nplot(sma50, "SMA 50")\nplot(mom60, "Mom 60")\n',
        )
    raise KeyError(sid)


def all_pine_sources() -> dict[str, str]:
    return {item.strategy_id: pine_source_for(item) for item in LAB_BY_ID.values()}
