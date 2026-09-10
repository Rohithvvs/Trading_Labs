import { lastCompletedTradingDayIST, currentCashSessionIST, effectivePineScreenerSessionIST, isTradingDayISO, isoDateIST } from "../tradingHours";

describe("NSE cash calendar", () => {
  it("treats Friday 28 Aug 2026 (Raksha Bandhan) as a trading day", () => {
    expect(isTradingDayISO("2026-08-28")).toBe(true);
  });

  it("treats Monday 14 Sep 2026 (Ganesh Chaturthi) as a holiday", () => {
    expect(isTradingDayISO("2026-09-14")).toBe(false);
  });

  it("on Sunday 30 Aug 2026 uses Friday 28 Aug as the last completed session", () => {
    const sundayNoonIST = new Date("2026-08-30T06:30:00.000Z");
    expect(lastCompletedTradingDayIST(sundayNoonIST)).toBe("2026-08-28");
    expect(effectivePineScreenerSessionIST(sundayNoonIST)).toBe("2026-08-28");
  });

  it("before market open on Friday uses Thursday for both completed and Pine Screener", () => {
    const fridayEarlyMorningIST = new Date("2026-08-28T01:00:00.000Z"); // 06:30 AM IST
    expect(lastCompletedTradingDayIST(fridayEarlyMorningIST)).toBe("2026-08-27");
    expect(effectivePineScreenerSessionIST(fridayEarlyMorningIST)).toBe("2026-08-27");
    expect(currentCashSessionIST(fridayEarlyMorningIST)).toBe("2026-08-28");
  });

  it("before Friday close uses Thursday for completed, Friday for Pine Screener", () => {
    const fridayMorningIST = new Date("2026-08-28T04:30:00.000Z");
    expect(lastCompletedTradingDayIST(fridayMorningIST)).toBe("2026-08-27");
    expect(effectivePineScreenerSessionIST(fridayMorningIST)).toBe("2026-08-28");
  });

  it("after Friday close uses Friday", () => {
    const fridayEveningIST = new Date("2026-08-28T10:31:00.000Z");
    expect(lastCompletedTradingDayIST(fridayEveningIST)).toBe("2026-08-28");
    expect(effectivePineScreenerSessionIST(fridayEveningIST)).toBe("2026-08-28");
  });

  it("on Ganesh Chaturthi uses the previous Friday", () => {
    const holidayNoonIST = new Date("2026-09-14T06:30:00.000Z");
    expect(lastCompletedTradingDayIST(holidayNoonIST)).toBe("2026-09-11");
    expect(effectivePineScreenerSessionIST(holidayNoonIST)).toBe("2026-09-11");
    expect(currentCashSessionIST(holidayNoonIST)).toBe("2026-09-11");
  });

  it("isoDateIST is the IST calendar date even on weekends", () => {
    const saturdayMorningIST = new Date("2026-09-05T03:44:00.000Z"); // 09:14 IST
    expect(isoDateIST(saturdayMorningIST)).toBe("2026-09-05");
    expect(effectivePineScreenerSessionIST(saturdayMorningIST)).toBe("2026-09-04");
    expect(currentCashSessionIST(saturdayMorningIST)).toBe("2026-09-04");
  });

  it("before market open on a trading day the scanner as-of is today", () => {
    const thursdayMidnightIST = new Date("2026-09-09T19:28:00.000Z"); // 00:58 IST on 10 Sep
    expect(isoDateIST(thursdayMidnightIST)).toBe("2026-09-10");
    expect(currentCashSessionIST(thursdayMidnightIST)).toBe("2026-09-10");
    expect(effectivePineScreenerSessionIST(thursdayMidnightIST)).toBe("2026-09-09");
    expect(lastCompletedTradingDayIST(thursdayMidnightIST)).toBe("2026-09-09");
  });
});
