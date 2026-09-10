import type { IndicatorFilter, IndicatorOutputDef } from "../api_indicator_scanner";

export type AbsorbedOutput = {
  name: string;
  kind: string;
};

const SIGNAL_NAME = /signal|scan$/i;

export function absorbOutputs(
  outputs: Array<{ name?: string; kind?: string }> | null | undefined,
): AbsorbedOutput[] {
  return (outputs || [])
    .map((item) => ({ name: String(item.name || "").trim(), kind: String(item.kind || "plot") }))
    .filter((item) => item.name.length > 0);
}

export function looksLikeAggregateSignal(name: string | null | undefined): boolean {
  const text = String(name || "").trim().toLowerCase();
  if (!text) return false;
  const left = text.split("=")[0].trim();
  if (/^(eligible\s+)?(signal|scan)$/.test(left)) return true;
  if (/\beligible\s+signal$/.test(left)) return true;
  if (/\bbreakout\s+signal$/.test(left)) return true;
  return false;
}

export function isAggregateSignalFilter(filter: IndicatorFilter | null | undefined): boolean {
  if (!filter) return false;
  return looksLikeAggregateSignal(filter.field) || looksLikeAggregateSignal(describeAbsorbedFilter(filter));
}

export function absorbEntryConditions(
  parsed: { entry_conditions?: unknown } | Record<string, unknown> | null | undefined,
): string[] {
  const raw =
    parsed && typeof parsed === "object"
      ? (parsed as { entry_conditions?: unknown }).entry_conditions
      : undefined;
  if (!Array.isArray(raw)) return [];
  const names: string[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    const name = typeof item === "string" ? item.trim() : String((item as { name?: string })?.name || "").trim();
    const key = name.toLowerCase();
    if (!name || looksLikeAggregateSignal(name) || seen.has(key)) continue;
    seen.add(key);
    names.push(name);
  }
  return names;
}

export function defaultColumnFilter(column: AbsorbedOutput): IndicatorFilter {
  if (column.kind === "plotshape" || column.kind === "alertcondition") {
    return { field: column.name, operator: "is_true" };
  }
  if (column.kind === "plot" && SIGNAL_NAME.test(column.name)) {
    return { field: column.name, operator: "=", value: 1 };
  }
  // TradingView Pine Screener uses a single-value equals filter on numeric plots.
  // EMA 20 = 1 matches nothing (it is a price). Do not default to >= 1.
  return { field: column.name, operator: "=" };
}

export function preferredScreenerColumn(columns: AbsorbedOutput[]): AbsorbedOutput | undefined {
  return (
    columns.find((item) => item.kind === "plot" && SIGNAL_NAME.test(item.name)) ||
    columns.find((item) => item.kind === "plotshape" || item.kind === "alertcondition") ||
    columns[0]
  );
}

function isSignalLikeColumn(column: AbsorbedOutput | undefined): boolean {
  if (!column) return false;
  if (column.kind === "plotshape" || column.kind === "alertcondition") return true;
  return column.kind === "plot" && SIGNAL_NAME.test(column.name);
}

/** True when the user copied TradingView's "type 1 on the first price plot" filter. */
export function isTvStyleSignalEqualsOneOnPricePlot(
  filter: IndicatorFilter | null | undefined,
  columns: AbsorbedOutput[],
): boolean {
  if (!filter) return false;
  const value = filter.value;
  const isOne = value === 1 || value === 1.0 || value === "1";
  if (!isOne) return false;
  if (!["=", "==", ">="].includes(filter.operator || "=")) return false;
  const column = columns.find((item) => item.name === filter.field);
  if (isSignalLikeColumn(column) || SIGNAL_NAME.test(filter.field || "")) return false;
  return true;
}

/** Pine Screener: a lone 1 on a price plot means equals 1, not >= 1. */
export function normalizePineScreenerFilters(
  filters: IndicatorFilter[],
  columns: AbsorbedOutput[],
): IndicatorFilter[] {
  return filters.map((filter) => {
    if (!isTvStyleSignalEqualsOneOnPricePlot(filter, columns)) return filter;
    if (filter.operator === ">=") return { ...filter, operator: "=" };
    return filter;
  });
}

const SCREENER_SIGNAL_ROOTS = [
  "scanSignal",
  "scan_signal",
  "longCondition",
  "long_condition",
  "buyCondition",
  "buy_condition",
  "buySignal",
  "buy_signal",
  "entryCondition",
  "entry_condition",
  "eligible",
];

/** Insert plot(buySignal ? 1 : 0, "Signal") so TradingView Pine Screener can filter Signal = 1. */
export function insertScreenerSignalPlot(source: string): string {
  const text = source || "";
  if (/plot\s*\(\s*(scanSignal|buySignal|longCondition|eligible)\b/i.test(text)) return text;
  if (/plot\s*\([^;]*\? 1 : 0/i.test(text)) return text;
  const root = SCREENER_SIGNAL_ROOTS.find((name) => new RegExp(`\\b${name}\\s*=`).test(text));
  if (!root) return text;
  const plotLine = `plot(${root} ? 1 : 0, "Signal")\n`;
  const match = text.match(/^[ \t]*plot\s*\(/m);
  if (match && match.index !== undefined) {
    return text.slice(0, match.index) + plotLine + text.slice(match.index);
  }
  return `${text.replace(/\s*$/, "")}\n${plotLine}`;
}

export function absorbScreenFilters(outputs: AbsorbedOutput[]): IndicatorFilter[] {
  const signalPlot = outputs.find((item) => item.kind === "plot" && SIGNAL_NAME.test(item.name));
  if (signalPlot) {
    return [defaultColumnFilter(signalPlot)];
  }
  const shape = outputs.find((item) => item.kind === "plotshape" || item.kind === "alertcondition");
  if (shape) {
    return [defaultColumnFilter(shape)];
  }
  return [];
}

export function absorbFromParsedDefinition(
  parsed: { outputs?: IndicatorOutputDef[]; entry_conditions?: unknown } | Record<string, unknown> | null | undefined,
): { columns: AbsorbedOutput[]; filters: IndicatorFilter[]; entryConditions: string[] } {
  const raw = parsed && typeof parsed === "object" ? (parsed as { outputs?: IndicatorOutputDef[] }).outputs : undefined;
  const columns = absorbOutputs(raw);
  const entryConditions = absorbEntryConditions(parsed);
  return {
    columns,
    entryConditions,
    filters: entryConditions.length ? [] : absorbScreenFilters(columns),
  };
}

export function describeAbsorbedFilter(filter: IndicatorFilter): string {
  if (filter.operator === "between") {
    return `${filter.field} between ${filter.low ?? "?"} and ${filter.high ?? "?"}`;
  }
  if (filter.operator === "is_true") return `${filter.field} is true`;
  if (filter.operator === "is_false") return `${filter.field} is false`;
  if (filter.value === undefined || filter.value === null || filter.value === "") {
    return `${filter.field} ${filter.operator}`;
  }
  return `${filter.field} ${filter.operator} ${String(filter.value)}`;
}
