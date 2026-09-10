import { describe, expect, it } from "vitest";
import type { SavedStrategyItem } from "../../api_strategy_tester";
import {
  resolveSelectedStrategyId,
  strategySelectOptions,
  uniqueStrategiesById,
  uniqueStrategiesByIdAndName,
} from "../strategyTesterState";

function strategy(partial: Partial<SavedStrategyItem> & { id: string; name: string }): SavedStrategyItem {
  return {
    description: "",
    ...partial,
  };
}

describe("strategyTesterState", () => {
  it("deduplicates by id, keeping the newer record", () => {
    const rows = uniqueStrategiesById([
      strategy({ id: "s-1", name: "A", updated_at: "2026-01-01T00:00:00Z" }),
      strategy({ id: "s-1", name: "A updated", updated_at: "2026-02-01T00:00:00Z" }),
      strategy({ id: "s-2", name: "B" }),
      strategy({ id: "", name: "ignored" }),
    ]);
    expect(rows.map((row) => row.id)).toEqual(["s-1", "s-2"]);
    expect(rows[0].name).toBe("A updated");
  });

  it("collapses duplicate names after unique-by-id and drops presets", () => {
    const rows = uniqueStrategiesByIdAndName([
      strategy({ id: "a", name: "Momentum Strategy", updated_at: "2026-01-01T00:00:00Z" }),
      strategy({ id: "b", name: "Momentum Strategy", updated_at: "2026-08-01T00:00:00Z" }),
      strategy({ id: "c", name: "My Custom" }),
      strategy({ id: "preset-1", name: "Breakout Strategy", is_preset: true }),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.map((row) => row.id).sort()).toEqual(["b", "c"]);
  });

  it("lists each strategy name once, preferring a saved copy over the preset", () => {
    const options = strategySelectOptions(
      [
        { preset_id: "momentum", name: "Momentum Strategy", description: "", filters: [] },
        { preset_id: "breakout", name: "Breakout Strategy", description: "", filters: [] },
      ],
      [
        strategy({ id: "s-old", name: "Momentum Strategy", updated_at: "2026-01-01T00:00:00Z" }),
        strategy({ id: "s-new", name: "Momentum Strategy", updated_at: "2026-08-01T00:00:00Z" }),
        strategy({ id: "s-custom", name: "My Custom", updated_at: "2026-08-02T00:00:00Z" }),
        strategy({ id: "s-custom-2", name: "My Custom", updated_at: "2026-07-01T00:00:00Z" }),
      ],
    );
    expect(options.map((opt) => ({ id: opt.id, name: opt.name, kind: opt.kind }))).toEqual([
      { id: "s-new", name: "Momentum Strategy", kind: "saved" },
      { id: "breakout", name: "Breakout Strategy", kind: "preset" },
      { id: "s-custom", name: "My Custom", kind: "saved" },
    ]);
  });

  it("remaps a preset selection onto the saved copy with the same name", () => {
    const options = strategySelectOptions(
      [{ preset_id: "momentum", name: "Momentum Strategy", description: "", filters: [] }],
      [strategy({ id: "s-1", name: "Momentum Strategy" })],
    );
    expect(resolveSelectedStrategyId("momentum", options, [{ preset_id: "momentum", name: "Momentum Strategy", description: "", filters: [] }], [
      strategy({ id: "s-1", name: "Momentum Strategy" }),
    ])).toBe("s-1");
  });
});
