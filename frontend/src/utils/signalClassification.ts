/**
 * Authoritative composite-score classification (0–100 Production score only).
 *
 * SCORE >= 68 → BUY
 * 55 <= SCORE < 68 → WATCH
 * SCORE < 55 → REJECT
 *
 * Do not apply this to LTM momentum_252 or 52-Week mom60.
 * Those strategies publish their own BUY/WATCH/REJECT/HOLD signals.
 */

export const BUY_SCORE_THRESHOLD = 68;
export const WATCH_SCORE_THRESHOLD = 55;

export type CompositeSignal = "BUY" | "WATCH" | "REJECT";

export function classifySignalFromScore(score: number): CompositeSignal {
  if (!Number.isFinite(score)) return "REJECT";
  if (score >= BUY_SCORE_THRESHOLD) return "BUY";
  if (score >= WATCH_SCORE_THRESHOLD) return "WATCH";
  return "REJECT";
}

export function isCompositeScoreKind(
  kind: string | null | undefined,
): kind is "composite" {
  return kind === "composite";
}
