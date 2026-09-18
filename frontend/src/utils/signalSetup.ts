import type { IndicatorFilter, SignalCondition } from "../api_indicator_scanner";
import type { AbsorbedOutput } from "./indicatorAbsorb";

export type ColumnSetupKind = "signal" | "pulse" | "value";

export type SignalSetupDraft = {
  type: "signal";
  condition: SignalCondition;
  source: string;
  value: number | "";
  low: number | "";
  high: number | "";
};

export type PulseSetupDraft = {
  type: "pulse";
  value: boolean;
};

export const SIGNAL_CONDITIONS: Array<{ id: SignalCondition; label: string }> = [
  { id: "above", label: "Above" },
  { id: "above_or_equal", label: "Above or equal" },
  { id: "below", label: "Below" },
  { id: "below_or_equal", label: "Below or equal" },
  { id: "crosses", label: "Crosses" },
  { id: "crosses_up", label: "Crosses up" },
  { id: "crosses_down", label: "Crosses down" },
  { id: "between", label: "Between" },
  { id: "outside", label: "Outside" },
  { id: "equal", label: "Equal" },
];

const RANGE_CONDITIONS = new Set<SignalCondition>(["between", "outside"]);

export function columnSetupKind(column: AbsorbedOutput | null | undefined): ColumnSetupKind {
  if (!column) return "value";
  const name = column.name.trim().toLowerCase();
  if (column.kind === "alertcondition" || /\bpulse\b/.test(name) || name.endsWith("pulse")) return "pulse";
  if (column.kind === "plotshape" || /(signal|scan)$/.test(name)) return "signal";
  return "value";
}

export function conditionOperator(condition: SignalCondition): string {
  switch (condition) {
    case "above":
    case "crosses_up":
      return ">";
    case "above_or_equal":
      return ">=";
    case "below":
    case "crosses_down":
      return "<";
    case "below_or_equal":
      return "<=";
    case "crosses":
      return "!=";
    case "between":
      return "between";
    case "outside":
      return "outside";
    case "equal":
    default:
      return "=";
  }
}

export function operatorToCondition(operator: string | undefined, stored?: SignalCondition): SignalCondition {
  if (stored && SIGNAL_CONDITIONS.some((item) => item.id === stored)) return stored;
  switch (operator) {
    case ">":
    case "above":
      return "above";
    case ">=":
    case "above_or_equal":
      return "above_or_equal";
    case "<":
    case "below":
      return "below";
    case "<=":
    case "below_or_equal":
      return "below_or_equal";
    case "!=":
    case "crosses":
      return "crosses";
    case "crosses_up":
      return "crosses_up";
    case "crosses_down":
      return "crosses_down";
    case "between":
      return "between";
    case "outside":
      return "outside";
    case "is_true":
      return "above";
    case "is_false":
      return "below";
    default:
      return "equal";
  }
}

export function isRangeCondition(condition: SignalCondition): boolean {
  return RANGE_CONDITIONS.has(condition);
}

export function defaultSignalDraft(column: AbsorbedOutput, existing?: IndicatorFilter | null): SignalSetupDraft {
  if (existing && existing.field === column.name && existing.setup_type !== "pulse") {
    const condition = operatorToCondition(existing.operator, existing.condition);
    const source = existing.compare_field || existing.source || "value";
    if (existing.operator === "is_true") {
      return { type: "signal", condition: "above", source: "value", value: 0, low: "", high: "" };
    }
    if (existing.operator === "is_false") {
      return { type: "signal", condition: "below", source: "value", value: 0, low: "", high: "" };
    }
    return {
      type: "signal",
      condition,
      source,
      value: existing.value === undefined || existing.value === null || existing.value === "" ? 0 : Number(existing.value),
      low: existing.low === undefined || existing.low === null ? "" : Number(existing.low),
      high: existing.high === undefined || existing.high === null ? "" : Number(existing.high),
    };
  }
  if (column.kind === "plot" && /(signal|scan)$/i.test(column.name)) {
    return { type: "signal", condition: "equal", source: "value", value: 1, low: "", high: "" };
  }
  return { type: "signal", condition: "above", source: "value", value: 0, low: "", high: "" };
}

export function draftToFilter(field: string, draft: SignalSetupDraft): IndicatorFilter {
  const operator = conditionOperator(draft.condition);
  const compareField = draft.source && draft.source !== "value" ? draft.source : null;
  const filter: IndicatorFilter = {
    field,
    operator,
    condition: draft.condition,
    source: draft.source || "value",
    setup_type: "signal",
    compare_field: compareField,
  };
  if (isRangeCondition(draft.condition)) {
    filter.low = draft.low === "" ? null : Number(draft.low);
    filter.high = draft.high === "" ? null : Number(draft.high);
  } else if (!compareField) {
    filter.value = draft.value === "" ? 0 : Number(draft.value);
  }
  return filter;
}

export function pulseFilter(field: string, value = true): IndicatorFilter {
  return {
    field,
    operator: value ? "is_true" : "is_false",
    value,
    setup_type: "pulse",
    source: "value",
  };
}

export function draftIsComplete(draft: SignalSetupDraft): boolean {
  if (draft.source && draft.source !== "value") return true;
  if (isRangeCondition(draft.condition)) {
    return draft.low !== "" && draft.high !== "" && Number.isFinite(Number(draft.low)) && Number.isFinite(Number(draft.high));
  }
  return draft.value !== "" && Number.isFinite(Number(draft.value));
}

export function valueSourceOptions(columns: AbsorbedOutput[], currentField: string): Array<{ id: string; label: string }> {
  const others = columns
    .filter((item) => item.name !== currentField)
    .map((item) => ({ id: item.name, label: item.name }));
  return [{ id: "value", label: "Value" }, ...others];
}
