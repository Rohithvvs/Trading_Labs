import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  fetchPaperAccountSummary,
  fetchPaperOrderById,
  fetchPaperQuote,
  placePaperOrder,
  prefillPaperTradeLocal,
  updatePaperOrder,
  invalidatePaperCaches,
  fetchChargePreview,
} from "../api";

import { toCanonicalSymbol } from "../utils/paperOrderNavigation";
import { extractStrategyFromNotes, mergeStrategyNote } from "../utils/paperOrderStrategy";
import { completePaperLevels } from "../utils/paperOrderLevels";
import {
  extractPaperAvailableCash,
  extractPaperMaxRiskPerTrade,
  logPaperCapital,
} from "../utils/paperCapital";
import type { PaperOrderNavState } from "../types/paperOrderNav";
import { isPaperOrderNavState } from "../types/paperOrderNav";
import type { PaperOrderTicketState, RecommendationPrefillRequest, ChargePreviewResponse } from "../types";
import { useToast, Button, Modal } from "../design-system";
import { InfoTooltip } from "../components/InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";
import { CACHE_KEYS, getCached, getStaleCached } from "../utils/appCache";
import { Skeleton } from "../components/Skeleton";
import {
  printRankedPerfReport,
  recordCacheHit,
  recordCacheMiss,
  recordSample,
  startPaperOrderPerf,
} from "../utils/paperOrderPerf";

const DEFAULT_TICKET: PaperOrderTicketState = {
  symbol: "INFY",
  side: "BUY",
  type: "LIMIT",
  productType: "CNC",
  qty: 1,
  limitPrice: null,
  stopPrice: null,
  stopLoss: null,
  target: null,
  notes: "",
  sourceSignal: null,
  sourceScore: null,
  sourceConfidence: null,
  sourceStrategy: null,
};

/**
 * Timeout strategy (replaces 12s bootstrap wall):
 * - FAST: resolve UI lane quickly or fall through to partial state
 * - BACKGROUND: keep fetching after fast timeout; apply when ready
 * Never block the shell on a single slow request.
 */
const FAST_TIMEOUT_MS = 1_500;
const BACKGROUND_TIMEOUT_MS = 6_000;
const QUOTE_POLL_MS = 3_000;

type LaneState = "idle" | "loading" | "ready" | "error" | "timeout";

function formatInr(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatNum(value?: number | null, digits = 2): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function logPaperOrder(event: string, payload?: Record<string, unknown>) {
  console.info(`[paper-order] ${event}`, payload ?? {});
}

function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new Error(`${label} timed out after ${ms}ms`));
    }, ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        window.clearTimeout(timer);
        reject(err);
      },
    );
  });
}

/**
 * Race a request against a fast timeout. On timeout, continue the original
 * promise in the background and invoke onLate when it completes.
 * UI never waits longer than fastMs for this lane.
 */
function fetchWithFastTimeout<T>(
  promise: Promise<T>,
  fastMs: number,
  label: string,
  onLate?: (value: T | null, err?: unknown) => void,
): Promise<{ value: T | null; late: boolean; error?: unknown }> {
  let settled = false;
  const tracked = promise.then(
    (value) => {
      if (settled) {
        onLate?.(value);
      }
      return value;
    },
    (err) => {
      if (settled) {
        onLate?.(null, err);
      }
      throw err;
    },
  );

  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      resolve({ value: null, late: true, error: new Error(`${label} fast-timeout ${fastMs}ms`) });
      // Keep background work alive (tracked handlers fire onLate)
      void tracked.catch(() => undefined);
    }, fastMs);

    tracked.then(
      (value) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        resolve({ value, late: false });
      },
      (err) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        resolve({ value: null, late: false, error: err });
      },
    );
  });
}

/**
 * Dedicated full-page Paper Order ticket.
 * Route: /paper-order
 * Does NOT execute until the user confirms in the modal.
 */
export function PaperOrderPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const toast = useToast();

  const navState: PaperOrderNavState = isPaperOrderNavState(location.state)
    ? (location.state as PaperOrderNavState)
    : {};

  const hasNavState = Boolean(
    navState.symbol ||
      navState.prefill ||
      navState.currentPrice != null ||
      navState.orderId != null ||
      navState.signal,
  );

  const initialSymbol = toCanonicalSymbol(
    navState.symbol || searchParams.get("symbol") || navState.prefill?.symbol || "",
  );
  const initialSide =
    (navState.side as "BUY" | "SELL" | undefined) ||
    (searchParams.get("side") === "SELL" ? "SELL" : "BUY");
  const orderIdFromUrl = Number(searchParams.get("orderId") || navState.orderId || 0) || null;
  const returnTo = navState.returnTo || "/scanner";
  const originStrategyName =
    (navState.strategyName ||
      (typeof navState.prefill?.recommendation_meta?.strategy_name === "string"
        ? String(navState.prefill.recommendation_meta.strategy_name)
        : "") ||
      "").trim() || null;
  const originRunId =
    (navState.runId ||
      (typeof navState.prefill?.recommendation_meta?.strategy_id === "string"
        ? String(navState.prefill.recommendation_meta.strategy_id)
        : "") ||
      "").trim() || null;

  const seedEntry =
    (navState.prefill?.suggested_entry != null && Number(navState.prefill.suggested_entry) > 0
      ? Number(navState.prefill.suggested_entry)
      : null) ??
    (navState.currentPrice != null && Number(navState.currentPrice) > 0
      ? Number(navState.currentPrice)
      : null);
  const seedStop =
    navState.prefill?.suggested_stop != null && Number(navState.prefill.suggested_stop) > 0
      ? Number(navState.prefill.suggested_stop)
      : null;
  const seedTarget =
    navState.prefill?.suggested_targets?.[0] != null &&
    Number(navState.prefill.suggested_targets[0]) > 0
      ? Number(navState.prefill.suggested_targets[0])
      : null;
  const seedLevels = completePaperLevels({
    entry: seedEntry,
    side: initialSide,
    stop: seedStop,
    target: seedTarget,
  });

  const [ticket, setTicket] = useState<PaperOrderTicketState>({
    ...DEFAULT_TICKET,
    symbol: initialSymbol || DEFAULT_TICKET.symbol,
    side: initialSide,
    // Prefer LIMIT only when we have a positive entry; otherwise MARKET (uses live quote)
    type: seedEntry != null ? "LIMIT" : "MARKET",
    limitPrice: seedEntry,
    stopLoss: seedLevels.stopLoss,
    target: seedLevels.target,
    sourceSignal:
      (navState.signal as string) ??
      String(navState.prefill?.recommendation_meta?.signal ?? "BUY"),
    sourceScore: navState.score ?? (Number(navState.prefill?.recommendation_meta?.score ?? 0) || null),
    sourceConfidence:
      navState.confidence ??
      (Number(navState.prefill?.recommendation_meta?.confidence ?? 0) || null),
    sourceStrategy: originStrategyName,
    notes: mergeStrategyNote("", originStrategyName, originRunId),
  });

  // Hydrate capital from cache immediately so shell is interactive without waiting on network.
  const cachedAccount = useMemo(
    () => getCached<any>(CACHE_KEYS.paperAccount) ?? getStaleCached<any>(CACHE_KEYS.paperAccount),
    [],
  );
  const seedCash = cachedAccount ? extractPaperAvailableCash(cachedAccount) : null;
  const seedRisk = cachedAccount ? extractPaperMaxRiskPerTrade(cachedAccount) : 0.02;

  const [currentPrice, setCurrentPrice] = useState<number | null>(navState.currentPrice ?? null);
  const [availableCash, setAvailableCash] = useState<number | null>(seedCash);
  /** False until paper account capital has been applied (or hard-failed). */
  const [accountLoaded, setAccountLoaded] = useState(seedCash != null);
  const [maxRiskPercent, setMaxRiskPercent] = useState(seedRisk);
  const [quoteStatus, setQuoteStatus] = useState<"loading" | "live" | "degraded" | "error">(
    navState.currentPrice != null ? "degraded" : "loading",
  );
  /** Shell is always interactive; each card/lane has its own indicator. */
  const [quoteLane, setQuoteLane] = useState<LaneState>(
    navState.currentPrice != null ? "ready" : "loading",
  );
  const [accountLane, setAccountLane] = useState<LaneState>(seedCash != null ? "ready" : "loading");
  const [recoLane, setRecoLane] = useState<LaneState>(navState.prefill ? "ready" : "idle");
  const [orderLane, setOrderLane] = useState<LaneState>(orderIdFromUrl ? "loading" : "idle");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pageError, setPageError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingOrderId, setEditingOrderId] = useState<number | null>(orderIdFromUrl);
  const [meta, setMeta] = useState({
    signal: navState.signal ?? ticket.sourceSignal,
    score: navState.score ?? ticket.sourceScore,
    confidence: navState.confidence ?? ticket.sourceConfidence,
    riskReward: navState.riskReward ?? null,
  });
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const [trailingStopPct, setTrailingStopPct] = useState<string>("2");
  const [cashAllocPct, setCashAllocPct] = useState<string>("10");
  const [chargePreview, setChargePreview] = useState<ChargePreviewResponse | null>(null);
  const [chargePreviewLoading, setChargePreviewLoading] = useState(false);
  const derivedStopRef = useRef(seedStop == null && seedLevels.derivedStop);
  const derivedTargetRef = useRef(seedTarget == null && seedLevels.derivedTarget);
  const userClearedStopRef = useRef(false);
  const userClearedTargetRef = useRef(false);
  /** Bumps on remount / retry so stale async work is ignored (Strict Mode safe). */
  const loadGenRef = useRef(0);
  const pollAbortRef = useRef<AbortController | null>(null);
  /** Double-click / multi-submit guard — survives before React re-render. */
  const confirmInFlightRef = useRef(false);

  const entryReference = useMemo(() => {
    if (ticket.type === "LIMIT" || ticket.type === "GTT" || ticket.type === "STOP_LIMIT") {
      return ticket.limitPrice ?? currentPrice;
    }
    if (ticket.type === "STOP") return ticket.stopPrice ?? currentPrice;
    return currentPrice;
  }, [ticket, currentPrice]);

  // Dynamic charge preview lookup from backend charge engine with debouncing
  useEffect(() => {
    const qty = Number(ticket.qty);
    const price = entryReference;
    const sym = toCanonicalSymbol(ticket.symbol);
    if (!sym || !qty || qty <= 0 || !price || price <= 0) {
      setChargePreview(null);
      return;
    }

    let active = true;
    setChargePreviewLoading(true);

    const timer = setTimeout(() => {
      fetchChargePreview({
        symbol: sym,
        side: ticket.side as "BUY" | "SELL",
        qty,
        price,
        exchange: "NSE",
        segment: "EQUITY_DELIVERY",
      })
        .then((res) => {
          if (active) {
            setChargePreview(res);
            setChargePreviewLoading(false);
          }
        })
        .catch(() => {
          if (active) {
            setChargePreviewLoading(false);
          }
        });
    }, 150);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [ticket.symbol, ticket.side, ticket.qty, entryReference]);

  useEffect(() => {
    const entry = entryReference != null && entryReference > 0 ? entryReference : null;
    if (entry == null) return;

    const isStrategyStop =
      seedStop != null ||
      navState.prefill?.suggested_stop != null ||
      navState.prefill?.recommendation_meta?.stop_source === "strategy";
    const isStrategyTarget =
      seedTarget != null ||
      navState.prefill?.suggested_targets?.[0] != null ||
      navState.prefill?.recommendation_meta?.target_source === "strategy";

    const effectiveStop = userClearedStopRef.current
      ? null
      : isStrategyStop
        ? ticket.stopLoss
        : derivedStopRef.current
          ? null
          : ticket.stopLoss;

    const effectiveTarget = userClearedTargetRef.current
      ? null
      : isStrategyTarget
        ? ticket.target
        : derivedTargetRef.current
          ? null
          : ticket.target;

    const next = completePaperLevels({
      entry,
      side: ticket.side,
      stop: effectiveStop,
      target: effectiveTarget,
    });

    const finalStop = userClearedStopRef.current ? null : next.stopLoss;
    const finalTarget = userClearedTargetRef.current ? null : next.target;

    if (next.derivedStop && !userClearedStopRef.current) derivedStopRef.current = true;
    if (next.derivedTarget && !userClearedTargetRef.current) derivedTargetRef.current = true;

    if (finalStop === ticket.stopLoss && finalTarget === ticket.target) return;
    setTicket((prev) => ({
      ...prev,
      stopLoss: finalStop,
      target: finalTarget,
    }));
  }, [entryReference, ticket.side, ticket.stopLoss]);

  const risk = useMemo(() => {
    const qty = Math.max(0, Number(ticket.qty) || 0);
    const entry = entryReference && entryReference > 0 ? entryReference : 0;
    const estimatedCost = entry * qty;
    const riskPerShare =
      entry && ticket.stopLoss != null ? Math.abs(entry - ticket.stopLoss) : 0;
    const rewardPerShare =
      entry && ticket.target != null ? Math.abs(ticket.target - entry) : 0;
    const riskAmount = riskPerShare * qty;
    const potentialProfit = rewardPerShare * qty;
    const potentialLoss = riskAmount;
    const riskReward = riskPerShare > 0 ? rewardPerShare / riskPerShare : meta.riskReward ?? 0;
    const riskPercent = availableCash && riskAmount ? (riskAmount / availableCash) * 100 : 0;

    // Use charge preview if matches current order value; otherwise calculate client-side fallback
    const turnover = estimatedCost;
    let brokerage = 0;
    let stt = 0;
    let exchangeTurnover = 0;
    let sebiTurnover = 0;
    let gst = 0;
    let stampDuty = 0;
    let dpCharges = 0;
    let totalCharges = 0;
    let breakEvenPrice = 0;

    if (chargePreview?.charges && Math.abs(chargePreview.turnover - turnover) < 1.0) {
      brokerage = Number(chargePreview.charges.brokerage) || 0;
      stt = Number(chargePreview.charges.stt) || 0;
      exchangeTurnover = Number(chargePreview.charges.exchange_charges) || 0;
      sebiTurnover = Number(chargePreview.charges.sebi_charges) || 0;
      gst = Number(chargePreview.charges.gst) || 0;
      stampDuty = Number(chargePreview.charges.stamp_duty) || 0;
      dpCharges = Number(chargePreview.charges.dp_charges) || 0;
      totalCharges = Number(chargePreview.charges.total_charges) || 0;
      breakEvenPrice = Number(chargePreview.break_even_price ?? chargePreview.assumptions?.break_even_price) || 0;
    } else if (turnover > 0 && qty > 0) {
      // Local fallback calculation matching INDIA_EQUITY_DELIVERY_DEFAULT
      brokerage = 0;
      stt = Math.round(turnover * 0.0010 * 100) / 100;
      exchangeTurnover = Math.round(turnover * 0.0000307 * 100) / 100;
      sebiTurnover = Math.round(turnover * 0.0000010 * 100) / 100;
      const taxable = brokerage + exchangeTurnover + sebiTurnover;
      gst = Math.round(taxable * 0.18 * 100) / 100;
      stampDuty = ticket.side === "BUY" ? Math.round(turnover * 0.00015 * 100) / 100 : 0;
      dpCharges = 0;
      totalCharges = Math.round((brokerage + stt + exchangeTurnover + sebiTurnover + gst + stampDuty + dpCharges) * 100) / 100;
      if (ticket.side === "BUY") {
        const estSellCharges = Math.round(turnover * 0.0010363 * 100) / 100;
        breakEvenPrice = Math.round(((turnover + totalCharges + estSellCharges) / qty) * 100) / 100;
      } else {
        breakEvenPrice = entry;
      }
    }

    if (ticket.side === "BUY" && breakEvenPrice <= 0 && turnover > 0 && qty > 0) {
      const estSellCharges = Math.round(turnover * 0.0010363 * 100) / 100;
      breakEvenPrice = Math.round(((turnover + totalCharges + estSellCharges) / qty) * 100) / 100;
    }

    return {
      estimatedCost,
      riskPerShare,
      rewardPerShare,
      riskAmount,
      potentialProfit,
      potentialLoss,
      riskReward,
      riskPercent,
      brokerage,
      charges: totalCharges,
      stt,
      exchangeTurnover,
      sebiTurnover,
      gst,
      stampDuty,
      dpCharges,
      breakEvenPrice,
      totalCost: ticket.side === "BUY" ? estimatedCost + totalCharges : Math.max(0, estimatedCost - totalCharges),
    };
  }, [ticket, entryReference, availableCash, meta.riskReward, chargePreview]);

  const applyAccount = useCallback(
    (acct: any | null, gen: number, symbol: string, status: LaneState = "ready") => {
      if (gen !== loadGenRef.current) return;
      if (acct) {
        const cash = extractPaperAvailableCash(acct);
        const riskPct = extractPaperMaxRiskPerTrade(acct);
        setAvailableCash(cash);
        setMaxRiskPercent(riskPct);
        setAccountLoaded(true);
        setAccountLane("ready");
        logPaperCapital("paper-order", "account_loaded", acct, {
          symbol,
          gen,
          resolved_available_cash: cash,
        });
        logPaperOrder("api_response", {
          kind: "account",
          available_cash: cash,
          balance: acct.balance ?? acct.cash_balance ?? null,
          available_funds: acct.available_funds ?? null,
        });
      } else {
        // Keep seed cash if present; mark lane error only when no usable capital.
        setAccountLoaded(true);
        setAccountLane((prev) => (prev === "ready" ? "ready" : status === "timeout" ? "timeout" : "error"));
        logPaperOrder("api_response", { kind: "account", available_cash: null, failed: true });
      }
    },
    [],
  );

  const applyQuote = useCallback((quote: any | null, gen: number, symbol: string) => {
    if (gen !== loadGenRef.current) return;
    if (quote?.current_price != null && Number(quote.current_price) > 0) {
      const priceNum = Number(quote.current_price);
      setCurrentPrice(priceNum);
      setQuoteStatus(quote.is_stale ? "degraded" : "live");
      setQuoteLane("ready");
      setTicket((prev) => {
        if (prev.symbol === symbol && (prev.limitPrice == null || prev.limitPrice <= 0)) {
          return {
            ...prev,
            limitPrice: prev.type === "LIMIT" ? priceNum : null,
          };
        }
        return prev;
      });
      logPaperOrder("api_response", {
        kind: "quote",
        symbol,
        price: priceNum,
        status: quote.is_stale ? "degraded" : "live",
      });
    } else {
      setQuoteStatus((prev) => (prev === "degraded" || prev === "live" ? prev : "error"));
      setQuoteLane((prev) => (prev === "ready" ? "ready" : "error"));
      logPaperOrder("api_response", { kind: "quote", symbol, price: null });
    }
  }, []);

  /**
   * Independent quote + account lanes with fast timeout + background retry.
   * Never blocks shell; late responses still apply when they arrive.
   */
  const loadQuoteAndAccount = useCallback(
    async (symbol: string, gen?: number, opts?: { forceAccount?: boolean; forceQuote?: boolean }) => {
      const canon = toCanonicalSymbol(symbol) || "INFY";
      const myGen = gen ?? loadGenRef.current;
      logPaperOrder("api_request", { kind: "quote+account", symbol: canon, gen: myGen });

      // --- Quote cache seed ---
      if (!opts?.forceQuote) {
        const cachedQuote =
          getCached<any>(CACHE_KEYS.paperQuote(canon)) ??
          getStaleCached<any>(CACHE_KEYS.paperQuote(canon));
        if (cachedQuote?.current_price != null && Number(cachedQuote.current_price) > 0) {
          applyQuote(cachedQuote, myGen, canon);
          recordCacheHit(myGen, "quote_cache", canon);
        } else {
          recordCacheMiss(myGen, "quote");
          setQuoteLane((s) => (s === "ready" ? s : "loading"));
          setQuoteStatus((s) => (s === "live" || s === "degraded" ? s : "loading"));
        }
      } else {
        setQuoteLane("loading");
        setQuoteStatus("loading");
      }

      // --- Account cache seed ---
      if (!opts?.forceAccount) {
        const cachedAcct =
          getCached<any>(CACHE_KEYS.paperAccount) ?? getStaleCached<any>(CACHE_KEYS.paperAccount);
        if (cachedAcct) {
          applyAccount(cachedAcct, myGen, canon);
          recordCacheHit(myGen, "account_cache");
        } else {
          recordCacheMiss(myGen, "account");
          setAccountLane((s) => (s === "ready" ? s : "loading"));
        }
      } else {
        setAccountLane("loading");
      }

      const quotePromise = fetchPaperQuote(canon, { force: opts?.forceQuote }).catch((err) => {
        logPaperOrder("api_failure", {
          kind: "quote",
          symbol: canon,
          message: err instanceof Error ? err.message : String(err),
        });
        return null;
      });

      const acctPromise = fetchPaperAccountSummary({ force: opts?.forceAccount }).catch((err) => {
        logPaperOrder("api_failure", {
          kind: "account",
          message: err instanceof Error ? err.message : String(err),
        });
        return null;
      });

      // Fire both immediately; each lane has its own fast timeout + background completion.
      const quoteLaneP = (async () => {
        const started = performance.now();
        const { value, late, error } = await fetchWithFastTimeout(
          quotePromise,
          FAST_TIMEOUT_MS,
          "Quote",
          (lateValue) => {
            if (myGen !== loadGenRef.current) return;
            if (lateValue) {
              applyQuote(lateValue, myGen, canon);
              recordSample(myGen, {
                name: "quote_background",
                category: "api",
                durationMs: Math.round(performance.now() - started),
                status: "ok",
                detail: "late quote applied",
              });
            }
          },
        );
        if (myGen !== loadGenRef.current) return;
        const durationMs = Math.round(performance.now() - started);
        if (value) {
          applyQuote(value, myGen, canon);
          recordSample(myGen, {
            name: "quote_api",
            category: "api",
            durationMs,
            status: "ok",
          });
        } else if (late) {
          setQuoteLane((s) => (s === "ready" ? s : "timeout"));
          recordSample(myGen, {
            name: "quote_api",
            category: "api",
            durationMs: FAST_TIMEOUT_MS,
            status: "timeout",
            detail: "fast timeout; background retry active",
          });
          // Background hard ceiling — mark error if still nothing
          void withTimeout(quotePromise, BACKGROUND_TIMEOUT_MS - FAST_TIMEOUT_MS, "Quote bg")
            .then((q) => {
              if (myGen !== loadGenRef.current) return;
              if (q) applyQuote(q, myGen, canon);
            })
            .catch(() => {
              if (myGen !== loadGenRef.current) return;
              setQuoteLane((s) => (s === "ready" ? s : "error"));
              setQuoteStatus((s) => (s === "live" || s === "degraded" ? s : "error"));
            });
        } else {
          setQuoteLane((s) => (s === "ready" ? s : "error"));
          recordSample(myGen, {
            name: "quote_api",
            category: "api",
            durationMs,
            status: "error",
            detail: error instanceof Error ? error.message : String(error ?? ""),
          });
        }
      })();

      const acctLaneP = (async () => {
        const started = performance.now();
        const { value, late, error } = await fetchWithFastTimeout(
          acctPromise,
          FAST_TIMEOUT_MS,
          "Paper account",
          (lateValue) => {
            if (myGen !== loadGenRef.current) return;
            if (lateValue) {
              applyAccount(lateValue, myGen, canon);
              recordSample(myGen, {
                name: "account_background",
                category: "api",
                durationMs: Math.round(performance.now() - started),
                status: "ok",
                detail: "late account applied",
              });
            }
          },
        );
        if (myGen !== loadGenRef.current) return;
        const durationMs = Math.round(performance.now() - started);
        if (value) {
          applyAccount(value, myGen, canon);
          recordSample(myGen, {
            name: "account_api",
            category: "api",
            durationMs,
            status: "ok",
          });
        } else if (late) {
          setAccountLane((s) => (s === "ready" ? s : "timeout"));
          recordSample(myGen, {
            name: "account_api",
            category: "api",
            durationMs: FAST_TIMEOUT_MS,
            status: "timeout",
            detail: "fast timeout; background retry active",
          });
          void withTimeout(acctPromise, BACKGROUND_TIMEOUT_MS - FAST_TIMEOUT_MS, "Account bg")
            .then((a) => {
              if (myGen !== loadGenRef.current) return;
              if (a) applyAccount(a, myGen, canon);
            })
            .catch(() => {
              if (myGen !== loadGenRef.current) return;
              applyAccount(null, myGen, canon, "timeout");
            });
        } else {
          applyAccount(null, myGen, canon, "error");
          recordSample(myGen, {
            name: "account_api",
            category: "api",
            durationMs,
            status: "error",
            detail: error instanceof Error ? error.message : String(error ?? ""),
          });
        }
      })();

      // Do not await background ceilings — only wait for the fast races so caller can finish.
      await Promise.all([quoteLaneP, acctLaneP]);
    },
    [applyAccount, applyQuote],
  );

  /**
   * Progressive bootstrap: paint shell from nav/cache immediately, then
   * load independent lanes in parallel (quote | account | order | prefill refine).
   * No 12s bootstrap wall — partial render always.
   */
  const runBootstrap = useCallback(
    async (isActive: () => boolean, opts?: { forceSymbol?: string; forceRefresh?: boolean }) => {
      const gen = ++loadGenRef.current;
      startPaperOrderPerf(gen);
      const symbolForLoad =
        toCanonicalSymbol(opts?.forceSymbol || initialSymbol) || DEFAULT_TICKET.symbol;

      logPaperOrder("loading_start", {
        gen,
        path: location.pathname,
        search: location.search,
        hasNavState,
        symbol: symbolForLoad,
        side: initialSide,
        orderId: orderIdFromUrl,
        hasPrefill: Boolean(navState.prefill),
        strategy: "progressive+fast-timeout",
      });
      if (!hasNavState && !searchParams.get("symbol") && !orderIdFromUrl) {
        logPaperOrder("missing_navigation_state", {
          search: location.search,
          note: "Falling back to URL/query or default symbol",
        });
      }

      setLoadError(null);
      if (opts?.forceRefresh) {
        setAccountLoaded(false);
        setAvailableCash(null);
        setAccountLane("loading");
        setQuoteLane("loading");
      }
      setPageError(null);

      try {
        // --- EDIT PATH: order-by-id ∥ quote+account ---
        if (orderIdFromUrl) {
          setOrderLane("loading");
          logPaperOrder("api_request", { kind: "order-by-id", orderId: orderIdFromUrl });
          const applyOrder = (orderResult: Awaited<ReturnType<typeof fetchPaperOrderById>>) => {
            setOrderLane("ready");
            setEditingOrderId(orderIdFromUrl);
            const orderSym = toCanonicalSymbol(orderResult.symbol) || symbolForLoad;
            setTicket({
              symbol: orderSym,
              side: orderResult.side,
              type: orderResult.type,
              productType: orderResult.product_type ?? "CNC",
              qty: orderResult.qty,
              limitPrice: orderResult.price ?? null,
              stopPrice: orderResult.stop_price ?? null,
              stopLoss: orderResult.stop_loss ?? null,
              target: orderResult.target ?? null,
              notes: orderResult.notes ?? "",
              sourceSignal: orderResult.source_signal ?? null,
              sourceScore: orderResult.source_score ?? null,
              sourceConfidence: orderResult.source_confidence ?? null,
              sourceStrategy: extractStrategyFromNotes(orderResult.notes) || originStrategyName,
            });
            setMeta({
              signal: orderResult.source_signal,
              score: orderResult.source_score,
              confidence: orderResult.source_confidence,
              riskReward: null,
            });
            if (orderSym !== symbolForLoad) {
              void loadQuoteAndAccount(orderSym, gen);
            }
          };

          const orderStarted = performance.now();
          const orderFetch = fetchPaperOrderById(orderIdFromUrl).catch((err) => {
            logPaperOrder("api_failure", {
              kind: "order-by-id",
              message: err instanceof Error ? err.message : String(err),
            });
            return null;
          });

          await Promise.all([
            fetchWithFastTimeout(orderFetch, FAST_TIMEOUT_MS, "Order load", (lateOrder) => {
              if (!isActive() || gen !== loadGenRef.current || !lateOrder) return;
              applyOrder(lateOrder);
              recordSample(gen, {
                name: "order_by_id_background",
                category: "api",
                durationMs: Math.round(performance.now() - orderStarted),
                status: "ok",
              });
            }).then((result) => {
              if (!isActive() || gen !== loadGenRef.current) return;
              const durationMs = Math.round(performance.now() - orderStarted);
              if (result.value) {
                applyOrder(result.value);
                recordSample(gen, {
                  name: "order_by_id",
                  category: "api",
                  durationMs,
                  status: "ok",
                });
              } else if (result.late) {
                setOrderLane("timeout");
                recordSample(gen, {
                  name: "order_by_id",
                  category: "api",
                  durationMs: FAST_TIMEOUT_MS,
                  status: "timeout",
                  detail: "fast timeout; background retry active",
                });
              } else {
                setOrderLane("error");
                setEditingOrderId(null);
                setPageError(
                  `Pending order #${orderIdFromUrl} was not found. Showing a blank ticket.`,
                );
                setTicket((t) => ({ ...t, symbol: symbolForLoad, side: initialSide }));
                recordSample(gen, {
                  name: "order_by_id",
                  category: "api",
                  durationMs,
                  status: "error",
                });
              }
            }),
            loadQuoteAndAccount(symbolForLoad, gen, {
              forceAccount: opts?.forceRefresh,
              forceQuote: opts?.forceRefresh,
            }),
          ]);
          return;
        }

        // --- PREFILL PATH: local instant + optional lab refine in background ---
        const prefill: RecommendationPrefillRequest | null | undefined = navState.prefill;
        if (prefill) {
          const local = prefillPaperTradeLocal(prefill);
          setRecoLane("ready");
          recordSample(gen, {
            name: "prefill_local",
            category: "cache",
            durationMs: 0,
            status: "cache_hit",
            cacheHit: true,
            detail: "nav recommendation applied sync",
          });
          const posOrNull = (n: number | null | undefined) =>
            n != null && Number(n) > 0 ? Number(n) : null;
          const limit = posOrNull(local.limit_price) ?? posOrNull(prefill.suggested_entry);
          const stopVal = posOrNull(local.stop_loss) ?? posOrNull(prefill.suggested_stop);
          const targetVal = posOrNull(local.target) ?? posOrNull(prefill.suggested_targets?.[0]);
          const filled = completePaperLevels({
            entry: limit,
            side: local.side,
            stop: stopVal,
            target: targetVal,
          });
          derivedStopRef.current = stopVal == null && filled.derivedStop;
          derivedTargetRef.current = targetVal == null && filled.derivedTarget;
          setTicket({
            symbol: toCanonicalSymbol(local.symbol) || symbolForLoad,
            side: local.side,
            type: limit != null ? local.type || "LIMIT" : "MARKET",
            productType: "CNC",
            qty: local.qty,
            limitPrice: limit,
            stopPrice: null,
            stopLoss: filled.stopLoss,
            target: filled.target,
            notes: mergeStrategyNote(
              local.note,
              originStrategyName ||
                (typeof prefill.recommendation_meta?.strategy_name === "string"
                  ? String(prefill.recommendation_meta.strategy_name)
                  : null),
              originRunId,
            ),
            sourceSignal: String(prefill.recommendation_meta?.signal ?? "BUY"),
            sourceScore: Number(prefill.recommendation_meta?.score ?? 0) || null,
            sourceConfidence: Number(prefill.recommendation_meta?.confidence ?? 0) || null,
            sourceStrategy:
              originStrategyName ||
              (typeof prefill.recommendation_meta?.strategy_name === "string"
                ? String(prefill.recommendation_meta.strategy_name)
                : null),
          });
          setMeta({
            signal: String(prefill.recommendation_meta?.signal ?? "BUY"),
            score: Number(prefill.recommendation_meta?.score ?? 0) || null,
            confidence: Number(prefill.recommendation_meta?.confidence ?? 0) || null,
            riskReward: navState.riskReward ?? null,
          });
          if (limit != null) {
            setCurrentPrice((p) => p ?? limit);
            setQuoteStatus((s) => (s === "live" ? s : "degraded"));
            setQuoteLane((s) => (s === "ready" ? s : "ready"));
          }

          const lanes: Promise<unknown>[] = [
            loadQuoteAndAccount(local.symbol || symbolForLoad, gen, {
              forceAccount: opts?.forceRefresh,
              forceQuote: opts?.forceRefresh,
            }),
          ];
          await Promise.all(lanes);
          return;
        }

        // --- SYMBOL PATH ---
        if (!symbolForLoad) {
          setLoadError("Unable to load order details. No symbol was provided.");
          setQuoteStatus("error");
          setQuoteLane("error");
          return;
        }

        setTicket((t) => ({
          ...t,
          symbol: symbolForLoad,
          side: initialSide,
          limitPrice: t.limitPrice ?? navState.currentPrice ?? null,
          sourceSignal: (navState.signal as string) ?? t.sourceSignal ?? initialSide,
          sourceScore: navState.score ?? t.sourceScore,
          sourceConfidence: navState.confidence ?? t.sourceConfidence,
        }));
        setMeta((m) => ({
          signal: navState.signal ?? m.signal ?? initialSide,
          score: navState.score ?? m.score,
          confidence: navState.confidence ?? m.confidence,
          riskReward: navState.riskReward ?? m.riskReward,
        }));
        await loadQuoteAndAccount(symbolForLoad, gen, {
          forceAccount: opts?.forceRefresh,
          forceQuote: opts?.forceRefresh,
        });
      } catch (e) {
        if (!isActive() || gen !== loadGenRef.current) return;
        const msg = e instanceof Error ? e.message : "Unable to load order details.";
        logPaperOrder("loading_failure", { reason: "bootstrap_error", message: msg, gen });
        if (navState.currentPrice != null) {
          setCurrentPrice(navState.currentPrice);
          setQuoteStatus("degraded");
          setQuoteLane("ready");
        }
        // Soft: never blank the page for a single failure
        setPageError(msg);
      } finally {
        if (isActive() && gen === loadGenRef.current) {
          logPaperOrder("loading_complete", {
            gen,
            symbol: symbolForLoad,
            hasPrefill: Boolean(navState.prefill),
          });
          // Ranked report after fast races settle; late backgrounds may still apply after.
          printRankedPerfReport(gen, { symbol: symbolForLoad });
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      initialSymbol,
      initialSide,
      orderIdFromUrl,
      hasNavState,
      location.pathname,
      location.search,
      loadQuoteAndAccount,
    ],
  );

  // Initial load + re-load when URL identity changes.
  // Strict Mode safe: each effect instance has its own `active` flag.
  useEffect(() => {
    let active = true;
    const isActive = () => active;

    logPaperOrder("navigation", {
      pathname: location.pathname,
      search: location.search,
      symbol: initialSymbol || null,
      side: initialSide,
      hasNavState,
      orderId: orderIdFromUrl,
    });

    void runBootstrap(isActive);

    return () => {
      active = false;
      loadGenRef.current += 1;
      pollAbortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search, orderIdFromUrl, initialSymbol, initialSide, runBootstrap]);

  function handleRetry() {
    setLoadError(null);
    setPageError(null);
    void runBootstrap(() => true, {
      forceSymbol: ticket.symbol || initialSymbol,
      forceRefresh: true,
    });
  }

  // Live quote poll while on the page (cancelled on leave / symbol change)
  useEffect(() => {
    const sym = toCanonicalSymbol(ticket.symbol);
    if (!sym) return;

    pollAbortRef.current?.abort();
    const ac = new AbortController();
    pollAbortRef.current = ac;

    const id = window.setInterval(() => {
      if (ac.signal.aborted) return;
      void fetchPaperQuote(sym, { force: true })
        .then((q) => {
          if (ac.signal.aborted) return;
          if (q?.current_price != null && Number(q.current_price) > 0) {
            setCurrentPrice(Number(q.current_price));
            setQuoteStatus(q.is_stale ? "degraded" : "live");
          }
        })
        .catch(() => {
          if (!ac.signal.aborted) {
            setQuoteStatus((s) => (s === "live" ? "degraded" : s));
          }
        });
    }, QUOTE_POLL_MS);

    return () => {
      ac.abort();
      window.clearInterval(id);
    };
  }, [ticket.symbol]);

  function handleBack() {
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate(returnTo || "/scanner");
    }
  }

  /**
   * Full frontend validation for Place Paper Order.
   * Returns structured PASS/FAIL results + field errors with concrete values.
   * Never collapses failures into a single generic message at the call site.
   */
  function validateTicket(): {
    ok: boolean;
    errors: Record<string, string>;
    messages: string[];
    results: Array<{ rule: string; status: "PASS" | "FAIL" | "SKIP"; detail?: string }>;
  } {
    const errors: Record<string, string> = {};
    const results: Array<{ rule: string; status: "PASS" | "FAIL" | "SKIP"; detail?: string }> = [];
    const qty = Number(ticket.qty);
    const entry = entryReference != null && entryReference > 0 ? entryReference : null;
    const entryLabel = entry != null ? formatInr(entry) : "—";

    // Symbol
    if (!ticket.symbol?.trim()) {
      errors.symbol = "Symbol is required.";
      results.push({ rule: "Symbol", status: "FAIL", detail: errors.symbol });
    } else {
      results.push({ rule: "Symbol", status: "PASS", detail: ticket.symbol });
    }

    // Side / Type / Product — informational (always valid enums from selects)
    results.push({ rule: "Side", status: "PASS", detail: ticket.side });
    results.push({ rule: "Order Type", status: "PASS", detail: ticket.type });
    results.push({
      rule: "Product",
      status: "PASS",
      detail: ticket.productType ?? "CNC",
    });

    // Quantity
    if (!Number.isFinite(qty) || qty < 1) {
      errors.qty = "Quantity must be at least 1.";
      results.push({ rule: "Quantity", status: "FAIL", detail: errors.qty });
    } else {
      results.push({ rule: "Quantity", status: "PASS", detail: String(qty) });
    }

    // Limit / stop trigger price
    if (ticket.type === "STOP_LIMIT") {
      if (ticket.stopPrice == null || ticket.stopPrice <= 0) {
        errors.stopPrice = "Stop Trigger is required and must be greater than 0.";
        results.push({ rule: "Stop Trigger", status: "FAIL", detail: errors.stopPrice });
      } else {
        results.push({ rule: "Stop Trigger", status: "PASS", detail: formatInr(ticket.stopPrice) });
      }
      if (ticket.limitPrice == null || ticket.limitPrice <= 0) {
        errors.price = "Limit Price is required and must be greater than 0.";
        results.push({ rule: "Limit Price", status: "FAIL", detail: errors.price });
      } else {
        results.push({ rule: "Limit Price", status: "PASS", detail: formatInr(ticket.limitPrice) });
      }
    } else if (ticket.type !== "MARKET") {
      const priceField = ticket.type === "STOP" ? ticket.stopPrice : ticket.limitPrice;
      const priceName = ticket.type === "STOP" ? "Stop Trigger" : "Limit Price";
      if (priceField == null || priceField <= 0) {
        errors.price = `${priceName} is required and must be greater than 0.`;
        results.push({ rule: priceName, status: "FAIL", detail: errors.price });
      } else {
        results.push({
          rule: priceName,
          status: "PASS",
          detail: formatInr(priceField),
        });
      }
    } else {
      results.push({ rule: "Limit Price", status: "SKIP", detail: "Not required for MARKET" });
    }

    // Entry reference used for SL/Target rules
    if (entry == null) {
      results.push({
        rule: "Entry Price",
        status: "FAIL",
        detail: "Entry price is unavailable. Set limit/stop price or wait for a live quote.",
      });
      if (!errors.price) {
        errors.price =
          "Entry price is unavailable. Set a limit/stop price or wait for a live quote before placing.";
      }
    } else {
      results.push({ rule: "Entry Price", status: "PASS", detail: entryLabel });
    }

    // Stop Loss vs Entry (BUY: SL < entry; SELL: SL > entry)
    if (ticket.stopLoss == null) {
      results.push({ rule: "Stop Loss", status: "SKIP", detail: "Optional — not set" });
    } else if (entry == null) {
      results.push({
        rule: "Stop Loss",
        status: "SKIP",
        detail: "Skipped — entry price unavailable",
      });
    } else if (ticket.side === "BUY" && ticket.stopLoss >= entry) {
      errors.stopLoss = `Stop Loss (${formatInr(ticket.stopLoss)}) must be below Entry Price (${entryLabel}) for BUY.`;
      results.push({ rule: "Stop Loss", status: "FAIL", detail: errors.stopLoss });
    } else if (ticket.side === "SELL" && ticket.stopLoss <= entry) {
      errors.stopLoss = `Stop Loss (${formatInr(ticket.stopLoss)}) must be above Entry Price (${entryLabel}) for SELL.`;
      results.push({ rule: "Stop Loss", status: "FAIL", detail: errors.stopLoss });
    } else {
      results.push({
        rule: "Stop Loss",
        status: "PASS",
        detail: `${formatInr(ticket.stopLoss)} vs entry ${entryLabel} (${ticket.side})`,
      });
    }

    // Target vs Entry (BUY: target > entry; SELL: target < entry)
    if (ticket.target == null) {
      results.push({ rule: "Target", status: "SKIP", detail: "Optional — not set" });
    } else if (entry == null) {
      results.push({
        rule: "Target",
        status: "SKIP",
        detail: "Skipped — entry price unavailable",
      });
    } else if (ticket.side === "BUY" && ticket.target <= entry) {
      errors.target = `Target (${formatInr(ticket.target)}) must be above Entry Price (${entryLabel}) for BUY.`;
      results.push({ rule: "Target", status: "FAIL", detail: errors.target });
    } else if (ticket.side === "SELL" && ticket.target >= entry) {
      errors.target = `Target (${formatInr(ticket.target)}) must be below Entry Price (${entryLabel}) for SELL.`;
      results.push({ rule: "Target", status: "FAIL", detail: errors.target });
    } else {
      results.push({
        rule: "Target",
        status: "PASS",
        detail: `${formatInr(ticket.target)} vs entry ${entryLabel} (${ticket.side})`,
      });
    }

    // Available cash (BUY only) — never treat "not loaded" as ₹0
    if (ticket.side !== "BUY") {
      results.push({
        rule: "Available Cash",
        status: "SKIP",
        detail: "Cash check applies to BUY only",
      });
    } else if (!accountLoaded || availableCash == null) {
      errors.cash = "Paper account capital is still loading. Wait a moment and try again.";
      results.push({ rule: "Available Cash", status: "FAIL", detail: errors.cash });
    } else if (risk.estimatedCost > availableCash + 0.01) {
      errors.cash = `Estimated cost ${formatInr(risk.estimatedCost)} exceeds available cash ${formatInr(availableCash)}.`;
      results.push({
        rule: "Available Cash",
        status: "FAIL",
        detail: errors.cash,
      });
    } else {
      results.push({
        rule: "Available Cash",
        status: "PASS",
        detail: `Cost ${formatInr(risk.estimatedCost)} ≤ cash ${formatInr(availableCash)}`,
      });
    }

    // Risk % of account (when SL is set so riskAmount > 0)
    if (!accountLoaded) {
      results.push({
        rule: "Risk %",
        status: "SKIP",
        detail: "Account not loaded yet",
      });
    } else if (!(risk.riskAmount > 0)) {
      results.push({
        rule: "Risk %",
        status: "SKIP",
        detail: "No stop-loss risk amount to evaluate",
      });
    } else if (risk.riskPercent > maxRiskPercent * 100 + 0.01) {
      errors.risk = `Risk ${risk.riskPercent.toFixed(2)}% of account exceeds guideline ${(maxRiskPercent * 100).toFixed(1)}% (risk amount ${formatInr(risk.riskAmount)}).`;
      results.push({ rule: "Risk %", status: "FAIL", detail: errors.risk });
    } else {
      results.push({
        rule: "Risk %",
        status: "PASS",
        detail: `${risk.riskPercent.toFixed(2)}% ≤ ${(maxRiskPercent * 100).toFixed(1)}% guideline`,
      });
    }

    // Cash allocation helper is optional UI only — not a hard order field
    results.push({
      rule: "Cash Allocation",
      status: "SKIP",
      detail: "Helper only — not a placement constraint",
    });

    const messages = Object.values(errors);
    const ok = messages.length === 0;

    logPaperOrder("validation_result", {
      ok,
      side: ticket.side,
      type: ticket.type,
      qty,
      entry,
      stopLoss: ticket.stopLoss,
      target: ticket.target,
      availableCash,
      estimatedCost: risk.estimatedCost,
      riskPercent: risk.riskPercent,
      maxRiskPercent,
      results,
      errors,
    });
    console.info(
      "[paper-order] Validation:\n" +
        results.map((r) => `${r.rule}: ${r.status}${r.detail ? ` — ${r.detail}` : ""}`).join("\n"),
    );

    setFieldErrors(errors);
    return { ok, errors, messages, results };
  }

  function handlePlaceClick() {
    if (!accountLoaded || (ticket.side === "BUY" && availableCash == null)) {
      toast.error("Loading paper account", "Available cash is still loading. Please wait.");
      return;
    }

    const validation = validateTicket();
    if (!validation.ok) {
      const title =
        validation.messages.length === 1
          ? "Order validation failed"
          : `${validation.messages.length} validation errors`;
      const summary =
        validation.messages.length === 1
          ? validation.messages[0]
          : validation.messages.map((m, i) => `${i + 1}. ${m}`).join(" ");
      // Title + every exact failure — never a generic-only "Fix validation errors" toast.
      toast.toast(title, {
        level: "error",
        description: summary,
        duration: Math.min(14_000, 6_000 + validation.messages.length * 2_500),
        dedupeKey: "paper-order-validation",
      });
      // Persistent on-page alert so failures remain after the toast dismisses.
      setPageError(
        validation.messages.length === 1
          ? validation.messages[0]
          : `Cannot place order:\n${validation.messages.map((m) => `• ${m}`).join("\n")}`,
      );
      return;
    }

    setPageError(null);
    setConfirmOpen(true);
  }

  async function handleConfirmOrder() {
    // Task 11: only one active confirmation — ignore double-clicks / re-entry
    if (confirmInFlightRef.current || isSubmitting) {
      logPaperOrder("confirm_ignored_duplicate", { reason: "in_flight" });
      return;
    }
    confirmInFlightRef.current = true;
    setIsSubmitting(true);
    setPageError(null);
    const t0 = performance.now();
    // Coerce non-positive optional prices to null (backend gt=0 rejects 0)
    const pos = (n: number | null | undefined) =>
      n != null && Number(n) > 0 ? Number(n) : null;
    const strategyName = ticket.sourceStrategy || originStrategyName;
    const normalized: PaperOrderTicketState = {
      ...ticket,
      symbol: toCanonicalSymbol(ticket.symbol),
      limitPrice: pos(ticket.limitPrice),
      stopPrice: pos(ticket.stopPrice),
      stopLoss: pos(ticket.stopLoss),
      target: pos(ticket.target),
      sourceStrategy: strategyName,
      notes: mergeStrategyNote(ticket.notes, strategyName, originRunId),
    };
    // Freeze idempotency key for this attempt (double-click reuses same key)
    const attemptKey = idempotencyKey;

    try {
      let orderStatus: string | undefined;
      let successTitle = "✓ Paper Order Placed Successfully";
      let successDesc: string | undefined;

      logPaperOrder("confirm_payload", {
        symbol: normalized.symbol,
        type: normalized.type,
        limitPrice: normalized.limitPrice,
        stopLoss: normalized.stopLoss,
        target: normalized.target,
      });

      if (editingOrderId) {
        await updatePaperOrder(editingOrderId, {
          qty: normalized.qty,
          limit_price: normalized.limitPrice,
          stop_price: normalized.stopPrice,
          stop_loss: normalized.stopLoss,
          target: normalized.target,
          type: normalized.type,
          product_type: normalized.productType,
        } as Partial<PaperOrderTicketState> & Record<string, unknown>);
        successTitle = "✓ Paper Order Updated Successfully";
      } else {
        const response = await placePaperOrder(normalized, attemptKey);
        // New key only after success — retries keep attemptKey for idempotency
        setIdempotencyKey(crypto.randomUUID());
        orderStatus = response.order?.status ?? (response as { status?: string }).status;
        if (orderStatus === "WAITING_FOR_MARKET" || orderStatus === "PENDING_MARKET_OPEN") {
          successTitle = "Order accepted";
          successDesc =
            "The market is currently closed. Your order has been placed successfully and will be executed automatically when the market opens.";
        } else if (orderStatus === "FILLED" || orderStatus === "EXECUTED") {
          successTitle = `Your ${normalized.side} order for ${normalized.symbol} has been executed successfully.`;
          successDesc = response.position
            ? "Position has been added to your portfolio."
            : response.message || "Order filled.";
        } else {
          successDesc = response.message || undefined;
        }
      }

      const apiMs = Math.round(performance.now() - t0);
      logPaperOrder("confirm_success", {
        symbol: normalized.symbol,
        api_ms: apiMs,
        status: orderStatus ?? (editingOrderId ? "UPDATED" : "PLACED"),
        // Targets: api <500ms, total perceived <1s
        budget_ok: apiMs < 1000,
      });

      // Close dialog + toast immediately (do not wait for desk / navigate)
      const tUi = performance.now();
      setConfirmOpen(false);
      setIsSubmitting(false);
      confirmInFlightRef.current = false;
      toast.success(successTitle, successDesc);
      logPaperOrder("confirm_ui_closed", {
        symbol: normalized.symbol,
        ui_ms: Math.round(performance.now() - tUi),
        total_ms: Math.round(performance.now() - t0),
      });

      // Background: cache invalidation + desk refresh — never blocks dialog close
      queueMicrotask(() => {
        try {
          invalidatePaperCaches();
        } catch {
          /* ignore */
        }
        window.dispatchEvent(
          new CustomEvent("paper:order-success", {
            detail: { symbol: normalized.symbol, apiMs },
          }),
        );
      });

      // Navigate after paint so toast/dialog teardown aren't delayed by route load
      requestAnimationFrame(() => {
        navigate("/paper", {
          replace: false,
          state: { orderJustPlaced: true, symbol: normalized.symbol },
        });
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to place order.";
      logPaperOrder("confirm_failure", {
        message: msg,
        api_ms: Math.round(performance.now() - t0),
      });
      setPageError(msg);
      toast.error("Order failed", msg);
      setIsSubmitting(false);
      confirmInFlightRef.current = false;
    }
  }

  function applyTrailingStop() {
    const pct = Number(trailingStopPct) || 0;
    if (!entryReference || pct <= 0) return;
    const next = completePaperLevels({
      entry: entryReference,
      side: ticket.side,
      stop: null,
      target: derivedTargetRef.current ? null : ticket.target,
      stopPct: pct,
    });
    derivedStopRef.current = true;
    userClearedStopRef.current = false;
    if (next.derivedTarget) {
      derivedTargetRef.current = true;
      userClearedTargetRef.current = false;
    }
    setTicket((prev) => ({
      ...prev,
      stopLoss: next.stopLoss,
      target: next.target,
    }));
  }

  function applyCashAllocation() {
    const pct = Number(cashAllocPct) || 0;
    if (!availableCash || !entryReference || pct <= 0) return;
    const qty = Math.max(1, Math.floor((availableCash * (pct / 100)) / entryReference));
    setTicket({ ...ticket, qty });
  }

  const signalLabel = String(meta.signal || ticket.sourceSignal || ticket.side || "—");
  const signalClass =
    signalLabel.toUpperCase() === "BUY"
      ? "paper-order-badge paper-order-badge--buy"
      : signalLabel.toUpperCase() === "SELL"
        ? "paper-order-badge paper-order-badge--sell"
        : "paper-order-badge";

  const showHardLoadError = Boolean(loadError);
  const quoteUnavailable = quoteStatus === "error" || quoteLane === "error";
  const quoteLoading =
    (quoteLane === "loading" || quoteLane === "timeout" || quoteStatus === "loading") &&
    currentPrice == null;
  const accountLoading = accountLane === "loading" || accountLane === "timeout";
  const anyLanePending =
    quoteLane === "loading" ||
    quoteLane === "timeout" ||
    accountLane === "loading" ||
    accountLane === "timeout" ||
    recoLane === "loading" ||
    orderLane === "loading" ||
    orderLane === "timeout";

  return (
    <main className="page-container page-container--wide paper-order-page" data-testid="paper-order-page">
      {/* 1. Header — always immediate */}
      <header className="paper-order-page__header">
        <div className="paper-order-page__header-left">
          <button
            type="button"
            className="button ghost-button paper-order-page__back"
            onClick={handleBack}
            data-testid="paper-order-back"
          >
            ← Back
          </button>
          <div>
            <p className="section-label">Paper Trading</p>
            <h1 className="paper-order-page__title">
              {editingOrderId ? "Edit Paper Order" : "Paper Order"}
            </h1>
          </div>
        </div>
        <div className="paper-order-page__header-meta">
          <span className={signalClass}>{signalLabel}</span>
          <LaneChip state={quoteLane} readyLabel={quoteStatus === "live" ? "Live quote" : "Quote"} loadingLabel="Loading Quote…" />
          <LaneChip state={accountLane} readyLabel="Account" loadingLabel="Loading account…" />
          {anyLanePending ? (
            <span className="helper-chip paper-order-lane-chip" title="Background refresh">
              Syncing…
            </span>
          ) : null}
        </div>
      </header>

      {showHardLoadError ? (
        <section className="panel error-state" role="alert" data-testid="paper-order-load-error">
          <h2 className="ds-title">Unable to load order details</h2>
          <p className="muted-copy">{loadError}</p>
          <div style={{ display: "flex", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
            <Button variant="primary" onClick={handleRetry} data-testid="paper-order-retry">
              Retry
            </Button>
            <Button variant="ghost" onClick={handleBack}>
              Back
            </Button>
          </div>
          <p className="helper-text" style={{ marginTop: 12 }}>
            You can still edit the ticket below with any values already known from navigation.
          </p>
        </section>
      ) : null}

      {quoteUnavailable && !showHardLoadError ? (
        <div className="warning-box panel" role="status" style={{ marginBottom: 12 }}>
          <p>
            <strong>Unable to load latest market data.</strong>{" "}
            {navState.currentPrice != null || ticket.limitPrice != null
              ? "Using scanner / last known price where available."
              : "Enter limit price manually or retry."}
          </p>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button type="button" className="button ghost-button" onClick={handleRetry}>
              Retry
            </button>
          </div>
        </div>
      ) : null}

      {/*
        Progressive paint order (all non-blocking):
        Stock → Buttons → Order Form → Recommendation → Risk → Account → Live Quote
      */}
      <div className="paper-order-layout">
          {/* 2. Stock card */}
          <section className="panel paper-order-summary" data-testid="paper-order-stock">
            <div className="paper-order-summary__top">
              <div>
                <p className="section-label">Stock</p>
                <h2 className="paper-order-summary__symbol">{ticket.symbol || "—"}</h2>
              </div>
              {/* Live quote is progressive — never blocks form */}
              <div className="paper-order-summary__price-block" data-testid="paper-order-live-quote">
                <p className="section-label">
                  Current / Live{" "}
                  <LaneChip
                    state={quoteLane}
                    readyLabel={quoteStatus === "degraded" ? "Degraded" : "Live"}
                    loadingLabel="…"
                    compact
                  />
                </p>
                <div className="paper-order-summary__price">
                  {currentPrice != null ? (
                    `₹${currentPrice.toFixed(2)}`
                  ) : quoteLoading ? (
                    <span className="paper-order-shimmer-inline" aria-busy="true">
                      <Skeleton height={28} width={110} />
                    </span>
                  ) : (
                    "—"
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* 3. Actions (buttons) — sticky, always interactive */}
          <div className="paper-order-page__actions paper-order-page__actions--inline" data-testid="paper-order-actions-top">
            <Button variant="ghost" onClick={handleBack} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handlePlaceClick}
              disabled={isSubmitting}
              data-testid="paper-order-place-top"
            >
              Place Paper Order
            </Button>
          </div>

          {/* 4. Order form — editable immediately */}
          <section className="panel paper-order-form" data-testid="paper-order-form">
            <div className="paper-order-section-title-row">
              <h3 className="paper-order-section-title">Order Details</h3>
              {orderLane === "loading" || orderLane === "timeout" ? (
                <span className="paper-order-lane-hint">Loading order…</span>
              ) : null}
            </div>
            <div className="paper-ticket-grid">
              <label className="filter-field">
                <span>
                  Symbol
                  <InfoTooltip content="Cash equity symbol (canonical form)" />
                </span>
                <input
                  data-testid="paper-order-symbol"
                  value={ticket.symbol}
                  onChange={(e) => {
                    const sym = toCanonicalSymbol(e.target.value) || e.target.value.toUpperCase();
                    const isChanged = sym !== ticket.symbol;
                    setTicket((prev) => ({
                      ...prev,
                      symbol: sym,
                      limitPrice: isChanged ? null : prev.limitPrice,
                      stopLoss: isChanged ? null : prev.stopLoss,
                      target: isChanged ? null : prev.target,
                    }));
                    if (isChanged) {
                      derivedStopRef.current = true;
                      derivedTargetRef.current = true;
                      userClearedStopRef.current = false;
                      userClearedTargetRef.current = false;
                    }
                  }}
                  onBlur={() => {
                    // Quote only on symbol change — account is cached and stable
                    if (ticket.symbol) void loadQuoteAndAccount(ticket.symbol);
                  }}
                />
                {fieldErrors.symbol ? <span className="field-error">{fieldErrors.symbol}</span> : null}
              </label>

              <label className="filter-field">
                <span>Side</span>
                <select
                  data-testid="paper-order-side"
                  value={ticket.side}
                  onChange={(e) => setTicket({ ...ticket, side: e.target.value as "BUY" | "SELL" })}
                >
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
              </label>

              <label className="filter-field">
                <span>
                  Order Type
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.ORDER_TYPE} />
                </span>
                <select
                  data-testid="paper-order-type"
                  value={ticket.type}
                  onChange={(e) => setTicket({ ...ticket, type: e.target.value as PaperOrderTicketState["type"] })}
                >
                  <option value="MARKET">Market</option>
                  <option value="LIMIT">Limit</option>
                  <option value="STOP">Stop-Loss</option>
                  <option value="STOP_LIMIT">Stop-Limit</option>
                  <option value="GTT">GTT</option>
                </select>
              </label>

              <label className="filter-field">
                <span>
                  Product
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.PRODUCT_TYPE} />
                </span>
                <select
                  value={ticket.productType ?? "CNC"}
                  onChange={(e) =>
                    setTicket({
                      ...ticket,
                      productType: e.target.value as PaperOrderTicketState["productType"],
                    })
                  }
                >
                  <option value="MIS">MIS (Intraday)</option>
                  <option value="CNC">CNC (Delivery)</option>
                  <option value="NRML">NRML (Carry)</option>
                </select>
              </label>

              <label className="filter-field">
                <span>
                  Quantity
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.QUANTITY} />
                </span>
                <input
                  data-testid="paper-order-qty"
                  type="number"
                  min={1}
                  value={ticket.qty}
                  onChange={(e) => setTicket({ ...ticket, qty: Number(e.target.value) })}
                />
                {fieldErrors.qty ? <span className="field-error">{fieldErrors.qty}</span> : null}
              </label>

              {ticket.type === "STOP_LIMIT" ? (
                <>
                  <label className="filter-field">
                    <span>
                      Stop Trigger
                      <InfoTooltip content={TOOLTIPS.PAPER_TRADING.STOP_LOSS_FIELD} />
                    </span>
                    <input
                      data-testid="paper-order-stop-trigger"
                      type="number"
                      min={0.01}
                      step="0.05"
                      placeholder="Stop trigger price"
                      value={ticket.stopPrice ?? ""}
                      onChange={(e) => {
                        const v = Number(e.target.value) || null;
                        setTicket({ ...ticket, stopPrice: v });
                      }}
                    />
                    {fieldErrors.stopPrice ? <span className="field-error">{fieldErrors.stopPrice}</span> : null}
                  </label>
                  <label className="filter-field">
                    <span>
                      Limit Price
                      <InfoTooltip content={TOOLTIPS.PAPER_TRADING.LIMIT_PRICE} />
                    </span>
                    <input
                      data-testid="paper-order-price"
                      type="number"
                      min={0.01}
                      step="0.05"
                      placeholder="Limit price"
                      value={ticket.limitPrice ?? ""}
                      onChange={(e) => {
                        const v = Number(e.target.value) || null;
                        setTicket({ ...ticket, limitPrice: v });
                      }}
                    />
                    {fieldErrors.price ? <span className="field-error">{fieldErrors.price}</span> : null}
                  </label>
                </>
              ) : ticket.type !== "MARKET" ? (
                <label className="filter-field">
                  <span>
                    {ticket.type === "STOP" ? "Stop Trigger" : "Limit Price"}
                    <InfoTooltip content={TOOLTIPS.PAPER_TRADING.LIMIT_PRICE} />
                  </span>
                  <input
                    data-testid="paper-order-price"
                    type="number"
                    min={0.01}
                    step="0.05"
                    value={
                      ticket.type === "STOP"
                        ? ticket.stopPrice ?? ""
                        : ticket.limitPrice ?? ""
                    }
                    onChange={(e) => {
                      const v = Number(e.target.value) || null;
                      if (ticket.type === "STOP") setTicket({ ...ticket, stopPrice: v });
                      else setTicket({ ...ticket, limitPrice: v });
                    }}
                  />
                  {navState.prefill?.suggested_entry != null ? (
                    <span className="helper-text" data-testid="paper-order-entry-source">
                      Auto-filled from strategy
                    </span>
                  ) : null}
                  {fieldErrors.price ? <span className="field-error">{fieldErrors.price}</span> : null}
                </label>
              ) : null}

              <label className="filter-field">
                <span>
                  Stop Loss
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.STOP_LOSS_FIELD} />
                </span>
                <input
                  data-testid="paper-order-sl"
                  type="number"
                  min={0.01}
                  step="0.05"
                  placeholder="Not available"
                  value={ticket.stopLoss ?? ""}
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    const val = raw === "" ? null : Number(raw);
                    derivedStopRef.current = false;
                    userClearedStopRef.current = val === null;
                    setTicket((prev) => ({ ...prev, stopLoss: val }));
                    setFieldErrors((prev) => {
                      if (!prev.stopLoss) return prev;
                      const next = { ...prev };
                      delete next.stopLoss;
                      return next;
                    });
                    setPageError(null);
                  }}
                />
                {ticket.stopLoss != null ? (
                  <span className="helper-text" data-testid="paper-order-sl-source">
                    {derivedStopRef.current
                      ? "Auto-filled from limit price (2% stop)"
                      : navState.prefill?.recommendation_meta?.stop_source === "strategy"
                        ? "Auto-filled from strategy"
                        : "Custom stop loss"}
                  </span>
                ) : (
                  <span className="helper-text">Optional — enter a stop loss or limit price to auto-fill</span>
                )}
                {fieldErrors.stopLoss ? (
                  <span className="field-error" data-testid="paper-order-sl-error">
                    {fieldErrors.stopLoss}
                  </span>
                ) : null}
              </label>

              <label className="filter-field">
                <span>
                  Target
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TARGET_FIELD} />
                </span>
                <input
                  data-testid="paper-order-target"
                  type="number"
                  min={0.01}
                  step="0.05"
                  placeholder="Not available"
                  value={ticket.target ?? ""}
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    const val = raw === "" ? null : Number(raw);
                    derivedTargetRef.current = false;
                    userClearedTargetRef.current = val === null;
                    setTicket((prev) => ({ ...prev, target: val }));
                    setFieldErrors((prev) => {
                      if (!prev.target) return prev;
                      const next = { ...prev };
                      delete next.target;
                      return next;
                    });
                    setPageError(null);
                  }}
                />
                {ticket.target != null ? (
                  <span className="helper-text" data-testid="paper-order-target-source">
                    {derivedTargetRef.current
                      ? "Auto-filled from limit price (1:2 vs stop)"
                      : navState.prefill?.recommendation_meta?.target_source === "strategy"
                        ? "Auto-filled from strategy"
                        : "Custom target"}
                  </span>
                ) : (
                  <span className="helper-text">Optional — enter a target or limit price to auto-fill</span>
                )}
                {fieldErrors.target ? (
                  <span className="field-error" data-testid="paper-order-target-error">
                    {fieldErrors.target}
                  </span>
                ) : null}
              </label>
            </div>

            <div className="broker-helper-grid" style={{ marginTop: 16 }}>
              <label className="filter-field">
                <span>
                  Trailing Stop %
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TRAILING_STOP} />
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="number"
                    min={0.1}
                    step="0.1"
                    value={trailingStopPct}
                    onChange={(e) => setTrailingStopPct(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button type="button" className="button ghost-button" onClick={applyTrailingStop}>
                    Apply
                  </button>
                </div>
              </label>
              <label className="filter-field">
                <span>
                  Cash Allocation %
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.CASH_ALLOCATION} />
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={cashAllocPct}
                    onChange={(e) => setCashAllocPct(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button type="button" className="button ghost-button" onClick={applyCashAllocation}>
                    Apply
                  </button>
                </div>
              </label>
            </div>

            <label className="filter-field" style={{ marginTop: 16 }}>
              <span>Notes</span>
              <input
                data-testid="paper-order-notes"
                value={ticket.notes ?? ""}
                onChange={(e) => setTicket({ ...ticket, notes: e.target.value })}
              />
            </label>
          </section>

          {/* 5. Recommendation card — independent */}
          <section className="panel paper-order-reco" data-testid="paper-order-recommendation">
            <div className="paper-order-section-title-row">
              <h3 className="paper-order-section-title">Recommendation</h3>
              <LaneChip
                state={recoLane === "idle" ? "ready" : recoLane}
                readyLabel={navState.prefill ? "Scanner" : "Manual"}
                loadingLabel="Refining…"
                compact
              />
            </div>
            {recoLane === "loading" && !navState.prefill ? (
              <div className="paper-order-shimmer-card" aria-busy="true">
                <Skeleton height={14} width="40%" />
                <Skeleton height={36} width="100%" />
                <Skeleton height={14} width="70%" />
              </div>
            ) : (
              <div className="paper-order-summary__metrics">
                <Metric label="Signal" value={signalLabel} />
                <Metric
                  label={String(navState.prefill?.recommendation_meta?.score_label || "Score")}
                  value={
                    meta.score != null && meta.score !== 0
                      ? String(navState.prefill?.recommendation_meta?.score_kind || "").startsWith("momentum")
                        ? `${formatNum(Number(meta.score), 1)}%`
                        : formatNum(Number(meta.score), 1)
                      : "—"
                  }
                />
                <Metric
                  label="Confidence"
                  value={
                    meta.confidence != null && Number(meta.confidence) > 0
                      ? Number(meta.confidence) <= 1
                        ? `${Math.round(Number(meta.confidence) * 100)}%`
                        : `${Math.round(Number(meta.confidence))}%`
                      : "—"
                  }
                />
                <Metric
                  label="Risk / Reward"
                  value={risk.riskReward ? formatNum(risk.riskReward, 2) : "—"}
                />
                <Metric
                  label="Strategy"
                  value={
                    ticket.sourceStrategy ||
                    originStrategyName ||
                    extractStrategyFromNotes(ticket.notes) ||
                    "—"
                  }
                  testId="paper-order-strategy"
                />
              </div>
            )}
            {navState.prefill ? (
              <p className="helper-text" style={{ marginTop: 12 }}>
                Scanner recommendation loaded
                {navState.prefill.recommendation_meta?.signal
                  ? ` · signal ${String(navState.prefill.recommendation_meta.signal)}`
                  : ""}
                {navState.prefill.suggested_entry != null
                  ? ` · suggested entry ${formatInr(navState.prefill.suggested_entry)}`
                  : ""}
                {ticket.stopLoss != null
                  ? ` · stop ${formatInr(ticket.stopLoss)}`
                  : " · stop not available"}
                {ticket.target != null
                  ? ` · target ${formatInr(ticket.target)}`
                  : " · target not available"}
                {ticket.qty ? ` · suggested qty ${ticket.qty}` : ""}.
              </p>
            ) : !hasNavState && searchParams.get("symbol") ? (
              <p className="helper-text" style={{ marginTop: 12 }}>
                Loaded from symbol (scanner data not in navigation state).
              </p>
            ) : (
              <p className="helper-text" style={{ marginTop: 12 }}>
                Manual ticket — enter levels below or apply helpers.
              </p>
            )}
          </section>

          {/* 6. Risk & Transaction Cost summary — client-side, always ready from form state */}
          <section className="panel paper-order-risk" data-testid="paper-order-risk">
            <h3 className="paper-order-section-title">Risk & Transaction Cost Summary</h3>
            <div className="paper-order-risk__grid">
              <Metric label={ticket.side === "BUY" ? "Gross Order Value" : "Gross Sale Value"} value={formatInr(risk.estimatedCost)} />
              <Metric label="Brokerage" value={formatInr(risk.brokerage)} />
              <Metric label="Total Taxes & Charges" value={formatInr(risk.charges)} />
              <Metric label={ticket.side === "BUY" ? "Net Outlay Required" : "Estimated Net Proceeds"} value={formatInr(risk.totalCost)} />
              {ticket.side === "BUY" && risk.breakEvenPrice > 0 ? (
                <Metric label="Break-Even Exit Price" value={formatInr(risk.breakEvenPrice)} />
              ) : null}
              <Metric label="Risk Amount" value={formatInr(risk.riskAmount)} />
              <Metric label="Potential Profit" value={formatInr(risk.potentialProfit)} />
              <Metric label="Potential Loss" value={formatInr(risk.potentialLoss)} />
              <Metric label="Risk % of Account" value={`${risk.riskPercent.toFixed(2)}%`} />
            </div>
            {fieldErrors.risk ? (
              <div className="warning-box" style={{ marginTop: 12 }} data-testid="paper-order-risk-error">
                <p>{fieldErrors.risk}</p>
              </div>
            ) : null}
            <p className="helper-text" style={{ marginTop: 12 }}>
              Guideline: risk no more than {(maxRiskPercent * 100).toFixed(1)}% per trade. Charges include STT (0.1%), NSE exchange fee, SEBI turnover fee, Stamp Duty &amp; 18% GST on services.
            </p>
          </section>

          {/* 7. Account balance — independent skeleton lane */}
          <section className="panel paper-order-account" data-testid="paper-order-account">
            <div className="paper-order-section-title-row">
              <h3 className="paper-order-section-title">Account Balance</h3>
              <LaneChip
                state={accountLane}
                readyLabel="Ready"
                loadingLabel="Loading paper account…"
                compact
              />
            </div>
            {accountLoading && availableCash == null ? (
              <div className="paper-order-shimmer-card" aria-busy="true">
                <Skeleton height={48} width="55%" />
                <Skeleton height={14} width="35%" />
              </div>
            ) : (
              <div className="paper-order-risk__grid">
                <Metric
                  label="Available Cash"
                  value={
                    !accountLoaded
                      ? "Loading…"
                      : availableCash == null
                        ? "Unavailable"
                        : formatInr(availableCash)
                  }
                />
                <Metric
                  label="Max Risk / Trade"
                  value={`${(maxRiskPercent * 100).toFixed(1)}%`}
                />
              </div>
            )}
            {fieldErrors.cash ? (
              <div className="warning-box" style={{ marginTop: 12 }} data-testid="paper-order-cash-error">
                <p>{fieldErrors.cash}</p>
              </div>
            ) : null}
          </section>
      </div>

      {pageError || Object.keys(fieldErrors).length > 0 ? (
        <div
          className="error-state panel"
          role="alert"
          data-testid="paper-order-validation-summary"
          style={{ marginTop: 16, whiteSpace: "pre-line" }}
        >
          <strong style={{ display: "block", marginBottom: 8 }}>
            {Object.keys(fieldErrors).length > 1
              ? `${Object.keys(fieldErrors).length} validation issues — fix all of the following:`
              : "Validation issue — fix the following:"}
          </strong>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {(pageError
              ? pageError
                  .replace(/^Cannot place order:\n?/, "")
                  .split("\n")
                  .map((line) => line.replace(/^[•\-\d.]+\s*/, "").trim())
                  .filter(Boolean)
              : Object.values(fieldErrors)
            ).map((msg) => (
              <li key={msg}>{msg}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Sticky actions */}
      <div className="paper-order-page__actions" data-testid="paper-order-actions">
        <Button variant="ghost" onClick={handleBack} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button
          variant="primary"
          onClick={handlePlaceClick}
          disabled={isSubmitting}
          data-testid="paper-order-place"
        >
          Place Paper Order
        </Button>
      </div>

      {/* Confirmation modal — only executes after Confirm */}
      <Modal
        open={confirmOpen}
        onClose={() => {
          if (!isSubmitting) setConfirmOpen(false);
        }}
        title="Confirm Paper Order"
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => void handleConfirmOrder()}
              loading={isSubmitting}
              disabled={isSubmitting}
              data-testid="paper-order-confirm"
            >
              Confirm Order
            </Button>
          </>
        }
      >
        <div className="paper-order-confirm" data-testid="paper-order-confirm-body">
          <p className="paper-order-confirm__lead">
            You are about to <strong>{ticket.side}</strong>
          </p>
          <p className="paper-order-confirm__qty">
            <strong>{ticket.qty}</strong> share{ticket.qty === 1 ? "" : "s"} of{" "}
            <strong>
              {ticket.symbol}
              {ticket.symbol && !ticket.symbol.includes("-") ? "-EQ" : ""}
            </strong>
          </p>
          <dl className="paper-order-confirm__dl">
            <div>
              <dt>Price</dt>
              <dd>{formatInr(entryReference)}</dd>
            </div>
            <div>
              <dt>Order Value (Turnover)</dt>
              <dd>{formatInr(risk.estimatedCost)}</dd>
            </div>
            <div>
              <dt style={{ display: "inline-flex", alignItems: "center" }}>
                <span>Total Broker Charges</span>
                <InfoTooltip
                  position="top"
                  maxWidth="300px"
                  ariaLabel="Broker charges breakdown"
                  content={
                    <div style={{ display: "flex", flexDirection: "column", gap: "6px", minWidth: "220px", textAlign: "left" }}>
                      <div style={{ fontWeight: 650, fontSize: "12px", borderBottom: "1px solid rgba(255,255,255,0.12)", paddingBottom: "4px", marginBottom: "2px", color: "var(--text-primary, #f1f5f9)" }}>
                        Broker Charges Breakdown
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "16px" }}>
                        <span style={{ color: "var(--text-muted, #94a3b8)" }}>Brokerage</span>
                        <span style={{ fontWeight: 600 }}>{formatInr(risk.brokerage)}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "16px" }}>
                        <span style={{ color: "var(--text-muted, #94a3b8)" }}>Securities Transaction Tax (STT)</span>
                        <span style={{ fontWeight: 600 }}>{formatInr(risk.stt)}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "16px" }}>
                        <span style={{ color: "var(--text-muted, #94a3b8)" }}>Exchange &amp; SEBI Charges</span>
                        <span style={{ fontWeight: 600 }}>{formatInr(risk.exchangeTurnover + risk.sebiTurnover)}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "16px" }}>
                        <span style={{ color: "var(--text-muted, #94a3b8)" }}>GST (18% on Services)</span>
                        <span style={{ fontWeight: 600 }}>{formatInr(risk.gst)}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "16px" }}>
                        <span style={{ color: "var(--text-muted, #94a3b8)" }}>{ticket.side === "BUY" ? "Stamp Duty (0.015%)" : "DP Charges"}</span>
                        <span style={{ fontWeight: 600 }}>{formatInr(ticket.side === "BUY" ? risk.stampDuty : risk.dpCharges)}</span>
                      </div>
                      <div style={{ borderTop: "1px dashed rgba(255,255,255,0.12)", paddingTop: "4px", marginTop: "2px", display: "flex", justifyContent: "space-between", gap: "16px", fontWeight: 700 }}>
                        <span>Total</span>
                        <span>{formatInr(risk.charges)}</span>
                      </div>
                    </div>
                  }
                />
              </dt>
              <dd>{formatInr(risk.charges)}</dd>
            </div>
            <div>
              <dt><strong>{ticket.side === "BUY" ? "Net Outlay Required" : "Estimated Net Proceeds"}</strong></dt>
              <dd><strong>{formatInr(risk.totalCost)}</strong></dd>
            </div>
            {ticket.side === "BUY" && risk.breakEvenPrice > 0 ? (
              <div style={{ color: "var(--accent-color, #3b82f6)" }}>
                <dt>Break-Even Exit Price</dt>
                <dd>{formatInr(risk.breakEvenPrice)}</dd>
              </div>
            ) : null}
            <div>
              <dt>Order Type</dt>
              <dd>{ticket.type}</dd>
            </div>
            {ticket.sourceStrategy || originStrategyName || extractStrategyFromNotes(ticket.notes) ? (
              <div>
                <dt>Strategy</dt>
                <dd data-testid="paper-order-confirm-strategy">
                  {ticket.sourceStrategy || originStrategyName || extractStrategyFromNotes(ticket.notes)}
                </dd>
              </div>
            ) : null}
            {ticket.stopLoss != null ? (
              <div>
                <dt>Stop Loss</dt>
                <dd>{formatInr(ticket.stopLoss)}</dd>
              </div>
            ) : null}
            {ticket.target != null ? (
              <div>
                <dt>Target</dt>
                <dd>{formatInr(ticket.target)}</dd>
              </div>
            ) : null}
          </dl>
          <div className="paper-order-confirm__notice">
            <strong>Paper Trading</strong>
            <p>This order will affect your paper portfolio only. No real money will be used.</p>
          </div>
        </div>
      </Modal>
    </main>
  );
}

const Metric = memo(function Metric({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId?: string;
}) {
  return (
    <div className="metric-tile" data-testid={testId}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
});

const LaneChip = memo(function LaneChip({
  state,
  readyLabel,
  loadingLabel,
  compact = false,
}: {
  state: LaneState;
  readyLabel: string;
  loadingLabel: string;
  compact?: boolean;
}) {
  if (state === "idle") return null;
  let text = readyLabel;
  let cls = "helper-chip paper-order-lane-chip";
  if (state === "loading") {
    text = loadingLabel;
    cls += " paper-order-lane-chip--loading";
  } else if (state === "timeout") {
    text = compact ? "…" : "Retrying…";
    cls += " is-risk paper-order-lane-chip--loading";
  } else if (state === "error") {
    text = compact ? "!" : "Unavailable";
    cls += " is-risk";
  } else if (state === "ready") {
    cls += " paper-order-lane-chip--ready";
  }
  return (
    <span className={cls} title={state} data-lane={state}>
      {text}
    </span>
  );
});

export default PaperOrderPage;
