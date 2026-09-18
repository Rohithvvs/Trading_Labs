"""Canonical 52-Week High Breakout [SCAN] template for UI and tests."""

from __future__ import annotations

BREAKOUT_SCAN_TITLE = "52-Week High Breakout [SCAN]"

BREAKOUT_SCAN_SOURCE = '''//@version=6
indicator("52-Week High Breakout [SCAN]", overlay=false)

breakoutLength = input.int(252, "Breakout Lookback", minval=1)
volumeLength = input.int(20, "Volume SMA Length", minval=1)
atrLength = input.int(14, "ATR Length", minval=1)
atrMultiplier = input.float(3.0, "ATR Multiplier", minval=0.1, step=0.1)
marketSmaLength = input.int(50, "Market SMA Length", minval=1)
benchmarkSymbol = input.symbol("NSE:CNX500", "Benchmark")

high252Prior = ta.highest(high, breakoutLength)[1]

volumeSma20 = ta.sma(volume, volumeLength)
volumeCondition = volume > volumeSma20

previousClose = close[1]

trueRange = math.max(
     high - low,
     math.max(
          math.abs(high - previousClose),
          math.abs(low - previousClose)
     )
)

atr14 = ta.sma(trueRange, atrLength)

nifty500Close = request.security(
     benchmarkSymbol,
     timeframe.period,
     close
)

nifty500Sma50 = request.security(
     benchmarkSymbol,
     timeframe.period,
     ta.sma(close, marketSmaLength)
)

marketOk = nifty500Close > nifty500Sma50

breakoutCondition =
     not na(high252Prior) and
     close >= high252Prior

scanSignal =
     marketOk and
     breakoutCondition and
     volumeCondition and
     not na(close) and
     close > 0

plot(scanSignal ? 1 : 0, "52W Breakout Signal")
plot(close, "Close")
plot(high252Prior, "Prior 252 High")
plot(volumeSma20, "Volume SMA 20")
plot(atr14, "Custom ATR 14")
plot(nifty500Close, "NIFTY 500 Close")
plot(nifty500Sma50, "NIFTY 500 SMA 50")

plotshape(
     scanSignal,
     title="52W Breakout",
     style=shape.triangleup,
     location=location.bottom,
     size=size.tiny,
     text="52W"
)

alertcondition(
     scanSignal,
     title="52W Breakout Scan",
     message="52-Week High Breakout detected"
)
'''

SUPPORTED_SYNTAX_HELP = [
    "indicator(title, overlay=...) — header only; overlay is ignored for scans",
    "input.int / input.float / input.bool / input.string / input.symbol",
    "OHLCV: open, high, low, close, volume and series indexing such as close[1]",
    "math.max/min/abs/round/floor/ceil",
    "ta.sma, ta.ema, ta.rma, ta.highest, ta.lowest, ta.atr, ta.rsi, ta.stdev, ta.crossover, ta.crossunder",
    "na(x), nz(x, replacement=0)",
    "request.security(symbol, timeframe.period, close or ta.sma(close, n))",
    "plot, plotshape, alertcondition — become screener columns",
    "Operators: + - * / % comparisons and/or/not ternary ?: ",
]
