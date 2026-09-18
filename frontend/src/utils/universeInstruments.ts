import { displayCanonicalSymbol } from "./canonicalSymbol";

export type UniverseInstrument = {
  symbol: string;
  universe_symbol: string;
  company_name: string | null;
  exchange: string;
  series: string | null;
  broker_symbol: string;
  isin: string | null;
  is_active: boolean;
  universe: string | null;
  stock_id?: number | null;
};

export function indexUniverseInstruments(
  items: UniverseInstrument[] | null | undefined,
): Map<string, UniverseInstrument> {
  const map = new Map<string, UniverseInstrument>();
  for (const item of items ?? []) {
    for (const key of [item.symbol, item.universe_symbol, item.broker_symbol]) {
      const normalized = String(key || "").trim().toUpperCase();
      if (normalized) map.set(normalized, item);
    }
  }
  return map;
}

export function lookupUniverseInstrument(
  symbol: string | null | undefined,
  byKey: Map<string, UniverseInstrument>,
): UniverseInstrument | undefined {
  if (!symbol) return undefined;
  const raw = symbol.trim().toUpperCase();
  return byKey.get(raw) ?? byKey.get(displayCanonicalSymbol(raw));
}

export function attachInstrumentMetadata<T extends { symbol: string; companyName?: string | null }>(
  rows: T[],
  byKey: Map<string, UniverseInstrument>,
): T[] {
  return rows.map((row) => {
    const instrument = lookupUniverseInstrument(row.symbol, byKey);
    return {
      ...row,
      companyName: instrument?.company_name ?? row.companyName ?? null,
    };
  });
}
