import { lastCompletedTradingDayIST, isTradingDayISO } from "../tradingHours";

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
  });

  it("before Friday close uses Thursday", () => {
    const fridayMorningIST = new Date("2026-08-28T04:30:00.000Z");
    expect(lastCompletedTradingDayIST(fridayMorningIST)).toBe("2026-08-27");
  });

  it("after Friday close uses Friday", () => {
    const fridayEveningIST = new Date("2026-08-28T10:31:00.000Z");
    expect(lastCompletedTradingDayIST(fridayEveningIST)).toBe("2026-08-28");
  });

  it("on Ganesh Chaturthi uses the previous Friday", () => {
    const holidayNoonIST = new Date("2026-09-14T06:30:00.000Z");
    expect(lastCompletedTradingDayIST(holidayNoonIST)).toBe("2026-09-11");
  });
});
