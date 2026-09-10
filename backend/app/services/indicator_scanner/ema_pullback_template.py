"""EMA Pullback Swing [SCAN] — indicator-scanner form of the Nifty 750 strategy."""

from __future__ import annotations

EMA_PULLBACK_SCAN_TITLE = "Nifty 750 - EMA Pullback Swing [SCAN]"

EMA_PULLBACK_SCAN_SOURCE = '''//@version=6
indicator("Nifty 750 - EMA Pullback Swing [SCAN]", overlay=false)

emaLen      = input.int(20, "Pullback EMA", minval=1)
dmaLen      = input.int(200, "Trend DMA", minval=1)
rsiLen      = input.int(14, "RSI Length", minval=1)
rsiLow      = input.int(40, "RSI Min")
rsiHigh     = input.int(60, "RSI Max")
volMult     = input.float(1.5, "Volume Multiplier", minval=0.1, step=0.1)
atrLen      = input.int(14, "ATR Length", minval=1)
atrMult     = input.float(2.0, "Stop ATR Multiple", minval=0.1, step=0.1)
rr          = input.float(2.5, "Reward:Risk", minval=0.1, step=0.1)
trendFilter = input.bool(true, "200-DMA Trend Filter")

ema20  = ta.ema(close, emaLen)
dma200 = ta.sma(close, dmaLen)
rsiVal = ta.rsi(close, rsiLen)
atrVal = ta.atr(atrLen)
volAvg = ta.sma(volume, 20)

pullback = low <= ema20 and close > ema20
rsiOK    = rsiVal > rsiLow and rsiVal < rsiHigh
volOK    = volume > volMult * volAvg
trendOK  = not trendFilter or close > dma200

longCond = trendOK and pullback and rsiOK and volOK

longStop = close - atrMult * atrVal
longTP   = close + atrMult * atrVal * rr

plot(longCond ? 1 : 0, "Signal")
plot(close, "Close")
plot(ema20, "20 EMA")
plot(dma200, "200 DMA")
plot(rsiVal, "RSI")
plot(volAvg, "Volume SMA 20")
plot(atrVal, "ATR")
plot(longStop, "Stop")
plot(longTP, "Target")

plotshape(longCond, title="Buy Signal", style=shape.triangleup, location=location.belowbar, color=color.green, size=size.small)
alertcondition(longCond, title="Swing Long", message="EMA Pullback Long")
'''
