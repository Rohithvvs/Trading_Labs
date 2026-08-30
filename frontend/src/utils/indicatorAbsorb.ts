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

export function absorbScreenFilters(outputs: AbsorbedOutput[]): IndicatorFilter[] {
  const signalPlot = outputs.find((item) => item.kind === "plot" && SIGNAL_NAME.test(item.name));
  if (signalPlot) {
    return [{ field: signalPlot.name, operator: "=", value: 1 }];
  }
  const shape = outputs.find((item) => item.kind === "plotshape" || item.kind === "alertcondition");
  if (shape) {
    return [{ field: shape.name, operator: "is_true" }];
  }
  return [];
}

export function absorbFromParsedDefinition(
  parsed: { outputs?: IndicatorOutputDef[] } | Record<string, unknown> | null | undefined,
): { columns: AbsorbedOutput[]; filters: IndicatorFilter[] } {
  const raw = parsed && typeof parsed === "object" ? (parsed as { outputs?: IndicatorOutputDef[] }).outputs : undefined;
  const columns = absorbOutputs(raw);
  return { columns, filters: absorbScreenFilters(columns) };
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
