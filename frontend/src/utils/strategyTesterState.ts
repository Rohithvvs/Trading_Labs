import type { SavedStrategyItem } from "../api_strategy_tester";

function strategyTimestamp(item: SavedStrategyItem): string {
  return item.updated_at || "";
}

/** Keep one record per strategy id. Later/newer rows win when ids collide. */
export function uniqueStrategiesById(list: SavedStrategyItem[] | null | undefined): SavedStrategyItem[] {
  const byId = new Map<string, SavedStrategyItem>();
  for (const item of list || []) {
    const id = String(item?.id ?? "").trim();
    if (!id) continue;
    const prev = byId.get(id);
    if (!prev || strategyTimestamp(item) >= strategyTimestamp(prev)) {
      byId.set(id, item);
    }
  }
  return Array.from(byId.values());
}

/**
 * Unique by id, then collapse identical names so the Strategy Tester dropdown
 * never lists "Momentum Strategy" twice. Later/newer rows win.
 */
export function uniqueStrategiesByIdAndName(list: SavedStrategyItem[] | null | undefined): SavedStrategyItem[] {
  const unique = uniqueStrategiesById(list).filter((item) => !item.is_preset);
  const byName = new Map<string, SavedStrategyItem>();
  const unnamed: SavedStrategyItem[] = [];
  for (const item of unique) {
    const key = (item.name || "").trim().toLowerCase();
    if (!key) {
      unnamed.push(item);
      continue;
    }
    const prev = byName.get(key);
    if (!prev || strategyTimestamp(item) >= strategyTimestamp(prev)) {
      byName.set(key, item);
    }
  }
  return [...byName.values(), ...unnamed];
}

export type StrategySelectOption = {
  id: string;
  name: string;
  kind: "preset" | "saved";
};

/**
 * One option per display name. A saved copy of a preset replaces the preset
 * so the dashboard matches Indicator Scanner (no repeated names).
 */
export function strategySelectOptions(
  presets: Array<{ preset_id: string; name: string }> | null | undefined,
  saved: SavedStrategyItem[] | null | undefined,
): StrategySelectOption[] {
  const uniqueSaved = uniqueStrategiesByIdAndName(saved);
  const savedByName = new Map<string, SavedStrategyItem>();
  for (const item of uniqueSaved) {
    const key = (item.name || "").trim().toLowerCase();
    if (key) savedByName.set(key, item);
  }

  const options: StrategySelectOption[] = [];
  const seen = new Set<string>();

  for (const preset of presets || []) {
    const id = String(preset.preset_id || "").trim();
    const name = preset.name || id;
    const key = name.trim().toLowerCase();
    if (!id || !key || seen.has(key)) continue;
    seen.add(key);
    const savedMatch = savedByName.get(key);
    if (savedMatch) {
      options.push({ id: savedMatch.id, name: savedMatch.name, kind: "saved" });
    } else {
      options.push({ id, name, kind: "preset" });
    }
  }

  for (const item of uniqueSaved) {
    const key = (item.name || "").trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    options.push({ id: item.id, name: item.name, kind: "saved" });
  }

  return options;
}

export function resolveSelectedStrategyId(
  currentId: string,
  options: StrategySelectOption[],
  presets: Array<{ preset_id: string; name: string }> | null | undefined,
  saved: SavedStrategyItem[] | null | undefined,
): string {
  if (!options.length) return currentId;
  if (options.some((opt) => opt.id === currentId)) return currentId;
  const currentName =
    presets?.find((item) => item.preset_id === currentId)?.name ||
    saved?.find((item) => item.id === currentId)?.name;
  if (currentName) {
    const match = options.find((opt) => opt.name.trim().toLowerCase() === currentName.trim().toLowerCase());
    if (match) return match.id;
  }
  return options[0]?.id || currentId;
}
