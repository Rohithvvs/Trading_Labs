import { describe, expect, it } from "vitest";
import {
  columnSetupKind,
  conditionOperator,
  defaultSignalDraft,
  draftToFilter,
  operatorToCondition,
  pulseFilter,
} from "../signalSetup";

describe("signalSetup", () => {
  it("classifies signal vs pulse vs value columns", () => {
    expect(columnSetupKind({ name: "Momentum Signal", kind: "plotshape" })).toBe("signal");
    expect(columnSetupKind({ name: "Momentum Pulse", kind: "alertcondition" })).toBe("pulse");
    expect(columnSetupKind({ name: "EMA 20", kind: "plot" })).toBe("value");
    expect(columnSetupKind({ name: "52W Breakout Signal", kind: "plot" })).toBe("signal");
  });

  it("maps the ten TradingView conditions onto scan operators", () => {
    expect(conditionOperator("above")).toBe(">");
    expect(conditionOperator("above_or_equal")).toBe(">=");
    expect(conditionOperator("below")).toBe("<");
    expect(conditionOperator("below_or_equal")).toBe("<=");
    expect(conditionOperator("crosses")).toBe("!=");
    expect(conditionOperator("crosses_up")).toBe(">");
    expect(conditionOperator("crosses_down")).toBe("<");
    expect(conditionOperator("between")).toBe("between");
    expect(conditionOperator("outside")).toBe("outside");
    expect(conditionOperator("equal")).toBe("=");
  });

  it("defaults Momentum Signal to Above Value 0 and keeps a saved condition", () => {
    const column = { name: "Momentum Signal", kind: "plotshape" };
    expect(defaultSignalDraft(column)).toEqual({
      type: "signal",
      condition: "above",
      source: "value",
      value: 0,
      low: "",
      high: "",
    });
    const saved = defaultSignalDraft(column, {
      field: "Momentum Signal",
      operator: "<",
      value: 1,
      condition: "below",
      source: "value",
      setup_type: "signal",
    });
    expect(saved.condition).toBe("below");
    expect(saved.value).toBe(1);
    expect(operatorToCondition("is_true")).toBe("above");
  });

  it("serializes a signal draft and a pulse filter separately", () => {
    expect(
      draftToFilter("Momentum Signal", {
        type: "signal",
        condition: "above",
        source: "value",
        value: 0,
        low: "",
        high: "",
      }),
    ).toEqual({
      field: "Momentum Signal",
      operator: ">",
      value: 0,
      condition: "above",
      source: "value",
      setup_type: "signal",
      compare_field: null,
    });
    expect(pulseFilter("Momentum Pulse", true)).toMatchObject({
      field: "Momentum Pulse",
      operator: "is_true",
      value: true,
      setup_type: "pulse",
    });
  });
});
