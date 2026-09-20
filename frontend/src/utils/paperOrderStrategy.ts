/** Persist and recover the originating strategy on paper orders via notes. */

const STRATEGY_TAG = /Strategy:\s*([^·\n]+)/i;
const IMPORTED_FROM = /Imported from\s+([^|]+)/i;

export function formatStrategyNote(
  strategyName?: string | null,
  runId?: string | null,
): string {
  const name = (strategyName || "").trim();
  const run = (runId || "").trim();
  if (!name && !run) return "";
  const parts: string[] = [];
  if (name) parts.push(`Strategy: ${name}`);
  if (run) parts.push(`Run: ${run}`);
  return parts.join(" · ");
}

export function mergeStrategyNote(
  notes: string | null | undefined,
  strategyName?: string | null,
  runId?: string | null,
): string {
  const existing = (notes || "").trim();
  const tag = formatStrategyNote(strategyName, runId);
  if (!tag) return existing;
  const name = (strategyName || "").trim();
  if (name && existing.toLowerCase().includes(`strategy: ${name.toLowerCase()}`)) {
    return existing;
  }
  if (existing.includes(tag)) return existing;
  return existing ? `${existing} · ${tag}` : tag;
}

export function extractStrategyFromNotes(notes?: string | null): string | null {
  if (!notes) return null;
  const tagged = notes.match(STRATEGY_TAG)?.[1]?.trim();
  if (tagged) return tagged;
  const imported = notes.match(IMPORTED_FROM)?.[1]?.trim();
  if (imported && imported.toLowerCase() !== "system recommendation") return imported;
  return null;
}
