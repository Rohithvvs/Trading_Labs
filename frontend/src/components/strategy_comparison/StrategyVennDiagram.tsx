import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ComparisonPayload } from "../../api_strategy_comparison";
import { SLOT_COLORS } from "./ComparisonCharts";

type VennRegion = {
  id: string;
  label: string;
  shortLabel: string;
  symbols: string[];
  slotsInvolved: number[];
  isIntersection: boolean;
  isUnion: boolean;
  color: string;
};

export function StrategyVennDiagram({ comparison }: { comparison: ComparisonPayload }) {
  const { slots = [], signals = { available: false, unavailable_reason: null, pairwise: [], overlap_pct: null, symbols: [], symbol_count: 0 } } = comparison;
  const numSlots = slots.length;

  const [selectedRegionId, setSelectedRegionId] = useState<string>("intersection");
  const [filterSearch, setFilterSearch] = useState<string>("");
  const [copied, setCopied] = useState<boolean>(false);

  const signalRows = useMemo(() => signals?.symbols || [], [signals?.symbols]);

  // Compute buy sets for each slot
  const buySets = useMemo(() => {
    return slots.map((slot) => {
      const set = new Set<string>();
      for (const row of signalRows) {
        if (row?.signals?.[slot.slot_id] === "BUY") {
          set.add(row.symbol);
        }
      }
      return set;
    });
  }, [slots, signalRows]);

  // Compute union, intersection, and regional subsets
  const vennData = useMemo(() => {
    const totalBuySymbols = new Set<string>();
    for (const set of buySets) {
      for (const sym of set) {
        totalBuySymbols.add(sym);
      }
    }

    // 1. Unanimous Intersection (present in ALL selected slots)
    const unanimousIntersection: string[] = [];
    // 2. Shared in at least 2 slots
    const sharedAny2Plus: string[] = [];
    // 3. Exclusives per slot
    const exclusivesPerSlot: string[][] = slots.map(() => []);

    for (const sym of totalBuySymbols) {
      const matchCount = buySets.filter((set) => set.has(sym)).length;
      if (matchCount === numSlots && numSlots > 1) {
        unanimousIntersection.push(sym);
      }
      if (matchCount >= 2) {
        sharedAny2Plus.push(sym);
      }
      if (matchCount === 1) {
        const slotIdx = buySets.findIndex((set) => set.has(sym));
        if (slotIdx >= 0) {
          exclusivesPerSlot[slotIdx].push(sym);
        }
      }
    }

    unanimousIntersection.sort();
    sharedAny2Plus.sort();
    exclusivesPerSlot.forEach((arr) => arr.sort());

    const totalBuyArray = Array.from(totalBuySymbols).sort();

    // Specific Pairwise Regions
    const regions: VennRegion[] = [];

    // Region: Unanimous Intersection
    regions.push({
      id: "intersection",
      label: `All ${numSlots} Strategies Consensus (∩)`,
      shortLabel: "Consensus ∩",
      symbols: unanimousIntersection,
      slotsInvolved: slots.map((_, i) => i),
      isIntersection: true,
      isUnion: false,
      color: "#eab308", // Gold
    });

    if (numSlots === 3) {
      // Pairwise between (0 & 1) excluding 2
      const pair01 = Array.from(buySets[0] || [])
        .filter((s) => buySets[1]?.has(s) && !buySets[2]?.has(s))
        .sort();
      regions.push({
        id: "pair_0_1",
        label: `${slots[0]?.strategy_name || "S1"} ∩ ${slots[1]?.strategy_name || "S2"} (only)`,
        shortLabel: `${(slots[0]?.strategy_name || "S1").slice(0, 10)} ∩ ${(slots[1]?.strategy_name || "S2").slice(0, 10)}`,
        symbols: pair01,
        slotsInvolved: [0, 1],
        isIntersection: true,
        isUnion: false,
        color: "#60a5fa",
      });

      // Pairwise between (0 & 2) excluding 1
      const pair02 = Array.from(buySets[0] || [])
        .filter((s) => buySets[2]?.has(s) && !buySets[1]?.has(s))
        .sort();
      regions.push({
        id: "pair_0_2",
        label: `${slots[0]?.strategy_name || "S1"} ∩ ${slots[2]?.strategy_name || "S3"} (only)`,
        shortLabel: `${(slots[0]?.strategy_name || "S1").slice(0, 10)} ∩ ${(slots[2]?.strategy_name || "S3").slice(0, 10)}`,
        symbols: pair02,
        slotsInvolved: [0, 2],
        isIntersection: true,
        isUnion: false,
        color: "#34d399",
      });

      // Pairwise between (1 & 2) excluding 0
      const pair12 = Array.from(buySets[1] || [])
        .filter((s) => buySets[2]?.has(s) && !buySets[0]?.has(s))
        .sort();
      regions.push({
        id: "pair_1_2",
        label: `${slots[1]?.strategy_name || "S2"} ∩ ${slots[2]?.strategy_name || "S3"} (only)`,
        shortLabel: `${(slots[1]?.strategy_name || "S2").slice(0, 10)} ∩ ${(slots[2]?.strategy_name || "S3").slice(0, 10)}`,
        symbols: pair12,
        slotsInvolved: [1, 2],
        isIntersection: true,
        isUnion: false,
        color: "#a78bfa",
      });
    }

    // Exclusives for each strategy
    slots.forEach((slot, i) => {
      regions.push({
        id: `only_${i}`,
        label: `${slot.strategy_name} Exclusive Only`,
        shortLabel: `${(slot.strategy_name || `S${i+1}`).slice(0, 12)} Only`,
        symbols: exclusivesPerSlot[i] || [],
        slotsInvolved: [i],
        isIntersection: false,
        isUnion: false,
        color: SLOT_COLORS[i % SLOT_COLORS.length],
      });
    });

    // Region: Total Union
    regions.push({
      id: "union",
      label: `Total Union of All Strategies (∪)`,
      shortLabel: "Total Union ∪",
      symbols: totalBuyArray,
      slotsInvolved: slots.map((_, i) => i),
      isIntersection: false,
      isUnion: true,
      color: "#38bdf8", // Sky blue
    });

    const jaccard = totalBuyArray.length > 0 ? (unanimousIntersection.length / totalBuyArray.length) * 100 : 0;

    return {
      totalBuyCount: totalBuyArray.length,
      intersectionCount: unanimousIntersection.length,
      sharedAny2Count: sharedAny2Plus.length,
      jaccard,
      regions,
      unanimousIntersection,
      exclusivesPerSlot,
    };
  }, [slots, buySets, numSlots]);

  const activeRegion = vennData.regions.find((r) => r.id === selectedRegionId) || vennData.regions[0];

  const filteredSymbols = useMemo(() => {
    const q = filterSearch.trim().toUpperCase();
    if (!q) return activeRegion.symbols;
    return activeRegion.symbols.filter((sym) => sym.includes(q));
  }, [activeRegion.symbols, filterSearch]);

  const handleCopy = () => {
    if (!filteredSymbols.length) return;
    navigator.clipboard.writeText(filteredSymbols.join(", "));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section id="sc-venn-section" className="sc-section sc-venn-section" data-testid="sc-venn-section">
      <div className="sc-venn-header">
        <div>
          <h2 className="sc-section-title">Venn Diagram Representation</h2>
          <p className="sc-section-subtitle">
            Mathematical Union (<span className="sc-math-op">∪</span>) and Intersection (<span className="sc-math-op">∩</span>) of candidate stocks across all {numSlots} selected strategies.
          </p>
        </div>

        {/* High-level Metric Stat Badges */}
        <div className="sc-venn-stats">
          <div className="sc-venn-stat-card sc-venn-stat-card--consensus">
            <span className="sc-venn-stat-label">Unanimous Consensus (∩)</span>
            <strong className="sc-venn-stat-value">{vennData.intersectionCount}</strong>
            <small>Matched by all {numSlots} strategies</small>
          </div>
          <div className="sc-venn-stat-card sc-venn-stat-card--union">
            <span className="sc-venn-stat-label">Total Union (∪)</span>
            <strong className="sc-venn-stat-value">{vennData.totalBuyCount}</strong>
            <small>Unique candidates identified</small>
          </div>
          <div className="sc-venn-stat-card">
            <span className="sc-venn-stat-label">Jaccard Consensus</span>
            <strong className="sc-venn-stat-value">{vennData.jaccard.toFixed(1)}%</strong>
            <small>Intersection / Union agreement ratio</small>
          </div>
        </div>
      </div>

      <div className="sc-venn-layout">
        {/* Left Side: Interactive SVG Graphic */}
        <div className="sc-venn-canvas-wrap">
          {numSlots === 2 ? (
            <Venn2Graphic
              slots={slots}
              buySets={buySets}
              activeId={selectedRegionId}
              onSelect={setSelectedRegionId}
            />
          ) : numSlots === 3 ? (
            <Venn3Graphic
              slots={slots}
              buySets={buySets}
              activeId={selectedRegionId}
              onSelect={setSelectedRegionId}
            />
          ) : (
            <VennMultiGraphic
              slots={slots}
              buySets={buySets}
              activeId={selectedRegionId}
              onSelect={setSelectedRegionId}
            />
          )}
          <div className="sc-venn-caption">
            Click on any circle region or tab to inspect the candidate stocks inside that set.
          </div>
        </div>

        {/* Right Side: Region Selector & Symbol Explorer */}
        <div className="sc-venn-panel">
          <div className="sc-venn-tabs-bar">
            {vennData.regions.map((reg) => {
              const isActive = reg.id === selectedRegionId;
              return (
                <button
                  key={reg.id}
                  type="button"
                  className={`sc-venn-tab ${isActive ? "sc-venn-tab--active" : ""}`}
                  style={{ borderColor: isActive ? reg.color : undefined }}
                  onClick={() => setSelectedRegionId(reg.id)}
                >
                  <span className="sc-venn-tab-dot" style={{ background: reg.color }} />
                  <span className="sc-venn-tab-title">{reg.shortLabel}</span>
                  <span className="sc-venn-tab-badge">{reg.symbols.length}</span>
                </button>
              );
            })}
          </div>

          <div className="sc-venn-active-desc">
            <div className="sc-venn-active-title-row">
              <h3 style={{ color: activeRegion.color }}>
                {activeRegion.label}
              </h3>
              <div className="sc-venn-actions">
                <button
                  type="button"
                  className="sc-btn sc-btn-sm"
                  onClick={handleCopy}
                  title="Copy comma-separated symbols to clipboard"
                >
                  {copied ? "✓ Copied!" : "Copy Symbols"}
                </button>
              </div>
            </div>
            <div className="sc-toolbar" style={{ marginTop: 8 }}>
              <input
                className="sc-search"
                style={{ maxWidth: 260 }}
                placeholder={`Search ${activeRegion.symbols.length} symbols…`}
                value={filterSearch}
                onChange={(e) => setFilterSearch(e.target.value)}
              />
              <span className="sc-muted">
                Showing {filteredSymbols.length} of {activeRegion.symbols.length}
              </span>
            </div>
          </div>

          <div className="sc-venn-chips-grid">
            {filteredSymbols.length === 0 ? (
              <div className="sc-chart-empty" style={{ padding: 24 }}>
                {activeRegion.symbols.length === 0
                  ? "No stocks in this specific intersection region."
                  : "No symbols matching your search filter."}
              </div>
            ) : (
              filteredSymbols.map((sym) => {
                const approvingSlots = slots.filter((slot) => {
                  const row = signalRows.find((r) => r.symbol === sym);
                  return row?.signals?.[slot.slot_id] === "BUY";
                });

                return (
                  <div className="sc-stock-card" key={sym}>
                    <div className="sc-stock-card-header">
                      <strong className="sc-stock-card-sym">{sym}</strong>
                      <Link
                        to={`/paper/order?symbol=${encodeURIComponent(sym)}`}
                        className="sc-stock-card-trade-link"
                        title={`Place Paper Order for ${sym}`}
                      >
                        Trade ↗
                      </Link>
                    </div>
                    <div className="sc-stock-card-badges">
                      {approvingSlots.map((slot) => (
                        <span
                          key={slot.slot_id}
                          className="sc-stock-slot-badge"
                          style={{
                            borderColor: SLOT_COLORS[slots.indexOf(slot) % SLOT_COLORS.length],
                            color: SLOT_COLORS[slots.indexOf(slot) % SLOT_COLORS.length],
                          }}
                        >
                          ● {(slot.strategy_name || "Strategy").slice(0, 14)}…
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

// 2-Set Venn SVG Graphic
function Venn2Graphic({
  slots,
  buySets,
  activeId,
  onSelect,
}: {
  slots: ComparisonPayload["slots"];
  buySets: Set<string>[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  const setA = buySets[0] || new Set<string>();
  const setB = buySets[1] || new Set<string>();

  const onlyA = [...setA].filter((s) => !setB.has(s)).length;
  const onlyB = [...setB].filter((s) => !setA.has(s)).length;
  const inter = [...setA].filter((s) => setB.has(s)).length;

  const nameA = slots[0]?.strategy_name || "Strategy 1";
  const nameB = slots[1]?.strategy_name || "Strategy 2";

  return (
    <svg viewBox="0 0 540 320" className="sc-venn-svg">
      <defs>
        <filter id="glow-gold" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="6" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* Circle A */}
      <circle
        cx="200"
        cy="160"
        r="120"
        fill={SLOT_COLORS[0]}
        fillOpacity={activeId === "only_0" ? 0.45 : 0.22}
        stroke={SLOT_COLORS[0]}
        strokeWidth={activeId === "only_0" ? 3 : 1.5}
        className="sc-venn-circle"
        onClick={() => onSelect("only_0")}
      />

      {/* Circle B */}
      <circle
        cx="340"
        cy="160"
        r="120"
        fill={SLOT_COLORS[1]}
        fillOpacity={activeId === "only_1" ? 0.45 : 0.22}
        stroke={SLOT_COLORS[1]}
        strokeWidth={activeId === "only_1" ? 3 : 1.5}
        className="sc-venn-circle"
        onClick={() => onSelect("only_1")}
      />

      {/* Intersection Region Center Marker */}
      <circle
        cx="270"
        cy="160"
        r="44"
        fill="#eab308"
        fillOpacity={activeId === "intersection" ? 0.6 : 0.35}
        stroke="#eab308"
        strokeWidth={activeId === "intersection" ? 3 : 1.5}
        className="sc-venn-circle sc-venn-center"
        onClick={() => onSelect("intersection")}
        filter={activeId === "intersection" ? "url(#glow-gold)" : undefined}
      />

      {/* Text & Count Labels */}
      <text x="130" y="80" fill={SLOT_COLORS[0]} fontWeight="700" fontSize="13">
        {nameA.slice(0, 18)}…
      </text>
      <text
        x="150"
        y="165"
        fill="#ffffff"
        fontWeight="800"
        fontSize="22"
        textAnchor="middle"
        onClick={() => onSelect("only_0")}
        className="sc-venn-count-text"
      >
        {onlyA}
      </text>
      <text x="150" y="185" fill="#94a3b8" fontSize="11" textAnchor="middle">
        Exclusive
      </text>

      {/* Intersection Label */}
      <text
        x="270"
        y="155"
        fill="#ffffff"
        fontWeight="900"
        fontSize="24"
        textAnchor="middle"
        onClick={() => onSelect("intersection")}
        className="sc-venn-count-text"
      >
        {inter}
      </text>
      <text x="270" y="175" fill="#fef08a" fontWeight="700" fontSize="11" textAnchor="middle">
        A ∩ B
      </text>

      {/* Set B Label */}
      <text x="330" y="80" fill={SLOT_COLORS[1]} fontWeight="700" fontSize="13">
        {nameB.slice(0, 18)}…
      </text>
      <text
        x="390"
        y="165"
        fill="#ffffff"
        fontWeight="800"
        fontSize="22"
        textAnchor="middle"
        onClick={() => onSelect("only_1")}
        className="sc-venn-count-text"
      >
        {onlyB}
      </text>
      <text x="390" y="185" fill="#94a3b8" fontSize="11" textAnchor="middle">
        Exclusive
      </text>
    </svg>
  );
}

// 3-Set Classic Venn SVG Graphic
function Venn3Graphic({
  slots,
  buySets,
  activeId,
  onSelect,
}: {
  slots: ComparisonPayload["slots"];
  buySets: Set<string>[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  const s0 = buySets[0] || new Set<string>();
  const s1 = buySets[1] || new Set<string>();
  const s2 = buySets[2] || new Set<string>();

  const name0 = slots[0]?.strategy_name || "Strategy 1";
  const name1 = slots[1]?.strategy_name || "Strategy 2";
  const name2 = slots[2]?.strategy_name || "Strategy 3";

  const triple = [...s0].filter((x) => s1.has(x) && s2.has(x)).length;
  const p01 = [...s0].filter((x) => s1.has(x) && !s2.has(x)).length;
  const p12 = [...s1].filter((x) => s2.has(x) && !s0.has(x)).length;
  const p02 = [...s0].filter((x) => s2.has(x) && !s1.has(x)).length;
  const only0 = [...s0].filter((x) => !s1.has(x) && !s2.has(x)).length;
  const only1 = [...s1].filter((x) => !s0.has(x) && !s2.has(x)).length;
  const only2 = [...s2].filter((x) => !s0.has(x) && !s1.has(x)).length;

  return (
    <svg viewBox="0 0 560 480" className="sc-venn-svg">
      <defs>
        <filter id="glow-gold-3" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="8" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* Circle 0 (Top Center) */}
      <circle
        cx="280"
        cy="180"
        r="130"
        fill={SLOT_COLORS[0]}
        fillOpacity={activeId === "only_0" ? 0.45 : 0.18}
        stroke={SLOT_COLORS[0]}
        strokeWidth={activeId === "only_0" ? 3 : 1.5}
        className="sc-venn-circle"
        onClick={() => onSelect("only_0")}
      />

      {/* Circle 1 (Bottom Left) */}
      <circle
        cx="195"
        cy="310"
        r="130"
        fill={SLOT_COLORS[1]}
        fillOpacity={activeId === "only_1" ? 0.45 : 0.18}
        stroke={SLOT_COLORS[1]}
        strokeWidth={activeId === "only_1" ? 3 : 1.5}
        className="sc-venn-circle"
        onClick={() => onSelect("only_1")}
      />

      {/* Circle 2 (Bottom Right) */}
      <circle
        cx="365"
        cy="310"
        r="130"
        fill={SLOT_COLORS[2]}
        fillOpacity={activeId === "only_2" ? 0.45 : 0.18}
        stroke={SLOT_COLORS[2]}
        strokeWidth={activeId === "only_2" ? 3 : 1.5}
        className="sc-venn-circle"
        onClick={() => onSelect("only_2")}
      />

      {/* Pairwise Lenses Clickable Targets */}
      <ellipse
        cx="225"
        cy="225"
        rx="28"
        ry="24"
        fill="#60a5fa"
        fillOpacity={activeId === "pair_0_1" ? 0.6 : 0.3}
        className="sc-venn-circle"
        onClick={() => onSelect("pair_0_1")}
      />
      <ellipse
        cx="335"
        cy="225"
        rx="28"
        ry="24"
        fill="#34d399"
        fillOpacity={activeId === "pair_0_2" ? 0.6 : 0.3}
        className="sc-venn-circle"
        onClick={() => onSelect("pair_0_2")}
      />
      <ellipse
        cx="280"
        cy="330"
        rx="32"
        ry="22"
        fill="#a78bfa"
        fillOpacity={activeId === "pair_1_2" ? 0.6 : 0.3}
        className="sc-venn-circle"
        onClick={() => onSelect("pair_1_2")}
      />

      {/* Triple Center Intersection */}
      <circle
        cx="280"
        cy="260"
        r="36"
        fill="#eab308"
        fillOpacity={activeId === "intersection" ? 0.8 : 0.45}
        stroke="#fef08a"
        strokeWidth={activeId === "intersection" ? 3.5 : 1.5}
        className="sc-venn-circle sc-venn-center"
        onClick={() => onSelect("intersection")}
        filter={activeId === "intersection" ? "url(#glow-gold-3)" : undefined}
      />

      {/* Labels & Counts */}
      <text x="280" y="32" fill={SLOT_COLORS[0]} fontWeight="700" fontSize="13" textAnchor="middle">
        {name0.slice(0, 24)}
      </text>
      <text
        x="280"
        y="125"
        fill="#ffffff"
        fontWeight="800"
        fontSize="22"
        textAnchor="middle"
        onClick={() => onSelect("only_0")}
        className="sc-venn-count-text"
      >
        {only0}
      </text>
      <text x="280" y="142" fill="#94a3b8" fontSize="10" textAnchor="middle">
        Exclusive
      </text>

      <text x="120" y="440" fill={SLOT_COLORS[1]} fontWeight="700" fontSize="13" textAnchor="middle">
        {name1.slice(0, 22)}…
      </text>
      <text
        x="150"
        y="330"
        fill="#ffffff"
        fontWeight="800"
        fontSize="22"
        textAnchor="middle"
        onClick={() => onSelect("only_1")}
        className="sc-venn-count-text"
      >
        {only1}
      </text>
      <text x="150" y="347" fill="#94a3b8" fontSize="10" textAnchor="middle">
        Exclusive
      </text>

      <text x="440" y="440" fill={SLOT_COLORS[2]} fontWeight="700" fontSize="13" textAnchor="middle">
        {name2.slice(0, 22)}…
      </text>
      <text
        x="410"
        y="330"
        fill="#ffffff"
        fontWeight="800"
        fontSize="22"
        textAnchor="middle"
        onClick={() => onSelect("only_2")}
        className="sc-venn-count-text"
      >
        {only2}
      </text>
      <text x="410" y="347" fill="#94a3b8" fontSize="10" textAnchor="middle">
        Exclusive
      </text>

      {/* Pairwise Counts */}
      <text
        x="225"
        y="230"
        fill="#ffffff"
        fontWeight="800"
        fontSize="15"
        textAnchor="middle"
        onClick={() => onSelect("pair_0_1")}
        className="sc-venn-count-text"
      >
        {p01}
      </text>
      <text
        x="335"
        y="230"
        fill="#ffffff"
        fontWeight="800"
        fontSize="15"
        textAnchor="middle"
        onClick={() => onSelect("pair_0_2")}
        className="sc-venn-count-text"
      >
        {p02}
      </text>
      <text
        x="280"
        y="335"
        fill="#ffffff"
        fontWeight="800"
        fontSize="15"
        textAnchor="middle"
        onClick={() => onSelect("pair_1_2")}
        className="sc-venn-count-text"
      >
        {p12}
      </text>

      {/* Triple Center Count */}
      <text
        x="280"
        y="262"
        fill="#ffffff"
        fontWeight="900"
        fontSize="22"
        textAnchor="middle"
        onClick={() => onSelect("intersection")}
        className="sc-venn-count-text"
      >
        {triple}
      </text>
      <text x="280" y="278" fill="#fef08a" fontWeight="800" fontSize="9" textAnchor="middle">
        ⭐ ALL 3
      </text>
    </svg>
  );
}

// 4-Set Multi Graphic
function VennMultiGraphic({
  slots,
  buySets,
  activeId,
  onSelect,
}: {
  slots: ComparisonPayload["slots"];
  buySets: Set<string>[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="sc-venn-multi-grid">
      <div className="sc-venn-multi-header">
        <h4>Multi-Strategy Set Breakdown ({slots.length} Strategies)</h4>
      </div>
      <div className="sc-venn-multi-cards">
        {slots.map((slot, i) => (
          <div
            key={slot.slot_id}
            className={`sc-venn-multi-card ${activeId === `only_${i}` ? "sc-venn-multi-card--active" : ""}`}
            style={{ borderLeftColor: SLOT_COLORS[i % SLOT_COLORS.length] }}
            onClick={() => onSelect(`only_${i}`)}
          >
            <div className="sc-venn-multi-card-title">{slot.strategy_name}</div>
            <div className="sc-venn-multi-card-count">{buySets[i]?.size || 0} Total BUYs</div>
          </div>
        ))}
      </div>
    </div>
  );
}
