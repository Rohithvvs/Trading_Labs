import type { ModalBuilderFilter } from "./pineParser";

/** Map human/indicator name to standard field identifier */
function normalizeField(raw: string): { field: string; period?: string; isBenchmark?: boolean } {
  const text = (raw || "").trim();
  if (/^nifty\s*(500)?\s*close/i.test(text) || /benchmark\s*close/i.test(text)) {
    return { field: "BENCHMARK_CLOSE", isBenchmark: true };
  }
  const benchIndMatch = text.match(/^(?:nifty\s*(?:500)?|benchmark)\s+(SMA|EMA|WMA|RSI|ATR|CLOSE)\s*(\d+)?/i);
  if (benchIndMatch) {
    const indName = benchIndMatch[1].toUpperCase();
    const period = benchIndMatch[2] || (indName === "SMA" ? "50" : "20");
    return { field: indName, period, isBenchmark: true };
  }
  if (/^close(\[1\])?$/i.test(text) || text.toLowerCase() === "price") {
    return { field: "CLOSE" };
  }
  if (/^prev(ious)?\s*close/i.test(text)) {
    return { field: "PREV_CLOSE" };
  }
  if (/^open$/i.test(text)) return { field: "OPEN" };
  if (/^high$/i.test(text)) return { field: "HIGH" };
  if (/^low$/i.test(text)) return { field: "LOW" };
  if (/^volume$/i.test(text)) return { field: "VOLUME" };
  if (/^prior\s*(\d+)?\s*high/i.test(text)) {
    const match = text.match(/prior\s*(\d+)\s*high/i);
    return { field: "HIGH", period: match ? match[1] : "252" };
  }
  if (/^prior\s*(\d+)?\s*low/i.test(text)) {
    const match = text.match(/prior\s*(\d+)\s*low/i);
    return { field: "LOW", period: match ? match[1] : "252" };
  }
  if (/^average\s*volume\s*(\d+)?/i.test(text) || /^avg\s*vol(ume)?\s*(\d+)?/i.test(text)) {
    const match = text.match(/(\d+)/);
    return { field: "AVG_VOLUME", period: match ? match[1] : "20" };
  }
  if (/^relative\s*volume\s*(\d+)?/i.test(text) || /^rel\s*vol(ume)?\s*(\d+)?/i.test(text)) {
    const match = text.match(/(\d+)/);
    return { field: "REL_VOLUME", period: match ? match[1] : "20" };
  }

  // Check for Indicator + Period (e.g. "SMA 50", "EMA 20", "RSI 14", "WMA 20", "ATR 14")
  const indMatch = text.match(/^(SMA|EMA|WMA|RSI|ATR|VWAP|HV|MACD)\s*(\d+)?/i);
  if (indMatch) {
    const indName = indMatch[1].toUpperCase();
    const period = indMatch[2] || (indName === "RSI" || indName === "ATR" ? "14" : indName === "SMA" ? "50" : "20");
    return { field: indName, period };
  }

  return { field: text.toUpperCase().replace(/\s+/g, "_") };
}

/** Map condition string (e.g. "Close > SMA 50", "RSI 14 crosses above 50") into ModalBuilderFilter */
export function conditionStringToFilter(condStr: string, idx = 0): ModalBuilderFilter | null {
  const text = (condStr || "").trim();
  if (!text) return null;

  // Check between / outside
  const betweenMatch = text.match(/^(.+?)\s+between\s+([\d.]+)\s+and\s+([\d.]+)$/i);
  if (betweenMatch) {
    const left = normalizeField(betweenMatch[1]);
    return {
      id: `cond_${idx}_${Date.now()}`,
      field: left.field,
      period: left.period,
      operator: "between",
      rightKind: "literal",
      literal: "",
      indicator: "SMA",
      indicatorPeriod: "50",
      low: betweenMatch[2],
      high: betweenMatch[3],
      isBenchmark: left.isBenchmark,
    };
  }

  // Match comparison ops or crosses
  const match = text.match(
    /^(.+?)\s*(>=|<=|>|<|==|!=|=|crosses\s+above|crosses\s+below|cross_above|cross_below)\s*(.+)$/i
  );
  if (!match) return null;

  const leftRaw = match[1].trim();
  const rawOp = match[2].trim().toLowerCase();
  const rightRaw = match[3].trim();

  let operator = ">";
  if (rawOp === ">=") operator = ">=";
  else if (rawOp === "<=") operator = "<=";
  else if (rawOp === ">") operator = ">";
  else if (rawOp === "<") operator = "<";
  else if (rawOp === "==" || rawOp === "=") operator = "==";
  else if (rawOp === "!=") operator = "!=";
  else if (rawOp.includes("above")) operator = "cross_above";
  else if (rawOp.includes("below")) operator = "cross_below";

  const left = normalizeField(leftRaw);

  // Check right side: numeric literal vs indicator
  const numVal = Number(rightRaw);
  if (Number.isFinite(numVal) && !/prior|sma|ema|rsi|atr|volume|close|high|low/i.test(rightRaw)) {
    return {
      id: `cond_${idx}_${Date.now()}`,
      field: left.field,
      period: left.period,
      operator,
      rightKind: "literal",
      literal: rightRaw,
      indicator: "SMA",
      indicatorPeriod: "50",
      low: "",
      high: "",
      isBenchmark: left.isBenchmark,
    };
  }

  // Right side is an indicator or field
  const right = normalizeField(rightRaw);
  return {
    id: `cond_${idx}_${Date.now()}`,
    field: left.field,
    period: left.period,
    operator,
    rightKind: "indicator",
    literal: "",
    indicator: right.field,
    indicatorPeriod: right.period || (right.field === "HIGH" || right.field === "LOW" ? "252" : right.field === "RSI" || right.field === "ATR" ? "14" : right.field === "SMA" ? "50" : "20"),
    low: "",
    high: "",
    isBenchmark: left.isBenchmark || right.isBenchmark,
  };
}

/** Convert array of condition strings or objects into ModalBuilderFilter[] */
export function entryConditionsToFilters(
  conditions: Array<{ name?: string; id?: string } | string> | null | undefined
): ModalBuilderFilter[] {
  if (!Array.isArray(conditions) || conditions.length === 0) return [];

  const filters: ModalBuilderFilter[] = [];
  conditions.forEach((item, index) => {
    const text = typeof item === "string" ? item : item?.name;
    if (text) {
      const parsed = conditionStringToFilter(text, index);
      if (parsed) filters.push(parsed);
    }
  });

  return filters;
}

/** Convert a filter operand to its Pine Script v6 representation and plot metadata */
function operandToPine(
  field: string,
  period?: string,
  isBenchmark?: boolean
): { expr: string; plot?: { name: string; expr: string }; isBenchmark?: boolean } {
  const norm = field.toUpperCase().trim();
  const p = period || "";

  if (isBenchmark || norm === "BENCHMARK_CLOSE") {
    if (norm === "SMA" || norm === "EMA") {
      const len = p || "50";
      return {
        expr: `request.security(benchmarkSymbol, timeframe.period, ta.${norm.toLowerCase()}(close, ${len}))`,
        plot: { name: `NIFTY 500 ${norm} ${len}`, expr: `request.security(benchmarkSymbol, timeframe.period, ta.${norm.toLowerCase()}(close, ${len}))` },
        isBenchmark: true,
      };
    }
    return {
      expr: "request.security(benchmarkSymbol, timeframe.period, close)",
      plot: { name: "NIFTY 500 Close", expr: "request.security(benchmarkSymbol, timeframe.period, close)" },
      isBenchmark: true,
    };
  }

  switch (norm) {
    case "CLOSE":
      return { expr: "close" };
    case "OPEN":
      return { expr: "open" };
    case "HIGH":
      if (p && Number(p) > 0) {
        return {
          expr: `ta.highest(high, ${p})[1]`,
          plot: { name: `Prior ${p} High`, expr: `ta.highest(high, ${p})[1]` },
        };
      }
      return { expr: "high" };
    case "LOW":
      if (p && Number(p) > 0) {
        return {
          expr: `ta.lowest(low, ${p})[1]`,
          plot: { name: `Prior ${p} Low`, expr: `ta.lowest(low, ${p})[1]` },
        };
      }
      return { expr: "low" };
    case "VOLUME":
      return { expr: "volume" };
    case "PREV_CLOSE":
      return { expr: "close[1]" };
    case "PREV_HIGH":
      return { expr: "high[1]" };
    case "DAILY_RETURN":
      return { expr: "((close - close[1]) / close[1] * 100)" };
    case "GAP_PCT":
      return { expr: "((open - close[1]) / close[1] * 100)" };
    case "SMA": {
      const len = p || "50";
      return { expr: `ta.sma(close, ${len})`, plot: { name: `SMA ${len}`, expr: `ta.sma(close, ${len})` } };
    }
    case "EMA": {
      const len = p || "20";
      return { expr: `ta.ema(close, ${len})`, plot: { name: `EMA ${len}`, expr: `ta.ema(close, ${len})` } };
    }
    case "WMA": {
      const len = p || "20";
      return { expr: `ta.wma(close, ${len})`, plot: { name: `WMA ${len}`, expr: `ta.wma(close, ${len})` } };
    }
    case "RSI": {
      const len = p || "14";
      return { expr: `ta.rsi(close, ${len})`, plot: { name: `RSI ${len}`, expr: `ta.rsi(close, ${len})` } };
    }
    case "ATR": {
      const len = p || "14";
      return { expr: `ta.atr(${len})`, plot: { name: `ATR ${len}`, expr: `ta.atr(${len})` } };
    }
    case "AVG_VOLUME": {
      const len = p || "20";
      return { expr: `ta.sma(volume, ${len})`, plot: { name: `Volume SMA ${len}`, expr: `ta.sma(volume, ${len})` } };
    }
    case "REL_VOLUME": {
      const len = p || "20";
      return { expr: `(volume / nz(ta.sma(volume, ${len}), 1))` };
    }
    case "VWAP":
      return { expr: "ta.vwap", plot: { name: "VWAP", expr: "ta.vwap" } };
    default:
      if (p && Number(p) > 0) {
        return { expr: `ta.sma(close, ${p})`, plot: { name: `${norm} ${p}`, expr: `ta.sma(close, ${p})` } };
      }
      return { expr: "close" };
  }
}

/** Right side operand generator */
function rightOperandToPine(
  filter: ModalBuilderFilter
): { expr: string; plot?: { name: string; expr: string }; isBenchmark?: boolean } {
  if (filter.rightKind === "literal" || (!filter.indicator && filter.literal)) {
    const raw = String(filter.literal ?? "").trim() || "0";
    return { expr: raw };
  }

  const ind = filter.indicator || "SMA";
  const p = filter.indicatorPeriod || (ind === "HIGH" || ind === "LOW" ? "252" : ind === "RSI" || ind === "ATR" ? "14" : ind === "SMA" ? "50" : "20");
  return operandToPine(ind, p, filter.isBenchmark);
}

export interface GeneratePineIndicatorOptions {
  name: string;
  description?: string;
  filters: ModalBuilderFilter[];
  logic: "ALL" | "ANY";
  side?: "LONG" | "SHORT";
  benchmarkSymbol?: string;
}

/**
 * Generate valid Pine Script v6 indicator code from builder filters and options.
 * Matches backend Pine compiler AST and screener execution standards.
 */
export function filtersToPineIndicator(opts: GeneratePineIndicatorOptions): string {
  const title = (opts.name || "Custom Strategy").replace(/"/g, "'").trim();
  const filters = opts.filters || [];
  const logic = opts.logic || "ALL";

  const conditionLines: string[] = [];
  const condNames: string[] = [];
  const plots: Array<{ name: string; expr: string }> = [];
  let hasBenchmark = false;

  filters.forEach((filter, index) => {
    const condVar = `c${index + 1}`;
    condNames.push(condVar);

    const left = operandToPine(filter.field, filter.period, filter.isBenchmark);
    if (left.isBenchmark) hasBenchmark = true;
    if (left.plot) plots.push(left.plot);

    const op = filter.operator || ">";

    if (op === "between") {
      const low = filter.low || "0";
      const high = filter.high || "0";
      conditionLines.push(`${condVar} = ${left.expr} >= ${low} and ${left.expr} <= ${high}`);
    } else if (op === "outside") {
      const low = filter.low || "0";
      const high = filter.high || "0";
      conditionLines.push(`${condVar} = ${left.expr} < ${low} or ${left.expr} > ${high}`);
    } else if (op === "cross_above") {
      const right = rightOperandToPine(filter);
      if (right.isBenchmark) hasBenchmark = true;
      if (right.plot) plots.push(right.plot);
      conditionLines.push(`${condVar} = ta.crossover(${left.expr}, ${right.expr})`);
    } else if (op === "cross_below") {
      const right = rightOperandToPine(filter);
      if (right.isBenchmark) hasBenchmark = true;
      if (right.plot) plots.push(right.plot);
      conditionLines.push(`${condVar} = ta.crossunder(${left.expr}, ${right.expr})`);
    } else {
      const right = rightOperandToPine(filter);
      if (right.isBenchmark) hasBenchmark = true;
      if (right.plot) plots.push(right.plot);
      const pineOp = op === "=" ? "==" : op;
      conditionLines.push(`${condVar} = ${left.expr} ${pineOp} ${right.expr}`);
    }
  });

  const benchmarkDecl = hasBenchmark
    ? `benchmarkSymbol = input.symbol("${opts.benchmarkSymbol || "NSE:CNX500"}", "Benchmark")\n\n`
    : "";

  const joiner = logic === "ANY" ? " or " : " and ";
  const signalExpr = condNames.length > 0 ? condNames.join(joiner) : "true";

  // De-duplicate plots by name
  const seenPlot = new Set<string>(["Signal", "Close"]);
  const plotLines: string[] = ['plot(scanSignal ? 1 : 0, "Signal")', 'plot(close, "Close")'];

  plots.forEach((p) => {
    if (!seenPlot.has(p.name)) {
      seenPlot.add(p.name);
      plotLines.push(`plot(${p.expr}, "${p.name}")`);
    }
  });

  return `//@version=6
indicator("${title}", overlay=false)

${benchmarkDecl}${conditionLines.join("\n")}

scanSignal = ${signalExpr}

${plotLines.join("\n")}
plotshape(scanSignal, title="Buy", style=shape.triangleup, location=location.bottom, size=size.tiny, text="BUY")
alertcondition(scanSignal, title="${title}", message="${title} condition triggered")
`;
}
