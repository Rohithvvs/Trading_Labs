import { describe, expect, it } from "vitest";
import { displayCanonicalSymbol } from "../canonicalSymbol";
import {
  attachInstrumentMetadata,
  indexUniverseInstruments,
  lookupUniverseInstrument,
} from "../universeInstruments";

describe("displayCanonicalSymbol", () => {
  it("strips broker prefix and equity series without inventing tickers", () => {
    expect(displayCanonicalSymbol("NSE:360ONE-EQ")).toBe("360ONE");
    expect(displayCanonicalSymbol("360ONE-EQ")).toBe("360ONE");
    expect(displayCanonicalSymbol("360ONE")).toBe("360ONE");
    expect(displayCanonicalSymbol("BAJAJ-AUTO-EQ")).toBe("BAJAJ-AUTO");
    expect(displayCanonicalSymbol("ATLANTAELE-BE")).toBe("ATLANTAELE");
  });
});

describe("universe instrument lookup", () => {
  const instruments = indexUniverseInstruments([
    {
      symbol: "360ONE",
      universe_symbol: "360ONE-EQ",
      company_name: "360 ONE WAM Ltd.",
      exchange: "NSE",
      series: "EQ",
      broker_symbol: "NSE:360ONE-EQ",
      isin: "INE466L01038",
      is_active: true,
      universe: "NIFTY500",
    },
  ]);

  it("resolves stored, canonical, and broker forms to the same company", () => {
    expect(lookupUniverseInstrument("360ONE-EQ", instruments)?.company_name).toBe("360 ONE WAM Ltd.");
    expect(lookupUniverseInstrument("360ONE", instruments)?.company_name).toBe("360 ONE WAM Ltd.");
    expect(lookupUniverseInstrument("NSE:360ONE-EQ", instruments)?.company_name).toBe("360 ONE WAM Ltd.");
  });

  it("attaches company names without changing the scan identity symbol", () => {
    const rows = attachInstrumentMetadata([{ symbol: "360ONE-EQ" }], instruments);
    expect(rows[0].symbol).toBe("360ONE-EQ");
    expect(rows[0].companyName).toBe("360 ONE WAM Ltd.");
  });
});
