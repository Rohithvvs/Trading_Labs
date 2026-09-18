import { describe, expect, it } from "vitest";
import { parsePineScript, DEFAULT_PINE_TEMPLATE } from "../pineParser";

describe("Pine Script Parser - Semantic Role Classification & Data-Flow Isolation", () => {
  // Test 1 — ATR must NOT become entry filter
  it("Test 1: ATR and Trailing Stop are classified as Risk Management/Exit and NEVER as entry filters", () => {
    const code = `//@version=6
strategy("ATR Exit Test")

trueRange = math.max(high - low, math.max(math.abs(high - close[1]), math.abs(low - close[1])))
atr14 = ta.sma(trueRange, 14)
trailingStop = close - 3 * atr14

if close < trailingStop
    strategy.close("Long")
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters).toEqual([]);
    expect(res.detectedFiltersCount).toBe(0);

    expect(res.riskRules && res.riskRules.length).toBeGreaterThanOrEqual(1);
    const risk = res.riskRules![0];
    expect(risk.type).toBe("ATR_TRAILING_STOP");
    expect(risk.atrLength).toBe(14);
    expect(risk.atrMethod).toBe("SMA_TR");
    expect(risk.multiplier).toBe(3);

    expect(res.exitConditions && res.exitConditions.length).toBeGreaterThanOrEqual(1);
    expect(res.exitConditions![0].action).toBe("strategy.close");
    expect(res.exitConditions![0].conditionText).toBe("Close < Trailing Stop");
  });

  // Test 2 — RSI entry filter
  it("Test 2: RSI condition used to guard strategy.entry is classified as ENTRY_FILTER", () => {
    const code = `//@version=6
strategy("RSI Entry Test")

rsi14 = ta.rsi(close, 14)

if rsi14 > 55
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.filters[0].field).toBe("RSI");
    expect(res.filters[0].period).toBe("14");
    expect(res.filters[0].operator).toBe(">");
    expect(res.filters[0].literal).toBe("55");
    expect(res.filters[0].role).toBe("ENTRY_FILTER");
  });

  // Test 3 — RSI calculated but unused
  it("Test 3: Unused calculated indicators are NOT converted into filters", () => {
    const code = `//@version=6
strategy("Unused RSI Test")

rsi14 = ta.rsi(close, 14)
sma50 = ta.sma(close, 50)

if close > sma50
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.filters[0].field).toBe("CLOSE");
    expect(res.filters[0].indicator).toBe("SMA");
    expect(res.filters[0].indicatorPeriod).toBe("50");

    const hasRsiFilter = res.filters.some((f) => f.field === "RSI" || f.indicator === "RSI");
    expect(hasRsiFilter).toBe(false);
  });

  // Test 4 — Variable resolution
  it("Test 4: Recursively resolves variable aliases to atomic indicators", () => {
    const code = `//@version=6
strategy("Alias Test")

sma50 = ta.sma(close, 50)
priceFilter = close > sma50
longCondition = priceFilter

if longCondition
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.filters[0].field).toBe("CLOSE");
    expect(res.filters[0].operator).toBe(">");
    expect(res.filters[0].indicator).toBe("SMA");
    expect(res.filters[0].indicatorPeriod).toBe("50");
  });

  // Test 5 — AND
  it("Test 5: AND expressions produce executionLogic = ALL and multiple filters", () => {
    const code = `//@version=6
strategy("AND Test")

sma50 = ta.sma(close, 50)
rsi14 = ta.rsi(close, 14)
volumeSma20 = ta.sma(volume, 20)

longCondition =
    close > sma50 and
    rsi14 > 55 and
    volume > volumeSma20

if longCondition
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.logic).toBe("ALL");
    expect(res.filters.length).toBe(3);
    expect(res.filters[0].field).toBe("CLOSE");
    expect(res.filters[1].field).toBe("RSI");
    expect(res.filters[2].field).toBe("VOLUME");
  });

  // Test 6 — OR
  it("Test 6: OR expressions produce executionLogic = ANY and do not flatten falsely", () => {
    const code = `//@version=6
strategy("OR Test")

sma50 = ta.sma(close, 50)
rsi14 = ta.rsi(close, 14)

longCondition =
    close > sma50 or
    rsi14 > 70

if longCondition
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.logic).toBe("ANY");
    expect(res.filters.length).toBe(2);
  });

  // Test 7 — 52W previous high
  it("Test 7: 52-Week High Breakout with [1] offset preserves >= operator and 252 period", () => {
    const code = `//@version=6
strategy("52W High Breakout")

high252 = ta.highest(high, 252)
previous52WeekHigh = high252[1]

breakoutCondition = close >= previous52WeekHigh

if breakoutCondition
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.filters[0].field).toBe("CLOSE");
    expect(res.filters[0].operator).toBe(">=");
    expect(res.filters[0].indicator).toBe("HIGH");
    expect(res.filters[0].indicatorPeriod).toBe("252");
  });

  // Test 8 — Volume
  it("Test 8: Volume with 20-session SMA produces strict '>' comparison", () => {
    const code = `//@version=6
strategy("Volume Test")

volumeSma20 = ta.sma(volume, 20)
volumeCondition = volume > volumeSma20

if volumeCondition
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.filters[0].field).toBe("VOLUME");
    expect(res.filters[0].operator).toBe(">");
    expect(res.filters[0].indicator).toBe("AVG_VOLUME");
    expect(res.filters[0].indicatorPeriod).toBe("20");
  });

  // Test 9 — Benchmark
  it("Test 9: request.security benchmark market filter is recognized as BENCHMARK_FILTER", () => {
    const code = `//@version=6
strategy("Benchmark Gate Test")

benchmarkClose = request.security("NSE:NIFTY500", timeframe.period, close)
benchmarkSma50 = request.security("NSE:NIFTY500", timeframe.period, ta.sma(close, 50))

marketOk = benchmarkClose > benchmarkSma50

if marketOk
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.benchmarkFilter).toBeTruthy();
    expect(res.benchmarkFilter?.benchmarkSymbol).toBe("NIFTY 500");
    expect(res.benchmarkFilter?.role).toBe("BENCHMARK_FILTER");
    expect(res.filters.length).toBe(1);
    expect(res.filters[0].isBenchmark).toBe(true);
  });

  // Test 10 — Market filter must NOT become exit
  it("Test 10: Market filter in entry condition does NOT generate an exit rule", () => {
    const code = `//@version=6
strategy("Market Entry Gate Only")

niftyClose = request.security("NSE:NIFTY500", timeframe.period, close)
niftySma50 = request.security("NSE:NIFTY500", timeframe.period, ta.sma(close, 50))
marketOk = niftyClose > niftySma50

if marketOk
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.exitConditions).toEqual([]);
  });

  // Test 11 — Trailing stop ratchet
  it("Test 11: Trailing stop ratcheting on Highest Close is correctly recognized", () => {
    const code = `//@version=6
strategy("Ratchet Stop Test")

trueRange = math.max(high - low, math.max(math.abs(high - close[1]), math.abs(low - close[1])))
atr14 = ta.sma(trueRange, 14)

var float highWaterMark = na
var float trailingStop = na

if strategy.position_size > 0
    if close > highWaterMark or na(highWaterMark)
        highWaterMark := close
    trailingStop := math.max(nz(trailingStop, close - 3 * atr14), close - 3 * atr14)

if close < trailingStop
    strategy.close("Long")
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.riskRules?.length).toBeGreaterThanOrEqual(1);
    const risk = res.riskRules![0];
    expect(risk.hwmSource).toBe("CLOSE");
    expect(risk.multiplier).toBe(3);
    expect(risk.atrLength).toBe(14);
    expect(risk.ratchet).toBe(true);
    expect(res.exitConditions?.[0]?.conditionText).toBe("Close < Trailing Stop");
  });

  // Test 12 — Momentum ranking
  it("Test 12: Momentum ranking formula (close / close[60] - 1) is classified as RANKING, not entry filter", () => {
    const code = `//@version=6
strategy("Ranking Test")

sma50 = ta.sma(close, 50)
momentum60 = close / close[60] - 1

if close > sma50
    strategy.entry("Long", strategy.long)
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.filters[0].field).toBe("CLOSE");
    expect(res.filters[0].indicator).toBe("SMA");

    expect(res.rankingRule).toBeTruthy();
    expect(res.rankingRule?.field).toBe("MOMENTUM");
    expect(res.rankingRule?.period).toBe(60);
    expect(res.rankingRule?.direction).toBe("desc");

    const hasMomentumFilter = res.filters.some((f) => f.field.includes("MOMENTUM") || f.literal.includes("60"));
    expect(hasMomentumFilter).toBe(false);
  });

  // Section 39 Specific Regression Tests:
  // Test A: not na(high252Prior) and close >= high252Prior -> 1 ENTRY_FILTER
  it("Test A: 'not na(high252Prior) and close >= high252Prior' produces exactly 1 ENTRY_FILTER", () => {
    const code = `//@version=6
strategy("Test A")
high252 = ta.highest(high, 252)
high252Prior = high252[1]
breakoutCondition = not na(high252Prior) and close >= high252Prior

if breakoutCondition
    strategy.entry("Long", strategy.long)
`;
    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.detectedFiltersCount).toBe(1);
    expect(res.filters[0].field).toBe("CLOSE");
    expect(res.filters[0].operator).toBe(">=");
    expect(res.filters[0].indicator).toBe("HIGH");
    expect(res.filters[0].indicatorPeriod).toBe("252");
    expect(res.warnings).toEqual([]);
  });

  // Test B: not na(close) and close > 0 -> 0 ENTRY_FILTERS
  it("Test B: 'not na(close) and close > 0' produces 0 ENTRY_FILTERS", () => {
    const code = `//@version=6
strategy("Test B")
longCondition = not na(close) and close > 0

if longCondition
    strategy.entry("Long", strategy.long)
`;
    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(0);
    expect(res.detectedFiltersCount).toBe(0);
    expect(res.parsedStrategy?.validityGuards.length).toBe(2);
  });

  // Test C: not na(atr14) and close < trailingStop inside strategy.close -> 1 EXIT_CONDITION, 0 entry filters
  it("Test C: 'not na(atr14) and close < trailingStop' inside close() produces 1 EXIT_CONDITION and 0 entry filters", () => {
    const code = `//@version=6
strategy("Test C")
trueRange = math.max(high - low, math.max(math.abs(high - close[1]), math.abs(low - close[1])))
atr14 = ta.sma(trueRange, 14)
trailingStop = close - 3 * atr14

if not na(atr14) and close < trailingStop
    strategy.close("Long")
`;
    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(0);
    expect(res.detectedFiltersCount).toBe(0);
    expect(res.exitConditions?.length).toBe(1);
    expect(res.exitConditions![0].conditionText).toBe("Close < Trailing Stop");
  });

  // Test D: strategy.position_size > 0 -> POSITION_STATE, never Builder filter
  it("Test D: strategy.position_size conditions are classified as POSITION_STATE and never Builder filters", () => {
    const code = `//@version=6
strategy("Test D")
longCondition = close > ta.sma(close, 50) and strategy.position_size == 0

if longCondition
    strategy.entry("Long", strategy.long)
`;
    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.filters[0].field).toBe("CLOSE");
    expect(res.filters[0].indicator).toBe("SMA");
    expect(res.parsedStrategy?.positionGuards.length).toBe(1);
    expect(res.warnings).toEqual([]);
  });

  // Test E: not soldThisBar -> ORDER_CONTROL, never Builder filter
  it("Test E: 'not soldThisBar' is classified as ORDER_CONTROL and never a Builder filter", () => {
    const code = `//@version=6
strategy("Test E")
var bool soldThisBar = false
longCondition = close > ta.sma(close, 50) and not soldThisBar

if longCondition
    strategy.entry("Long", strategy.long)
`;
    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(1);
    expect(res.parsedStrategy?.orderControlGuards.length).toBe(1);
    expect(res.warnings).toEqual([]);
  });

  // Test F: bar_index > strategy.opentrades.entry_bar_index(0) -> ENTRY_BAR_PROTECTION
  it("Test F: 'bar_index > strategy.opentrades.entry_bar_index(0)' is classified as ENTRY_BAR_PROTECTION and not in Exit condition string", () => {
    const code = `//@version=6
strategy("Test F")
if strategy.position_size > 0
    if bar_index > strategy.opentrades.entry_bar_index(0)
        if close < trailingStop
            strategy.close("Long")
`;
    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.exitConditions?.length).toBe(1);
    expect(res.exitConditions![0].conditionText).toBe("Close < Trailing Stop");
    // Verify it didn't concatenate the bar_index expression into conditionText
    expect(res.exitConditions![0].conditionText).not.toContain("bar_index");
    expect(res.exitConditions![0].conditionText).not.toContain("strategy.position_size");
  });

  // Test G: Full Realistic 52W Pine Script with comments, decorators, and runtime guards
  it("Test G: Full Realistic 52W Pine Script produces EXACTLY 3 entry filters, no warnings, clean description", () => {
    const code = DEFAULT_PINE_TEMPLATE;

    const res = parsePineScript(code, { debug: true });
    expect(res.success).toBe(true);
    expect(res.strategyName).toBe("52-Week High Breakout");
    expect(res.positionSide).toBe("LONG");
    expect(res.logic).toBe("ALL");

    // CRITICAL: Exactly 3 entry filters, NOT 8!
    expect(res.filters.length).toBe(3);
    expect(res.detectedFiltersCount).toBe(3);

    // Description must NOT contain '==='
    expect(res.description).not.toContain("===");
    expect(res.description).not.toContain("---");

    // 1. Benchmark: NIFTY 500 Close > NIFTY 500 SMA 50
    expect(res.filters[0].isBenchmark).toBe(true);
    expect(res.filters[0].benchmarkSymbol).toBe("NIFTY 500");

    // 2. 52W Breakout: Close >= Previous 252-Session High
    expect(res.filters[1].field).toBe("CLOSE");
    expect(res.filters[1].operator).toBe(">=");
    expect(res.filters[1].indicator).toBe("HIGH");
    expect(res.filters[1].indicatorPeriod).toBe("252");

    // 3. Volume: Volume > Average Volume 20
    expect(res.filters[2].field).toBe("VOLUME");
    expect(res.filters[2].operator).toBe(">");
    expect(res.filters[2].indicator).toBe("AVG_VOLUME");
    expect(res.filters[2].indicatorPeriod).toBe("20");

    // Ranking: Momentum 60
    expect(res.rankingRule).toBeTruthy();
    expect(res.rankingRule?.period).toBe(60);

    // Risk Management
    expect(res.riskRules?.length).toBeGreaterThanOrEqual(1);
    const risk = res.riskRules![0];
    expect(risk.atrMethod).toBe("SMA_TR");
    expect(risk.atrLength).toBe(14);
    expect(risk.multiplier).toBe(3);
    expect(risk.hwmSource).toBe("CLOSE");
    expect(risk.ratchet).toBe(true);

    // Exit Condition: Must say "Close < Trailing Stop" cleanly
    expect(res.exitConditions?.length).toBeGreaterThanOrEqual(1);
    expect(res.exitConditions![0].conditionText).toBe("Close < Trailing Stop");

    // Zero false warnings
    expect(res.warnings).toEqual([]);
    expect(res.unsupportedCount).toBe(0);

    // Forbidden variable names must NOT be in filters
    const forbiddenNames = ["ATR", "TRUERANGE", "TRAILINGSTOP", "HIGHWATERMARK", "MOMENTUM60", "SOLDTHISBAR", "CLOSE>0", "NOTNA"];
    for (const filter of res.filters) {
      const fieldUpper = filter.field.toUpperCase();
      const indUpper = filter.indicator.toUpperCase();
      for (const forbidden of forbiddenNames) {
        expect(fieldUpper).not.toContain(forbidden);
        expect(indUpper).not.toContain(forbidden);
      }
    }
  });

  it("resolves input.int lookbacks so CLOSE >= HIGH 252 and VOLUME > AVG_VOLUME 20, not HIGH null / AVG 50", () => {
    const code = `//@version=6
strategy("52-Week High Breakout - Trading Labs", overlay=true, pyramiding=0, process_orders_on_close=true, initial_capital=100000)

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
trueRange = math.max(high - low, math.max(math.abs(high - previousClose), math.abs(low - previousClose)))
customAtr14 = ta.sma(trueRange, atrLength)

benchmarkClose = request.security(benchmarkSymbol, timeframe.period, close, gaps=barmerge.gaps_off, lookahead=barmerge.lookahead_off)
benchmarkSma50 = request.security(benchmarkSymbol, timeframe.period, ta.sma(close, marketSmaLength), gaps=barmerge.gaps_off, lookahead=barmerge.lookahead_off)
marketOk = benchmarkClose > benchmarkSma50

breakoutCondition = not na(high252Prior) and close >= high252Prior
longCondition = marketOk and breakoutCondition and volumeCondition and not na(close) and close > 0

var float highWaterMark = na
var float trailingStop = na
var int entryBarIndex = na
var bool soldThisBar = false
soldThisBar := false

if strategy.position_size > 0
    if bar_index > entryBarIndex
        if close > highWaterMark
            highWaterMark := close
        if not na(trailingStop) and close < trailingStop
            strategy.close("Long", comment="atr_trail")
            soldThisBar := true

if longCondition and strategy.position_size == 0 and not soldThisBar
    strategy.entry("Long", strategy.long, comment="52W Breakout")
    entryBarIndex := bar_index
    highWaterMark := close
    trailingStop := close - atrMultiplier * customAtr14
`;

    const res = parsePineScript(code, { debug: true });
    expect(res.success).toBe(true);
    expect(res.filters.length).toBe(3);

    const high = res.filters.find((f) => f.indicator === "HIGH");
    expect(high).toBeTruthy();
    expect(high!.field).toBe("CLOSE");
    expect(high!.operator).toBe(">=");
    expect(high!.indicatorPeriod).toBe("252");
    expect(high!.indicatorPeriod).not.toBe("null");

    const vol = res.filters.find((f) => f.field === "VOLUME");
    expect(vol).toBeTruthy();
    expect(vol!.indicator).toBe("AVG_VOLUME");
    expect(vol!.indicatorPeriod).toBe("20");
    expect(vol!.operator).toBe(">");

    const bench = res.filters.find((f) => f.isBenchmark);
    expect(bench).toBeTruthy();
    expect(bench!.benchmarkSymbol).toBe("NIFTY 500");
    expect(bench!.indicator).toBe("SMA");
    expect(bench!.indicatorPeriod).toBe("50");

    const highTrace = res.debugTrace?.find((d) => d.expression.includes("close >= high252Prior"));
    expect(highTrace?.resolved).toContain("HIGH 252");
    expect(highTrace?.resolved).not.toMatch(/HIGH null/i);

    const volTrace = res.debugTrace?.find((d) => d.expression.includes("volume > volumeSma20"));
    expect(volTrace?.resolved).toContain("AVG_VOLUME 20");
    expect(volTrace?.resolved).not.toContain("AVG_VOLUME 50");
  });

  it("imports a TradingView Pine Screener indicator() via scanSignal with input.int periods", () => {
    const code = `//@version=6
indicator("52-Week High Breakout [SCAN]", overlay=false)

breakoutLength = input.int(252, "Breakout Lookback", minval=1)
volumeLength = input.int(20, "Volume SMA Length", minval=1)
marketSmaLength = input.int(50, "Market SMA Length", minval=1)
benchmarkSymbol = input.symbol("NSE:CNX500", "Benchmark")

high252Prior = ta.highest(high, breakoutLength)[1]
volumeSma20 = ta.sma(volume, volumeLength)
volumeCondition = volume > volumeSma20

nifty500Close = request.security(benchmarkSymbol, timeframe.period, close)
nifty500Sma50 = request.security(benchmarkSymbol, timeframe.period, ta.sma(close, marketSmaLength))
marketOk = nifty500Close > nifty500Sma50

breakoutCondition = not na(high252Prior) and close >= high252Prior
scanSignal = marketOk and breakoutCondition and volumeCondition and not na(close) and close > 0

plot(scanSignal ? 1 : 0, "52W Breakout Signal")
plotshape(scanSignal, title="52W Breakout", style=shape.triangleup, location=location.bottom, size=size.tiny, text="52W")
alertcondition(scanSignal, title="52W Breakout Scan", message="52-Week High Breakout detected")
`;

    const res = parsePineScript(code);
    expect(res.success).toBe(true);
    expect(res.strategyName).toBe("52-Week High Breakout [SCAN]");
    expect(res.filters.length).toBe(3);
    expect(res.filters.find((f) => f.indicator === "HIGH")?.indicatorPeriod).toBe("252");
    expect(res.filters.find((f) => f.field === "VOLUME")?.indicatorPeriod).toBe("20");
    expect(res.filters.find((f) => f.isBenchmark)?.benchmarkSymbol).toBe("NIFTY 500");
  });
});
