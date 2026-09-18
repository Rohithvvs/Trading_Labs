import type { StrategyConfigPayload, StrategyFilterInput } from "../api_strategy_tester";
import type { ModalBuilderFilter } from "./pineParser";

function seriesName(raw: string | undefined, fallback = "CLOSE"): string {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  return text.toUpperCase().replace(/\s+/g, "_").replace(/-/g, "_");
}

function optionalPeriod(raw: string | number | undefined): number | undefined {
  if (raw == null || raw === "") return undefined;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

function leftOperand(f: ModalBuilderFilter): { field: string; left: string | { indicator: string; period?: number } } {
  const name =
    f.isBenchmark || f.field === "BENCHMARK_CLOSE" ? "BENCHMARK_CLOSE" : seriesName(f.field);
  const period = optionalPeriod(f.period);
  if (period) {
    return { field: `${name}_${period}`, left: { indicator: name, period } };
  }
  return { field: name, left: name };
}

/** Convert a builder/Pine filter into the backend strategy-config leaf shape. */
export function toApiFilter(f: ModalBuilderFilter): StrategyFilterInput {
  const { field, left } = leftOperand(f);
  const operator = String(f.operator || "").trim();
  if (!operator) {
    throw new Error(`Filter "${f.label || field}" is missing an operator.`);
  }

  const base: StrategyFilterInput = {
    id: f.id,
    field,
    left,
    operator,
    label: f.label,
  };

  if (operator === "between" || operator === "outside") {
    const low = Number(f.low);
    const high = Number(f.high);
    if (!Number.isFinite(low) || !Number.isFinite(high)) {
      throw new Error(`Filter "${f.label || field}" needs numeric low and high bounds.`);
    }
    return { ...base, low, high };
  }

  const indicatorName = seriesName(f.indicator, "");
  if (f.rightKind === "indicator" && indicatorName) {
    const period = optionalPeriod(f.indicatorPeriod);
    return {
      ...base,
      value: period ? { indicator: indicatorName, period } : { indicator: indicatorName },
    };
  }

  const raw = String(f.literal ?? "").trim();
  if (raw === "") {
    throw new Error(`Filter "${f.label || field}" is missing a comparison value.`);
  }
  const num = Number(raw);
  return { ...base, value: Number.isFinite(num) ? num : raw };
}

export function filtersToApi(filters: ModalBuilderFilter[]): StrategyFilterInput[] {
  if (!Array.isArray(filters) || filters.length === 0) {
    throw new Error("Strategy must include at least one filter.");
  }
  return filters.map(toApiFilter);
}

/** Parse field and numeric period suffix (e.g. SMA_50 -> SMA, 50; REL_VOLUME -> REL_VOLUME, undefined). */
export function parseFilterField(rawField: string | undefined): { field: string; period?: string } {
  if (!rawField) return { field: "CLOSE" };
  const text = String(rawField).trim();
  const lastUnderscore = text.lastIndexOf("_");
  if (lastUnderscore !== -1) {
    const tail = text.slice(lastUnderscore + 1);
    if (/^\d+$/.test(tail)) {
      return {
        field: text.slice(0, lastUnderscore).toUpperCase(),
        period: tail,
      };
    }
  }
  return {
    field: text.toUpperCase(),
    period: undefined,
  };
}

/** Map backend/preset/import filter object into ModalBuilderFilter shape. */
export function mapRawFilterToModalFilter(f: any, idx: number): ModalBuilderFilter {
  const leftIndicator = f.left && typeof f.left === "object" ? f.left.indicator : undefined;
  const leftPeriod = f.left && typeof f.left === "object" && f.left.period != null ? String(f.left.period) : undefined;
  const rawFieldName = typeof f.left === "string" ? f.left : (typeof f.field === "string" ? f.field : (leftIndicator || "CLOSE"));
  const fieldParsed = parseFilterField(rawFieldName);

  const finalField = leftIndicator ? leftIndicator.toUpperCase() : fieldParsed.field;
  const finalPeriod = leftPeriod || (f.period != null && f.period !== "" ? String(f.period) : fieldParsed.period);

  const isObjVal = Boolean(f.value && typeof f.value === "object" && !Array.isArray(f.value));
  const isNumVal = typeof f.value === "number" || (!isObjVal && f.value != null && f.value !== "" && !isNaN(Number(f.value)));

  const rightKind: "indicator" | "literal" = isObjVal ? "indicator" : "literal";
  const literal = isNumVal ? String(f.value) : (typeof f.value === "string" ? f.value : "");
  const indicator = isObjVal ? (f.value.indicator || "SMA") : "SMA";
  const indicatorPeriod = isObjVal && f.value.period != null ? String(f.value.period) : "";

  const lowVal = f.low != null ? String(f.low) : (Array.isArray(f.value) && f.value[0] != null ? String(f.value[0]) : "");
  const highVal = f.high != null ? String(f.high) : (Array.isArray(f.value) && f.value[1] != null ? String(f.value[1]) : "");

  return {
    id: f.id || `f_${idx}`,
    field: finalField,
    period: finalPeriod || undefined,
    operator: f.operator || f.op || ">",
    rightKind,
    literal,
    indicator,
    indicatorPeriod,
    low: lowVal,
    high: highVal,
    label: f.label || undefined,
    isBenchmark: Boolean(f.isBenchmark || finalField === "BENCHMARK_CLOSE" || rawFieldName === "BENCHMARK_CLOSE"),
    benchmarkSymbol: f.benchmarkSymbol || undefined,
  };
}

export function buildStrategyPayload(opts: {
  name: string;
  description?: string;
  universe: string;
  timeframe: string;
  side: "LONG" | "SHORT";
  startDate: string;
  endDate: string;
  initialCapital: number;
  filters: ModalBuilderFilter[];
  logic: "ALL" | "ANY";
  source?: StrategyConfigPayload["source"];
}): StrategyConfigPayload {
  return {
    name: opts.name,
    description: opts.description,
    universe: opts.universe,
    timeframe: opts.timeframe === "1 Day" ? "1D" : opts.timeframe,
    side: opts.side,
    start_date: opts.startDate,
    end_date: opts.endDate,
    initial_capital: opts.initialCapital,
    filters: filtersToApi(opts.filters),
    signal_rules: { buy_requires_all: opts.logic === "ALL" },
    position_rules: { side: opts.side, return_method: "SIMPLE" },
    source: opts.source,
  };
}
