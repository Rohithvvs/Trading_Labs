import { describe, it, expect } from "vitest";
import { conditionStringToFilter, entryConditionsToFilters, filtersToPineIndicator } from "../pineGenerator";
import { parsePineScript, ModalBuilderFilter } from "../pineParser";

describe("pineGenerator", () => {
  describe("conditionStringToFilter", () => {
    it("parses comparison condition Close > SMA 50", () => {
      const filter = conditionStringToFilter("Close > SMA 50");
      expect(filter).not.toBeNull();
      expect(filter?.field).toBe("CLOSE");
      expect(filter?.operator).toBe(">");
      expect(filter?.rightKind).toBe("indicator");
      expect(filter?.indicator).toBe("SMA");
      expect(filter?.indicatorPeriod).toBe("50");
    });

    it("parses literal condition RSI 14 > 55", () => {
      const filter = conditionStringToFilter("RSI 14 > 55");
      expect(filter).not.toBeNull();
      expect(filter?.field).toBe("RSI");
      expect(filter?.period).toBe("14");
      expect(filter?.operator).toBe(">");
      expect(filter?.rightKind).toBe("literal");
      expect(filter?.literal).toBe("55");
    });

    it("parses crossover condition RSI 14 crosses above 50", () => {
      const filter = conditionStringToFilter("RSI 14 crosses above 50");
      expect(filter).not.toBeNull();
      expect(filter?.field).toBe("RSI");
      expect(filter?.period).toBe("14");
      expect(filter?.operator).toBe("cross_above");
      expect(filter?.rightKind).toBe("literal");
      expect(filter?.literal).toBe("50");
    });

    it("parses between condition Close between 100 and 500", () => {
      const filter = conditionStringToFilter("Close between 100 and 500");
      expect(filter).not.toBeNull();
      expect(filter?.field).toBe("CLOSE");
      expect(filter?.operator).toBe("between");
      expect(filter?.low).toBe("100");
      expect(filter?.high).toBe("500");
    });

    it("parses Prior 252 High condition Close >= Prior 252 High", () => {
      const filter = conditionStringToFilter("Close >= Prior 252 High");
      expect(filter).not.toBeNull();
      expect(filter?.field).toBe("CLOSE");
      expect(filter?.operator).toBe(">=");
      expect(filter?.rightKind).toBe("indicator");
      expect(filter?.indicator).toBe("HIGH");
      expect(filter?.indicatorPeriod).toBe("252");
    });

    it("parses benchmark condition NIFTY 500 Close > NIFTY 500 SMA 50", () => {
      const filter = conditionStringToFilter("NIFTY 500 Close > NIFTY 500 SMA 50");
      expect(filter).not.toBeNull();
      expect(filter?.field).toBe("BENCHMARK_CLOSE");
      expect(filter?.isBenchmark).toBe(true);
      expect(filter?.operator).toBe(">");
      expect(filter?.rightKind).toBe("indicator");
      expect(filter?.indicator).toBe("SMA");
      expect(filter?.indicatorPeriod).toBe("50");
    });
  });

  describe("entryConditionsToFilters", () => {
    it("converts array of condition objects and strings", () => {
      const raw = [
        { name: "Close > SMA 50" },
        "RSI 14 > 55",
        { name: "Volume > Average Volume 20" },
      ];
      const filters = entryConditionsToFilters(raw);
      expect(filters.length).toBe(3);
      expect(filters[0].field).toBe("CLOSE");
      expect(filters[1].field).toBe("RSI");
      expect(filters[2].field).toBe("VOLUME");
      expect(filters[2].indicator).toBe("AVG_VOLUME");
    });
  });

  describe("filtersToPineIndicator and round-trip", () => {
    it("generates Pine Script v6 indicator code that parses with parsePineScript", () => {
      const filters: ModalBuilderFilter[] = [
        {
          id: "1",
          field: "CLOSE",
          operator: ">",
          rightKind: "indicator",
          literal: "",
          indicator: "SMA",
          indicatorPeriod: "50",
          low: "",
          high: "",
        },
        {
          id: "2",
          field: "RSI",
          period: "14",
          operator: ">",
          rightKind: "literal",
          literal: "55",
          indicator: "SMA",
          indicatorPeriod: "20",
          low: "",
          high: "",
        },
        {
          id: "3",
          field: "VOLUME",
          operator: ">",
          rightKind: "indicator",
          literal: "",
          indicator: "AVG_VOLUME",
          indicatorPeriod: "20",
          low: "",
          high: "",
        },
      ];

      const code = filtersToPineIndicator({
        name: "My Tested Strategy",
        filters,
        logic: "ALL",
      });

      expect(code).toContain('//@version=6');
      expect(code).toContain('indicator("My Tested Strategy", overlay=false)');
      expect(code).toContain('c1 = close > ta.sma(close, 50)');
      expect(code).toContain('c2 = ta.rsi(close, 14) > 55');
      expect(code).toContain('c3 = volume > ta.sma(volume, 20)');
      expect(code).toContain('scanSignal = c1 and c2 and c3');
      expect(code).toContain('plot(scanSignal ? 1 : 0, "Signal")');

      // Round-trip parse
      const parsed = parsePineScript(code);
      expect(parsed.success).toBe(true);
      expect(parsed.strategyName).toBe("My Tested Strategy");
      expect(parsed.filters.length).toBe(3);
    });

    it("generates benchmark declarations when isBenchmark is true", () => {
      const filters: ModalBuilderFilter[] = [
        {
          id: "1",
          field: "BENCHMARK_CLOSE",
          isBenchmark: true,
          operator: ">",
          rightKind: "indicator",
          literal: "",
          indicator: "SMA",
          indicatorPeriod: "50",
          low: "",
          high: "",
        },
      ];

      const code = filtersToPineIndicator({
        name: "Benchmark Strategy",
        filters,
        logic: "ALL",
      });

      expect(code).toContain('benchmarkSymbol = input.symbol("NSE:CNX500", "Benchmark")');
      expect(code).toContain('request.security(benchmarkSymbol, timeframe.period, close)');
      expect(code).toContain('request.security(benchmarkSymbol, timeframe.period, ta.sma(close, 50))');
    });
  });
});
