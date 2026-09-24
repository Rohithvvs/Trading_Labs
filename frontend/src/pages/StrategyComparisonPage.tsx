import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  compareStrategies,
  fetchComparisonCatalog,
  fetchComparisonRuns,
  type ComparisonCatalogStrategy,
  type ComparisonPayload,
  type ComparisonRunPreview,
  type ComparisonSlotInput,
  type ComparisonSource,
  type ComparisonSuggestion,
} from "../api_strategy_comparison";
import { ComparisonCharts, SLOT_COLORS } from "../components/strategy_comparison/ComparisonCharts";
import { ComparisonLeaderboard } from "../components/strategy_comparison/LeaderboardTable";
import { ComparisonRadar } from "../components/strategy_comparison/ComparisonRadar";
import { PineCodeEditor } from "../components/strategy_tester/PineCodeEditor";
import { StrategyVennDiagram } from "../components/strategy_comparison/StrategyVennDiagram";
import "./strategyTester.css";
import "./strategyComparison.css";

type DraftSlot = {
  strategyId: string;
  strategyName: string;
  runId: string;
  source: ComparisonSource | "";
  query: string;
  open: boolean;
  runs: ComparisonRunPreview[];
  runsLoading: boolean;
  runsError: string | null;
};

const EMPTY_SLOT = (): DraftSlot => ({
  strategyId: "",
  strategyName: "",
  runId: "",
  source: "",
  query: "",
  open: false,
  runs: [],
  runsLoading: false,
  runsError: null,
});

function fmtNum(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

function fmtPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(2)}%`;
}

function fmtInr(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function signedClass(value: number | null | undefined): string {
  if (value == null) return "";
  if (value > 0) return "sc-pos";
  if (value < 0) return "sc-neg";
  return "";
}

function listOrDash(items: string[] | null | undefined): string {
  if (!items || items.length === 0) return "—";
  return items.join("\n");
}

function SlotHeadCell({
  index,
  slot,
  catalog,
  catalogLoading,
  canRemove,
  onRemove,
  onSelectStrategy,
  onSelectRun,
  onToggleOpen,
  onQuery,
}: {
  index: number;
  slot: DraftSlot;
  catalog: ComparisonCatalogStrategy[];
  catalogLoading: boolean;
  canRemove: boolean;
  onRemove: () => void;
  onSelectStrategy: (item: ComparisonCatalogStrategy) => void;
  onSelectRun: (runId: string) => void;
  onToggleOpen: (open: boolean) => void;
  onQuery: (query: string) => void;
}) {
  const filtered = catalog.filter((item) => {
    const q = slot.query.trim().toLowerCase();
    if (!q || item.id === slot.strategyId) return true;
    return item.name.toLowerCase().includes(q) || (item.description || "").toLowerCase().includes(q);
  });

  return (
    <div className="sc-radar-head-cell sc-head-picker" data-testid={`sc-slot-${index}`} data-slot-picker>
      {canRemove ? (
        <button type="button" className="sc-head-remove" onClick={onRemove} aria-label="Remove strategy" data-testid={`sc-remove-${index}`}>
          ×
        </button>
      ) : null}
      {slot.strategyId ? (
        <>
          <button type="button" className="sc-head-trigger" onClick={() => onToggleOpen(!slot.open)} data-testid={`sc-strategy-search-${index}`}>
            <span className="sc-radar-head-swatch" style={{ background: SLOT_COLORS[index] }} />
            <span className="sc-radar-head-name">{slot.strategyName || "Strategy"}</span>
            <span className="sc-radar-head-chevron" aria-hidden>▾</span>
          </button>
          {slot.open ? (
            <div className="sc-head-menu" data-testid={`sc-strategy-options-${index}`}>
              <input
                className="sc-search"
                autoFocus
                value={slot.query}
                placeholder="Search strategies"
                onChange={(e) => onQuery(e.target.value)}
              />
              <div className="sc-option-list sc-option-list--head">
                {filtered.length === 0 ? (
                  <div className="sc-option sc-muted">No matching saved strategies</div>
                ) : (
                  filtered.map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      className={`sc-option ${item.id === slot.strategyId ? "is-active" : ""}`}
                      onClick={() => onSelectStrategy(item)}
                    >
                      {item.name}
                      <small>
                        {item.completed_run_count} scan run{item.completed_run_count === 1 ? "" : "s"}
                        {item.completed_lean_count ? ` · ${item.completed_lean_count} LEAN` : ""}
                      </small>
                    </button>
                  ))
                )}
              </div>
            </div>
          ) : null}
          {slot.runsLoading ? <div className="sc-skeleton" style={{ height: 22, width: "70%" }} /> : null}
          {!slot.runsLoading && slot.strategyId && slot.runs.length > 0 ? (
            <select
              className="sc-head-run"
              value={slot.runId}
              onChange={(e) => onSelectRun(e.target.value)}
              data-testid={`sc-run-select-${index}`}
            >
              <option value="">Select a completed run</option>
              {slot.runs.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {run.label}
                </option>
              ))}
            </select>
          ) : null}
          {!slot.runsLoading && slot.strategyId && slot.runs.length === 0 ? (
            <span className="sc-head-run-empty">
              No runs · <Link to="/strategy-tester">Tester</Link>
            </span>
          ) : null}
        </>
      ) : (
        <>
          <button
            type="button"
            className="sc-head-trigger sc-head-trigger--empty"
            onClick={() => onToggleOpen(true)}
            data-testid={`sc-select-cta-${index}`}
          >
            + Select a strategy
            <span className="sc-radar-head-chevron" aria-hidden>▾</span>
          </button>
          {slot.open ? (
            <div className="sc-head-menu">
              <input
                className="sc-search"
                autoFocus
                placeholder="Search strategies"
                value={slot.query}
                onChange={(e) => onQuery(e.target.value)}
                data-testid={`sc-strategy-search-${index}`}
              />
              <div className="sc-option-list sc-option-list--head">
                {catalogLoading ? <div className="sc-option">Loading…</div> : null}
                {!catalogLoading && catalog.length === 0 ? (
                  <div className="sc-option sc-muted">Save a strategy in Strategy Tester first.</div>
                ) : (
                  catalog
                    .filter((item) => item.name.toLowerCase().includes(slot.query.toLowerCase()))
                    .map((item) => (
                      <button type="button" key={item.id} className="sc-option" onClick={() => onSelectStrategy(item)}>
                        {item.name}
                        <small>
                          {item.completed_run_count} completed run{item.completed_run_count === 1 ? "" : "s"}
                        </small>
                      </button>
                    ))
                )}
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function strongerIndexes(values: Array<number | null | undefined>, higherIsBetter: boolean): Set<number> {
  const present = values
    .map((value, index) => (value == null || Number.isNaN(Number(value)) ? null : { index, value: Number(value) }))
    .filter((item): item is { index: number; value: number } => item != null);
  if (present.length < 2) return new Set();
  const target = higherIsBetter ? Math.max(...present.map((item) => item.value)) : Math.min(...present.map((item) => item.value));
  const hits = present.filter((item) => item.value === target).map((item) => item.index);
  if (hits.length === present.length) return new Set();
  return new Set(hits);
}

function valuesDiffer(values: Array<string | number | null | undefined>): boolean {
  return new Set(values.map((value) => (value == null || value === "" ? "" : String(value)))).size > 1;
}

export function StrategyComparisonPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [catalog, setCatalog] = useState<ComparisonCatalogStrategy[]>([]);
  const [suggestions, setSuggestions] = useState<ComparisonSuggestion[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [slots, setSlots] = useState<DraftSlot[]>([EMPTY_SLOT(), EMPTY_SLOT()]);
  const [comparison, setComparison] = useState<ComparisonPayload | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [tradeSearch, setTradeSearch] = useState("");
  const [signalSearch, setSignalSearch] = useState("");
  const [highlightDiffs, setHighlightDiffs] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setCatalogLoading(true);
    fetchComparisonCatalog()
      .then((data) => {
        if (cancelled) return;
        setCatalog(data.strategies);
        setSuggestions(data.suggestions || []);
        setCatalogError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setCatalogError(err.message || "Unable to load strategies.");
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("[data-slot-picker]")) return;
      setSlots((prev) => prev.map((slot) => (slot.open ? { ...slot, open: false } : slot)));
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSlots((prev) => prev.map((slot) => (slot.open ? { ...slot, open: false } : slot)));
      }
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const loadRuns = useCallback(async (index: number, strategyId: string) => {
    setSlots((prev) =>
      prev.map((slot, i) => (i === index ? { ...slot, runsLoading: true, runsError: null } : slot)),
    );
    try {
      const data = await fetchComparisonRuns(strategyId);
      setSlots((prev) =>
        prev.map((slot, i) => {
          if (i !== index) return slot;
          const latest = data.runs[0];
          const alreadySelected = slot.runId && data.runs.some((run) => run.run_id === slot.runId);
          return {
            ...slot,
            runs: data.runs,
            runsLoading: false,
            runId: alreadySelected ? slot.runId : latest?.run_id || "",
            source: alreadySelected ? slot.source : latest?.source || "",
          };
        }),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load runs.";
      setSlots((prev) =>
        prev.map((slot, i) => (i === index ? { ...slot, runsLoading: false, runsError: message, runs: [] } : slot)),
      );
    }
  }, []);

  useEffect(() => {
    const raw = searchParams.getAll("slot");
    if (!raw.length || catalog.length === 0) return;
    const parsed = raw.slice(0, 4).map((item) => {
      const [strategyId, runId, source] = item.split(":");
      const strategy = catalog.find((s) => s.id === strategyId);
      return {
        ...EMPTY_SLOT(),
        strategyId: strategyId || "",
        strategyName: strategy?.name || "",
        runId: runId || "",
        source: (source as ComparisonSource) || "",
      };
    });
    if (parsed.length >= 2) {
      setSlots(parsed);
      parsed.forEach((slot, index) => {
        if (slot.strategyId) void loadRuns(index, slot.strategyId);
      });
    }
    // Hydrate once from URL after catalog loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog]);

  const readyInputs: ComparisonSlotInput[] = useMemo(
    () =>
      slots
        .filter((slot) => slot.strategyId && slot.runId)
        .map((slot) => ({
          strategy_id: slot.strategyId,
          run_id: slot.runId,
          source: slot.source || undefined,
        })),
    [slots],
  );

  useEffect(() => {
    if (readyInputs.length < 2) {
      setComparison(null);
      setCompareError(null);
      return;
    }
    let cancelled = false;
    setCompareLoading(true);
    setCompareError(null);
    compareStrategies(readyInputs)
      .then((data) => {
        if (!cancelled) setComparison(data);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setComparison(null);
          setCompareError(err.message || "Unable to compare strategies.");
        }
      })
      .finally(() => {
        if (!cancelled) setCompareLoading(false);
      });
    const nextValue = readyInputs
      .map((slot) => `${slot.strategy_id}:${slot.run_id}:${slot.source || "strategy_tester"}`)
      .join("|");
    const currentValue = searchParams.getAll("slot").join("|");
    if (nextValue !== currentValue) {
      const next = new URLSearchParams();
      readyInputs.forEach((slot) => next.append("slot", `${slot.strategy_id}:${slot.run_id}:${slot.source || "strategy_tester"}`));
      setSearchParams(next, { replace: true });
    }
    return () => {
      cancelled = true;
    };
    // searchParams is read for equality only; including it would refetch on every URL write.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readyInputs, setSearchParams]);

  function addSlot() {
    if (slots.length >= 4) return;
    setSlots((prev) => [...prev, EMPTY_SLOT()]);
  }

  function removeSlot(index: number) {
    setSlots((prev) => (prev.length <= 2 ? prev : prev.filter((_, i) => i !== index)));
  }

  function selectStrategy(index: number, strategy: ComparisonCatalogStrategy) {
    setSlots((prev) =>
      prev.map((slot, i) =>
        i === index
          ? {
              ...slot,
              strategyId: strategy.id,
              strategyName: strategy.name,
              query: strategy.name,
              open: false,
              runId: "",
              source: "",
              runs: [],
            }
          : slot,
      ),
    );
    void loadRuns(index, strategy.id);
  }

  function selectRun(index: number, runId: string) {
    const run = slots[index]?.runs.find((item) => item.run_id === runId);
    setSlots((prev) =>
      prev.map((slot, i) =>
        i === index ? { ...slot, runId, source: run?.source || "strategy_tester" } : slot,
      ),
    );
  }

  function applySuggestion(suggestion: ComparisonSuggestion) {
    const next: DraftSlot[] = suggestion.strategy_ids.slice(0, 4).map((id) => {
      const strategy = catalog.find((item) => item.id === id);
      const latest = strategy?.latest_run;
      const source: ComparisonSource | "" =
        latest?.source === "lean" || latest?.source === "strategy_tester" || latest?.source === "indicator_scan"
          ? latest.source
          : "";
      return {
        ...EMPTY_SLOT(),
        strategyId: id,
        strategyName: strategy?.name || "",
        runId: latest?.run_id || "",
        source,
      };
    });
    while (next.length < 2) next.push(EMPTY_SLOT());
    setSlots(next);
    next.forEach((slot, index) => {
      if (slot.strategyId) void loadRuns(index, slot.strategyId);
    });
  }

  const cols = comparison?.slots.length || readyInputs.length || slots.length;

  return (
    <div className="strategy-comparison-page" data-testid="strategy-comparison-page">
      <header className="sc-header">
        <div>
          <p className="sc-kicker">Strategy Tester / Compare</p>
          <h1 className="sc-title">Strategy Comparison</h1>
          <p className="sc-subtitle">
            Compare 2–4 saved strategies using completed Strategy Tester scans and LEAN backtests. The summary table
            at the top uses the same radar display-scale for Score, Grade, and Rank. Missing metrics stay blank.
          </p>
        </div>
        <div className="sc-header-actions">
          <label className="sc-toggle">
            <input
              type="checkbox"
              checked={highlightDiffs}
              onChange={(e) => setHighlightDiffs(e.target.checked)}
              data-testid="sc-highlight-toggle"
            />
            Highlight differences
          </label>
          <Link to="/strategy-tester" className="sc-btn" data-testid="sc-open-tester">
            Open Strategy Tester
          </Link>
          {comparison ? (
            <button
              type="button"
              className="sc-btn sc-btn--venn-cta"
              onClick={() => {
                document.getElementById("sc-venn-section")?.scrollIntoView({ behavior: "smooth" });
              }}
              title="Jump directly to Venn Diagram representation"
            >
              🟡 Venn Diagram (∩ / ∪) ↓
            </button>
          ) : null}
          <button type="button" className="sc-btn sc-btn-primary" onClick={addSlot} disabled={slots.length >= 4} data-testid="sc-add-strategy">
            + Add Strategy
          </button>
        </div>
      </header>

      {catalogError ? (
        <div className="sc-banner sc-banner--error" role="alert">
          {catalogError}
        </div>
      ) : null}

      <section className="sc-radar-panel sc-compare-canvas">
        <div
          className="sc-radar-head"
          data-testid="sc-slots"
          style={{ gridTemplateColumns: `minmax(48px, 0.7fr) repeat(${slots.length}, minmax(0, 1fr))` }}
        >
          <div className="sc-radar-head-cell sc-radar-head-cell--empty" />
          {slots.map((slot, index) => (
            <SlotHeadCell
              key={`slot-${index}`}
              index={index}
              slot={slot}
              catalog={catalog}
              catalogLoading={catalogLoading}
              canRemove={slots.length > 2}
              onRemove={() => removeSlot(index)}
              onSelectStrategy={(item) => selectStrategy(index, item)}
              onSelectRun={(runId) => selectRun(index, runId)}
              onToggleOpen={(open) =>
                setSlots((prev) => prev.map((s, i) => (i === index ? { ...s, open, query: open ? s.query || s.strategyName : s.strategyName || s.query } : { ...s, open: false })))
              }
              onQuery={(query) =>
                setSlots((prev) => prev.map((s, i) => (i === index ? { ...s, query, open: true } : s)))
              }
            />
          ))}
        </div>
        {comparison ? (
          <>
            <ComparisonLeaderboard comparison={comparison} highlight={highlightDiffs} />
            <ComparisonRadar comparison={comparison} hideHeader />
          </>
        ) : (
          <div className="sc-radar-body">
            <div className="sc-chart-empty">
              {compareLoading ? "Loading comparison from completed runs…" : "Select two strategies to plot a metric profile."}
            </div>
          </div>
        )}
      </section>

      {comparison ? (
        <nav className="sc-quick-nav">
          <button
            type="button"
            onClick={() => document.getElementById("sc-metrics")?.scrollIntoView({ behavior: "smooth" })}
          >
            📈 Metrics
          </button>
          <button
            type="button"
            onClick={() => document.getElementById("sc-signals")?.scrollIntoView({ behavior: "smooth" })}
          >
            🎯 Signal Overlap
          </button>
          <button
            type="button"
            className="sc-quick-nav-highlight"
            onClick={() => document.getElementById("sc-venn-section")?.scrollIntoView({ behavior: "smooth" })}
          >
            🟡 Venn Diagram (∩ / ∪)
          </button>
          <button
            type="button"
            onClick={() => document.getElementById("sc-charts")?.scrollIntoView({ behavior: "smooth" })}
          >
            📊 Charts
          </button>
          <button
            type="button"
            onClick={() => document.getElementById("sc-config")?.scrollIntoView({ behavior: "smooth" })}
          >
            ⚙️ Config &amp; Logic
          </button>
          <button
            type="button"
            onClick={() => document.getElementById("sc-trades")?.scrollIntoView({ behavior: "smooth" })}
          >
            💼 Trades
          </button>
        </nav>
      ) : null}

      {!catalogLoading && catalog.length === 0 && !catalogError ? (
        <div className="sc-empty" data-testid="sc-empty-catalog">
          <h2>No saved strategies yet</h2>
          <p>
            Save a strategy in <Link to="/strategy-tester">Strategy Tester</Link> and complete a scan or LEAN backtest
            before comparing.
          </p>
        </div>
      ) : null}

      {readyInputs.length < 2 && catalog.length > 0 && !compareLoading ? (
        <div className="sc-empty" data-testid="sc-empty-state">
          <h2>Select two or more strategies</h2>
          <p>Pick existing Strategy Tester strategies. The latest completed run is selected automatically, and you can switch runs in the dropdown.</p>
        </div>
      ) : null}

      {readyInputs.length < 2 && suggestions.length > 0 ? (
        <div className="sc-related-wrap" data-testid="sc-related">
          <h2 className="sc-related-title">Related comparisons from your saved strategies</h2>
          <div className="sc-related">
            {suggestions.map((item) => (
              <button
                type="button"
                key={item.strategy_ids.join("-")}
                className="sc-related-card"
                onClick={() => applySuggestion(item)}
              >
                <h3>{item.title}</h3>
                <p>{item.subtitle}</p>
                <small>{item.names.join(" · ")}</small>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {compareError ? (
        <div className="sc-banner sc-banner--error" role="alert" data-testid="sc-compare-error">
          {compareError}
        </div>
      ) : null}

      {compareLoading ? (
        <div className="sc-section" aria-busy="true" data-testid="sc-loading">
          <div style={{ padding: 16, display: "grid", gap: 10 }}>
            <div className="sc-muted">Loading comparison from completed Strategy Tester runs…</div>
            <div className="sc-skeleton" />
            <div className="sc-skeleton" />
            <div className="sc-skeleton" style={{ width: "60%" }} />
          </div>
        </div>
      ) : null}

      {comparison ? (
        <>
          {comparison.config_warnings.length > 0 ? (
            <div className="sc-banner sc-banner--warn" data-testid="sc-config-warning">
              These runs used different backtest settings. Read metrics as separate experiments, not a like-for-like
              contest.
              <ul>
                {comparison.config_warnings.map((warn) => (
                  <li key={warn.field}>{warn.message}</li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="sc-section-note" style={{ paddingLeft: 0 }}>
              Backtest settings match across the selected runs.
            </div>
          )}

          <MetricSection comparison={comparison} cols={cols} highlight={highlightDiffs} />
          <SummarySection comparison={comparison} />
          <SignalSection comparison={comparison} search={signalSearch} onSearch={setSignalSearch} />
          <StrategyVennDiagram comparison={comparison} />
          <div id="sc-charts">
            <ComparisonCharts comparison={comparison} />
          </div>
          <ConfigSection comparison={comparison} cols={cols} highlight={highlightDiffs} />
          <LogicSection comparison={comparison} cols={cols} highlight={highlightDiffs} />
          {comparison.has_pine ? <PineSection comparison={comparison} /> : null}
          <TradeSection comparison={comparison} search={tradeSearch} onSearch={setTradeSearch} />
        </>
      ) : null}
    </div>
  );
}

function Grid({ cols, children }: { cols: number; children: ReactNode }) {
  return (
    <div className="sc-grid" style={{ ["--sc-cols" as string]: cols }}>
      {children}
    </div>
  );
}

function MetricSection({
  comparison,
  cols,
  highlight,
}: {
  comparison: ComparisonPayload;
  cols: number;
  highlight: boolean;
}) {
  const rows: Array<{
    label: string;
    higherIsBetter?: boolean;
    value: (slot: ComparisonPayload["slots"][number]) => number | null;
    render: (slot: ComparisonPayload["slots"][number]) => ReactNode;
  }> = [
    { label: "BUY signals", higherIsBetter: true, value: (s) => s.scan_summary?.buy ?? null, render: (s) => fmtNum(s.scan_summary?.buy, 0) },
    { label: "WATCH signals", value: (s) => s.scan_summary?.watch ?? null, render: (s) => fmtNum(s.scan_summary?.watch, 0) },
    { label: "REJECT signals", value: (s) => s.scan_summary?.reject ?? null, render: (s) => fmtNum(s.scan_summary?.reject, 0) },
    { label: "Win Rate", higherIsBetter: true, value: (s) => s.metrics.win_rate, render: (s) => fmtPct(s.metrics.win_rate) },
    { label: "Average return", higherIsBetter: true, value: (s) => s.metrics.average_trade, render: (s) => (s.metrics.average_trade_unit === "pct" ? fmtPct(s.metrics.average_trade) : fmtNum(s.metrics.average_trade)) },
    { label: "Total Return %", higherIsBetter: true, value: (s) => s.metrics.total_return_pct, render: (s) => <span className={signedClass(s.metrics.total_return_pct)}>{fmtPct(s.metrics.total_return_pct)}</span> },
    { label: "Net Profit", higherIsBetter: true, value: (s) => s.metrics.net_profit, render: (s) => <span className={signedClass(s.metrics.net_profit)}>{fmtInr(s.metrics.net_profit)}</span> },
    { label: "CAGR", higherIsBetter: true, value: (s) => s.metrics.cagr, render: (s) => fmtPct(s.metrics.cagr) },
    { label: "Total Trades", value: (s) => s.metrics.total_trades, render: (s) => fmtNum(s.metrics.total_trades, 0) },
    { label: "Profit Factor", higherIsBetter: true, value: (s) => s.metrics.profit_factor, render: (s) => fmtNum(s.metrics.profit_factor) },
    { label: "Max Drawdown", higherIsBetter: false, value: (s) => s.metrics.max_drawdown_pct ?? s.metrics.max_drawdown, render: (s) => (s.metrics.max_drawdown_pct != null ? fmtPct(s.metrics.max_drawdown_pct) : fmtInr(s.metrics.max_drawdown)) },
    { label: "Sharpe Ratio", higherIsBetter: true, value: (s) => s.metrics.sharpe_ratio, render: (s) => fmtNum(s.metrics.sharpe_ratio, 3) },
    { label: "Sortino Ratio", higherIsBetter: true, value: (s) => s.metrics.sortino_ratio, render: (s) => fmtNum(s.metrics.sortino_ratio, 3) },
    { label: "Long / Short trades", value: () => null, render: (s) => (s.metrics.long_trades == null && s.metrics.short_trades == null ? "—" : `${fmtNum(s.metrics.long_trades, 0)} / ${fmtNum(s.metrics.short_trades, 0)}`) },
    {
      label: "Best Trade",
      value: () => null,
      render: (s) =>
        s.metrics.best_trade
          ? `${s.metrics.best_trade.symbol || "—"} ${s.metrics.best_trade.return_pct != null ? fmtPct(s.metrics.best_trade.return_pct) : fmtInr(s.metrics.best_trade.net_pnl)}`
          : "—",
    },
    {
      label: "Worst Trade",
      value: () => null,
      render: (s) =>
        s.metrics.worst_trade
          ? `${s.metrics.worst_trade.symbol || "—"} ${s.metrics.worst_trade.return_pct != null ? fmtPct(s.metrics.worst_trade.return_pct) : fmtInr(s.metrics.worst_trade.net_pnl)}`
          : "—",
    },
    { label: "Final Equity", higherIsBetter: true, value: (s) => s.metrics.final_equity, render: (s) => fmtInr(s.metrics.final_equity) },
  ];
  return (
    <section className="sc-section" id="sc-metrics" data-testid="sc-metrics">
      <h2 className="sc-section-title">Performance</h2>
      <Grid cols={cols}>
        <div className="sc-grid-head">
          <div className="sc-cell">Metric</div>
          {comparison.slots.map((slot, i) => (
            <div className="sc-cell sc-cell--value" key={slot.slot_id}>
              <span className="sc-dot" style={{ background: SLOT_COLORS[i], marginRight: 8 }} />
              {slot.strategy_name}
              <span className={`sc-pill ${slot.source === "lean" ? "sc-pill--lean" : ""}`} style={{ marginLeft: 8 }}>
                {slot.source === "lean" ? "LEAN" : "Scan"}
              </span>
            </div>
          ))}
        </div>
        {rows.map((row) => {
          const hi = highlight && row.higherIsBetter != null ? strongerIndexes(comparison.slots.map(row.value), row.higherIsBetter) : new Set<number>();
          return (
            <div className="sc-grid-row" key={row.label}>
              <div className="sc-cell">{row.label}</div>
              {comparison.slots.map((slot, index) => (
                <div className={`sc-cell sc-cell--value ${hi.has(index) ? "sc-cell--hi" : ""}`} key={`${slot.slot_id}-${row.label}`}>
                  {row.render(slot)}
                </div>
              ))}
            </div>
          );
        })}
      </Grid>
      <p className="sc-section-note">
        {comparison.slots.some((s) => s.metrics.metrics_source === "strategy_tester")
          ? "Scan runs expose window returns and signal stats. Sharpe, Sortino, CAGR, drawdown and final equity appear when a LEAN backtest is selected. Missing values stay blank — they are not estimated."
          : comparison.slots[0]?.metrics.metrics_note}
      </p>
    </section>
  );
}

function SummarySection({ comparison }: { comparison: ComparisonPayload }) {
  return (
    <section className="sc-section" data-testid="sc-summary">
      <h2 className="sc-section-title">Side-by-side summary</h2>
      <div className="sc-summary">
        {comparison.slots.map((slot) => (
          <p key={slot.slot_id}>
            <strong>{slot.strategy_name}</strong>
            {slot.source === "lean"
              ? " (LEAN backtest)"
              : slot.source === "indicator_scan"
              ? " (Indicator scan)"
              : " (Strategy Tester scan)"}: win rate{" "}
            {fmtPct(slot.metrics.win_rate)}, total return {fmtPct(slot.metrics.total_return_pct)}, trades{" "}
            {fmtNum(slot.metrics.total_trades, 0)}
            {slot.metrics.sharpe_ratio != null ? `, Sharpe ${fmtNum(slot.metrics.sharpe_ratio, 3)}` : ""}
            {slot.config.start_date && slot.config.end_date
              ? `, window ${slot.config.start_date} → ${slot.config.end_date}`
              : ""}
            {slot.config.universe ? `, universe ${slot.config.universe}` : ""}.
          </p>
        ))}
        <p>
          Figures are copied from the selected completed runs. Score, Grade, and Rank in the summary table use the radar
          display scale only — they are not a trading recommendation.
        </p>
      </div>
    </section>
  );
}

function ConfigSection({
  comparison,
  cols,
  highlight,
}: {
  comparison: ComparisonPayload;
  cols: number;
  highlight: boolean;
}) {
  const rows = [
    { label: "Date range", key: (s: ComparisonPayload["slots"][number]) => `${s.config.start_date || "—"} → ${s.config.end_date || "—"}` },
    { label: "Universe", key: (s: ComparisonPayload["slots"][number]) => s.config.universe || "—" },
    { label: "Timeframe", key: (s: ComparisonPayload["slots"][number]) => s.config.timeframe || "—" },
    { label: "Initial capital", key: (s: ComparisonPayload["slots"][number]) => fmtInr(s.config.initial_capital) },
    { label: "Commission", key: (s: ComparisonPayload["slots"][number]) => (s.config.commission == null ? "—" : `${(s.config.commission * 100).toFixed(3)}%`) },
    { label: "Slippage", key: (s: ComparisonPayload["slots"][number]) => (s.config.slippage == null ? "—" : `${(s.config.slippage * 100).toFixed(3)}%`) },
    { label: "Position type", key: (s: ComparisonPayload["slots"][number]) => s.config.position_type || "—" },
  ];
  return (
    <section className="sc-section" data-testid="sc-config">
      <h2 className="sc-section-title">Backtest configuration</h2>
      <Grid cols={cols}>
        {rows.map((row) => {
          const mismatch = highlight && valuesDiffer(comparison.slots.map(row.key));
          return (
            <div className="sc-grid-row" key={row.label}>
              <div className="sc-cell">{row.label}</div>
              {comparison.slots.map((slot) => (
                <div className={`sc-cell sc-cell--value ${mismatch ? "sc-cell--mismatch" : ""}`} key={`${slot.slot_id}-${row.label}`}>
                  {row.key(slot)}
                </div>
              ))}
            </div>
          );
        })}
      </Grid>
    </section>
  );
}

function presence(value: string | null | undefined): ReactNode {
  if (!value) return <span className="sc-bool sc-bool--no">—</span>;
  return (
    <span className="sc-bool sc-bool--yes">
      ✓ {value}
    </span>
  );
}

function LogicSection({
  comparison,
  cols,
  highlight,
}: {
  comparison: ComparisonPayload;
  cols: number;
  highlight: boolean;
}) {
  const rows: Array<{
    label: string;
    render: (slot: ComparisonPayload["slots"][number]) => ReactNode;
    text: (slot: ComparisonPayload["slots"][number]) => string;
  }> = [
    { label: "Entry conditions", render: (s) => listOrDash(s.logic.entry_conditions), text: (s) => listOrDash(s.logic.entry_conditions) },
    { label: "Exit conditions", render: (s) => listOrDash(s.logic.exit_conditions), text: (s) => listOrDash(s.logic.exit_conditions) },
    { label: "Indicators", render: (s) => listOrDash(s.logic.indicators), text: (s) => listOrDash(s.logic.indicators) },
    { label: "Filters", render: (s) => listOrDash(s.logic.filters), text: (s) => listOrDash(s.logic.filters) },
    { label: "Stop loss", render: (s) => presence(s.logic.stop_loss), text: (s) => s.logic.stop_loss || "" },
    { label: "Take profit", render: (s) => presence(s.logic.take_profit), text: (s) => s.logic.take_profit || "" },
    { label: "Trailing stop", render: (s) => presence(s.logic.trailing_stop), text: (s) => s.logic.trailing_stop || "" },
    { label: "Position type", render: (s) => s.logic.position_type || "—", text: (s) => s.logic.position_type || "" },
  ];
  return (
    <section className="sc-section" data-testid="sc-logic">
      <h2 className="sc-section-title">Strategy logic</h2>
      <Grid cols={cols}>
        {rows.map((row) => {
          const mismatch = highlight && valuesDiffer(comparison.slots.map(row.text));
          return (
            <div className="sc-grid-row" key={row.label}>
              <div className="sc-cell">{row.label}</div>
              {comparison.slots.map((slot) => (
                <div className={`sc-cell sc-cell--stack ${mismatch ? "sc-cell--mismatch" : ""}`} key={`${slot.slot_id}-${row.label}`}>
                  {row.render(slot)}
                </div>
              ))}
            </div>
          );
        })}
      </Grid>
    </section>
  );
}

function PineSection({ comparison }: { comparison: ComparisonPayload }) {
  return (
    <section className="sc-section" data-testid="sc-pine">
      <h2 className="sc-section-title">Pine Script</h2>
      <div className="sc-pine" style={{ gridTemplateColumns: `repeat(${comparison.slots.length}, minmax(0, 1fr))` }}>
        {comparison.slots.map((slot, i) => (
          <div className="sc-pine-col" key={slot.slot_id}>
            <div className="sc-slot-top" style={{ marginBottom: 8 }}>
              <span className="sc-dot" style={{ background: SLOT_COLORS[i] }} />
              <strong>{slot.strategy_name}</strong>
            </div>
            {slot.logic.pine_code ? (
              <PineCodeEditor value={slot.logic.pine_code} onChange={() => undefined} readOnly />
            ) : (
              <div className="sc-chart-empty">No Pine Script on this strategy (builder rules only).</div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function SignalSection({
  comparison,
  search,
  onSearch,
}: {
  comparison: ComparisonPayload;
  search: string;
  onSearch: (v: string) => void;
}) {
  const { signals } = comparison;
  const q = search.trim().toUpperCase();
  const rows = signals.symbols.filter((row) => !q || row.symbol.includes(q));
  return (
    <section className="sc-section" id="sc-signals" data-testid="sc-signals">
      <h2 className="sc-section-title">Signal comparison</h2>
      {!signals.available ? (
        <p className="sc-section-note">{signals.unavailable_reason}</p>
      ) : (
        <>
          <div className="sc-legend">
            {signals.overlap_pct != null ? <span>Buy overlap {fmtPct(signals.overlap_pct)}</span> : null}
            {signals.pairwise.map((pair) => (
              <span key={`${pair.left_slot_id}-${pair.right_slot_id}`}>
                Shared {pair.shared_count} · left-only {pair.left_only_buy.length} · right-only {pair.right_only_buy.length}
              </span>
            ))}
          </div>
          {signals.pairwise.map((pair) => {
            const left = comparison.slots.find((s) => s.slot_id === pair.left_slot_id);
            const right = comparison.slots.find((s) => s.slot_id === pair.right_slot_id);
            return (
              <div className="sc-signal-lists" key={`${pair.left_slot_id}-${pair.right_slot_id}`}>
                <div className="sc-signal-box">
                  <h4>Shared BUY</h4>
                  <div className="sc-chips">{pair.shared_buy.slice(0, 40).map((sym) => <span className="sc-chip" key={sym}>{sym}</span>)}</div>
                  {pair.shared_buy.length === 0 ? <div className="sc-muted">None</div> : null}
                </div>
                <div className="sc-signal-box">
                  <h4>{left?.strategy_name} only</h4>
                  <div className="sc-chips">{pair.left_only_buy.slice(0, 40).map((sym) => <span className="sc-chip" key={sym}>{sym}</span>)}</div>
                </div>
                <div className="sc-signal-box">
                  <h4>{right?.strategy_name} only</h4>
                  <div className="sc-chips">{pair.right_only_buy.slice(0, 40).map((sym) => <span className="sc-chip" key={sym}>{sym}</span>)}</div>
                </div>
              </div>
            );
          })}
          <div className="sc-toolbar">
            <input className="sc-search" style={{ maxWidth: 280 }} placeholder="Filter symbols" value={search} onChange={(e) => onSearch(e.target.value)} />
            <span className="sc-muted">{signals.symbol_count} symbols</span>
          </div>
          <div className="sc-table-wrap">
            <table className="sc-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  {comparison.slots.map((slot) => (
                    <th key={slot.slot_id}>{slot.strategy_name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 200).map((row) => (
                  <tr key={row.symbol}>
                    <td>{row.symbol}</td>
                    {comparison.slots.map((slot) => (
                      <td key={slot.slot_id}>{row.signals[slot.slot_id] || "—"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function TradeSection({
  comparison,
  search,
  onSearch,
}: {
  comparison: ComparisonPayload;
  search: string;
  onSearch: (v: string) => void;
}) {
  const q = search.trim().toUpperCase();
  const rows = comparison.trades.symbols.filter((row) => !q || row.symbol.includes(q));
  return (
    <section className="sc-section" id="sc-trades" data-testid="sc-trades">
      <h2 className="sc-section-title">Trade comparison</h2>
      <div className="sc-toolbar">
        <input className="sc-search" style={{ maxWidth: 280 }} placeholder="Filter by symbol" value={search} onChange={(e) => onSearch(e.target.value)} data-testid="sc-trade-search" />
        <span className="sc-muted">{comparison.trades.symbol_count} symbols</span>
      </div>
      {rows.length === 0 ? (
        <p className="sc-section-note">No trades or window returns on the selected runs.</p>
      ) : (
        <div className="sc-table-wrap">
          <table className="sc-table">
            <thead>
              <tr>
                <th>Symbol</th>
                {comparison.slots.map((slot) => (
                  <th key={slot.slot_id} colSpan={6}>
                    {slot.strategy_name}
                  </th>
                ))}
              </tr>
              <tr>
                <th />
                {comparison.slots.map((slot) => (
                  <FragmentHeader key={slot.slot_id} />
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 250).map((row) => (
                <tr key={row.symbol}>
                  <td>{row.symbol}</td>
                  {comparison.slots.map((slot) => {
                    const trade = row.by_slot[slot.slot_id];
                    if (!trade) {
                      return (
                        <td key={slot.slot_id} colSpan={6} className="sc-muted">
                          —
                        </td>
                      );
                    }
                    return (
                      <TradeCells key={slot.slot_id} trade={trade} />
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function FragmentHeader() {
  return (
    <>
      <th>Entry</th>
      <th>Exit</th>
      <th>P&amp;L</th>
      <th>Return %</th>
      <th>Holding</th>
      <th>Exit reason</th>
    </>
  );
}

function TradeCells({ trade }: { trade: NonNullable<ComparisonPayload["trades"]["symbols"][number]["by_slot"][string]> }) {
  return (
    <>
      <td>
        {trade.entry_date || (trade.entry_price != null ? fmtNum(trade.entry_price) : "—")}
        {trade.entry_date && trade.entry_price != null ? <span className="sc-sub">{fmtNum(trade.entry_price)}</span> : null}
      </td>
      <td>
        {trade.exit_date || (trade.exit_price != null ? fmtNum(trade.exit_price) : "—")}
        {trade.exit_date && trade.exit_price != null ? <span className="sc-sub">{fmtNum(trade.exit_price)}</span> : null}
      </td>
      <td className={signedClass(trade.net_pnl)}>{fmtInr(trade.net_pnl)}</td>
      <td className={signedClass(trade.return_pct)}>{fmtPct(trade.return_pct)}</td>
      <td>{trade.holding_period != null ? `${trade.holding_period} bars` : trade.holding_window || "—"}</td>
      <td>{trade.exit_reason || "—"}</td>
    </>
  );
}

export default StrategyComparisonPage;
