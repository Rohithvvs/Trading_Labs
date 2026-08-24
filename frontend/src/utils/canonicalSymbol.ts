/** Equity series suffixes — must stay in sync with backend ``app.utils.symbol``. */
const EQUITY_SERIES_SUFFIXES = [
  "-EQ",
  "-BE",
  "-BZ",
  "-SM",
  "-ST",
  "-IV",
  "-RR",
  "-BL",
  "-BT",
  "-GC",
] as const;

/**
 * Display/canonical ticker used in the 755-stock table.
 * Strips exchange prefixes and equity series suffixes, but keeps hyphens that
 * are part of the name (BAJAJ-AUTO). Does not invent a ticker from a company name.
 */
export function displayCanonicalSymbol(raw: string | null | undefined): string {
  if (!raw) return "";
  let s = raw.trim().toUpperCase();
  if (s.startsWith("NSE:")) s = s.slice(4);
  else if (s.startsWith("BSE:")) s = s.slice(4);
  else if (s.includes(":")) s = s.split(":")[1] ?? s;
  for (const suffix of EQUITY_SERIES_SUFFIXES) {
    if (s.endsWith(suffix)) {
      s = s.slice(0, -suffix.length);
      break;
    }
  }
  return s;
}
