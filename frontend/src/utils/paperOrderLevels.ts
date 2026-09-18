/**
 * Paper-ticket levels derived from the working entry / limit price.
 *
 * Uses the same conventions already on the Paper Order page:
 * - default stop distance is the 2% trailing-stop helper
 * - default target is 1:2 versus that stop
 * - prices snap to a ₹0.05 tick (same rounding as Apply Trailing Stop)
 *
 * Strategy-provided stop/target always win when present.
 */

export const PAPER_DEFAULT_STOP_PCT = 2;
export const PAPER_DEFAULT_REWARD_MULT = 2;
export const PAPER_PRICE_TICK = 0.05;

export function roundToTick(price: number, tick = PAPER_PRICE_TICK): number {
  if (!Number.isFinite(price) || tick <= 0) return price;
  return Math.round(price / tick) * tick;
}

function pos(n: number | null | undefined): number | null {
  return n != null && Number.isFinite(Number(n)) && Number(n) > 0 ? Number(n) : null;
}

export function levelsFromEntry(
  entry: number,
  side: "BUY" | "SELL",
  stopPct = PAPER_DEFAULT_STOP_PCT,
  rewardMult = PAPER_DEFAULT_REWARD_MULT,
): { stopLoss: number | null; target: number | null } {
  if (!Number.isFinite(entry) || entry <= 0 || stopPct <= 0 || rewardMult <= 0) {
    return { stopLoss: null, target: null };
  }
  const dir = side === "BUY" ? 1 : -1;
  const stopLoss = roundToTick(entry * (1 - (dir * stopPct) / 100));
  if (stopLoss == null || stopLoss <= 0 || stopLoss === entry) {
    return { stopLoss: null, target: null };
  }
  const risk = Math.abs(entry - stopLoss);
  const target = roundToTick(entry + dir * risk * rewardMult);
  if (target == null || target <= 0) {
    return { stopLoss, target: null };
  }
  return { stopLoss, target };
}

export function completePaperLevels(opts: {
  entry: number | null | undefined;
  side: "BUY" | "SELL";
  stop?: number | null;
  target?: number | null;
  stopPct?: number;
  rewardMult?: number;
}): {
  stopLoss: number | null;
  target: number | null;
  derivedStop: boolean;
  derivedTarget: boolean;
} {
  const entry = pos(opts.entry);
  let stop = pos(opts.stop);
  let target = pos(opts.target);
  let derivedStop = false;
  let derivedTarget = false;
  if (entry == null) {
    return { stopLoss: stop, target, derivedStop, derivedTarget };
  }

  const computed = levelsFromEntry(
    entry,
    opts.side,
    opts.stopPct ?? PAPER_DEFAULT_STOP_PCT,
    opts.rewardMult ?? PAPER_DEFAULT_REWARD_MULT,
  );
  if (stop == null && computed.stopLoss != null) {
    stop = computed.stopLoss;
    derivedStop = true;
  }
  if (target == null && stop != null) {
    const dir = opts.side === "BUY" ? 1 : -1;
    const risk = Math.abs(entry - stop);
    if (risk > 0) {
      target = roundToTick(entry + dir * risk * (opts.rewardMult ?? PAPER_DEFAULT_REWARD_MULT));
      derivedTarget = true;
    }
  }
  return { stopLoss: stop, target, derivedStop, derivedTarget };
}
