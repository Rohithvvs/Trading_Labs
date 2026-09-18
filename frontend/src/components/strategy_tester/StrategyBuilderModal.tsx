import React, { useEffect, useState, useMemo } from "react";
import { PineCodeEditor } from "./PineCodeEditor";
import { parsePineScript, DEFAULT_PINE_TEMPLATE, ModalBuilderFilter } from "../../utils/pineParser";
import { IndicatorEditorPanel } from "./IndicatorEditorPanel";
import type { SavedIndicator } from "../../api_indicator_scanner";

export type { ModalBuilderFilter };

export interface StrategyBuilderModalProps {
  isOpen: boolean;
  initialName: string;
  initialDescription: string;
  initialFilters: ModalBuilderFilter[];
  initialLogic: "ALL" | "ANY";
  initialSide: "LONG" | "SHORT";
  initialSource?: "builder" | "pine";
  initialPineCode?: string;
  initialTab?: "builder" | "pine" | "indicator";
  editingIndicator?: SavedIndicator | null;
  onClose: () => void;
  onApply: (
    name: string,
    description: string,
    filters: ModalBuilderFilter[],
    logic: "ALL" | "ANY",
    side: "LONG" | "SHORT",
    source?: "builder" | "pine",
    pineCode?: string
  ) => void;
  onApplyIndicator?: (indicator: SavedIndicator, applyToScreener?: boolean) => void;
}

const FIELD_OPTIONS = [
  { value: "CLOSE", label: "Close Price" },
  { value: "OPEN", label: "Open Price" },
  { value: "HIGH", label: "High Price" },
  { value: "LOW", label: "Low Price" },
  { value: "VOLUME", label: "Volume" },
  { value: "AVG_VOLUME", label: "Average Volume" },
  { value: "REL_VOLUME", label: "Relative Volume" },
  { value: "PREV_CLOSE", label: "Previous Close" },
  { value: "PREV_HIGH", label: "Previous Day High" },
  { value: "DAILY_RETURN", label: "Daily Return" },
  { value: "GAP_PCT", label: "Gap %" },
  { value: "BENCHMARK_CLOSE", label: "NIFTY 500 Close" },
  { value: "SMA", label: "SMA" },
  { value: "EMA", label: "EMA" },
  { value: "WMA", label: "WMA" },
  { value: "RSI", label: "RSI" },
  { value: "MACD", label: "MACD Line" },
  { value: "VWAP", label: "VWAP" },
  { value: "ATR", label: "ATR" },
  { value: "BB_UPPER", label: "Upper Bollinger Band" },
  { value: "BB_MIDDLE", label: "Middle Bollinger Band" },
  { value: "BB_LOWER", label: "Lower Bollinger Band" },
  { value: "BB_WIDTH", label: "Bollinger Band Width" },
  { value: "HV", label: "Historical Volatility" },
];

const OPERATORS = [
  { value: ">", label: "> (Greater than)" },
  { value: "<", label: "< (Less than)" },
  { value: ">=", label: ">= (Greater or equal)" },
  { value: "<=", label: "<= (Less or equal)" },
  { value: "==", label: "== (Equal to)" },
  { value: "!=", label: "!= (Not equal)" },
  { value: "cross_above", label: "Crosses Above" },
  { value: "cross_below", label: "Crosses Below" },
  { value: "between", label: "Between" },
  { value: "outside", label: "Outside" },
];

export const StrategyBuilderModal: React.FC<StrategyBuilderModalProps> = ({
  isOpen,
  initialName,
  initialDescription,
  initialFilters,
  initialLogic,
  initialSide,
  initialSource = "builder",
  initialPineCode = DEFAULT_PINE_TEMPLATE,
  initialTab = "builder",
  editingIndicator = null,
  onClose,
  onApply,
  onApplyIndicator,
}) => {
  const [activeTab, setActiveTab] = useState<"builder" | "pine" | "indicator">(initialTab);

  useEffect(() => {
    if (isOpen) setActiveTab(initialTab);
  }, [isOpen, initialTab]);
  const [name, setName] = useState(initialName || "Momentum Strategy");
  const [description, setDescription] = useState(initialDescription || "");
  const [filters, setFilters] = useState<ModalBuilderFilter[]>(() =>
    initialFilters.length > 0
      ? JSON.parse(JSON.stringify(initialFilters))
      : [
          { id: "1", field: "CLOSE", operator: ">", rightKind: "indicator", literal: "", indicator: "SMA", indicatorPeriod: "50", low: "", high: "" },
          { id: "2", field: "SMA", period: "50", operator: ">", rightKind: "indicator", literal: "", indicator: "SMA", indicatorPeriod: "200", low: "", high: "" },
          { id: "3", field: "RSI", period: "14", operator: ">", rightKind: "literal", literal: "55", indicator: "SMA", indicatorPeriod: "20", low: "", high: "" },
          { id: "4", field: "VOLUME", operator: ">", rightKind: "indicator", literal: "", indicator: "AVG_VOLUME", indicatorPeriod: "20", low: "", high: "" },
        ]
  );
  const [logic, setLogic] = useState<"ALL" | "ANY">(initialLogic || "ALL");
  const [side, setSide] = useState<"LONG" | "SHORT">(initialSide || "LONG");
  const [sourceType, setSourceType] = useState<"builder" | "pine">(initialSource);
  const [pineCode, setPineCode] = useState<string>(initialPineCode || DEFAULT_PINE_TEMPLATE);

  const [isUserModified, setIsUserModified] = useState<boolean>(false);
  const [confirmReplaceOpen, setConfirmReplaceOpen] = useState<boolean>(false);
  const [pendingResult, setPendingResult] = useState<any | null>(null);
  const [showDebugTrace, setShowDebugTrace] = useState<boolean>(false);

  const [pineError, setPineError] = useState<string | null>(null);
  const [pineWarnings, setPineWarnings] = useState<string[]>([]);
  const [pineImportSummary, setPineImportSummary] = useState<{
    title: string;
    filterCount: number;
    benchmarkText?: string | null;
    exitText?: string | null;
    riskText?: string | null;
    rankingText?: string | null;
    side: "LONG" | "SHORT";
    logic: "ALL" | "ANY";
    debugTrace?: any[];
  } | null>(null);

  const detectedVersion = useMemo(() => {
    const vMatch = pineCode.match(/\/\/\s*@version\s*=\s*(\d+)/i);
    if (vMatch && vMatch[1]) {
      const vNum = parseInt(vMatch[1], 10);
      if (vNum === 5 || vNum === 6) {
        return { text: `Pine Script version detected: v${vNum}`, isSupported: true };
      }
      return { text: `Unsupported Pine Script version (v${vNum}). Please use Pine Script v5/v6.`, isSupported: false };
    }
    return { text: `Pine Script version detected: v6 (default)`, isSupported: true };
  }, [pineCode]);

  if (!isOpen) return null;

  const handleAddFilter = () => {
    setIsUserModified(true);
    const newId = `f_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setFilters([
      ...filters,
      {
        id: newId,
        field: "CLOSE",
        operator: ">",
        rightKind: "indicator",
        literal: "",
        indicator: "SMA",
        indicatorPeriod: "50",
        low: "",
        high: "",
      },
    ]);
  };

  const handleRemoveFilter = (index: number) => {
    if (filters.length <= 1) return;
    setIsUserModified(true);
    setFilters(filters.filter((_, i) => i !== index));
  };

  const handleFilterChange = (
    index: number,
    keyOrUpdates: keyof ModalBuilderFilter | Partial<ModalBuilderFilter>,
    value?: any
  ) => {
    setIsUserModified(true);
    setFilters((prev) => {
      const copy = [...prev];
      if (typeof keyOrUpdates === "string") {
        copy[index] = { ...copy[index], [keyOrUpdates]: value };
      } else {
        copy[index] = { ...copy[index], ...keyOrUpdates };
      }
      return copy;
    });
  };

  const applyParsedResult = (res: any) => {
    setName(res.strategyName);
    if (res.description) setDescription(res.description);
    setSide(res.positionSide);
    setLogic(res.logic);
    setFilters(res.filters);
    setSourceType("pine");
    setPineWarnings(res.warnings || []);

    const benchmarkText = res.benchmarkFilter?.label || (res.parsedStrategy?.benchmarkConditions?.[0]?.label ?? null);
    const exitText = res.exitConditions?.[0]?.conditionText ? `Exit: ${res.exitConditions[0].conditionText}` : null;
    const riskText = res.riskRules?.[0]?.description ?? null;
    const rankingText = res.rankingRule?.description ? `Ranking: ${res.rankingRule.description}` : null;

    setPineImportSummary({
      title: `✓ Pine Script analyzed successfully`,
      filterCount: res.filters.length,
      benchmarkText,
      exitText,
      riskText,
      rankingText,
      side: res.positionSide,
      logic: res.logic,
      debugTrace: res.debugTrace,
    });

    setConfirmReplaceOpen(false);
    setPendingResult(null);
    setActiveTab("builder");
  };

  const handleObserveFilters = () => {
    setPineError(null);
    setPineWarnings([]);

    if (!pineCode.trim()) {
      setPineError("Please enter Pine Script code first.");
      return;
    }

    const res = parsePineScript(pineCode, { debug: true });

    if (!res.success && res.errors.length > 0) {
      setPineError(`✕ Unable to analyze Pine Script\n\n${res.errors.join("\n")}\n\nPlease fix the Pine Script and try again.`);
      return;
    }

    if (res.filters.length === 0) {
      if (res.warnings.length > 0) {
        setPineWarnings(res.warnings);
      } else {
        setPineError("No supported entry filters were detected.\n\nPlease review the Pine Script or manually configure the Strategy Builder.");
      }
      return;
    }

    // Check if user has already modified manual filters -> show data-loss protection dialog
    if (isUserModified && filters.length > 0) {
      setPendingResult(res);
      setConfirmReplaceOpen(true);
      return;
    }

    // Auto-populate Strategy Builder state
    applyParsedResult(res);
  };

  const handleSave = () => {
    if (!name.trim()) {
      alert("Please enter a strategy name.");
      return;
    }
    if (filters.length === 0) {
      alert("Please configure at least one filter condition.");
      return;
    }

    onApply(name.trim(), description.trim(), filters, logic, side, sourceType, pineCode);
    onClose();
  };

  return (
    <div className="st-modal-overlay" onClick={onClose} data-testid="modal-strategy-builder">
      <div
        className="st-modal-card"
        style={{ maxWidth: activeTab === "indicator" ? 960 : 720, height: activeTab === "indicator" ? "min(90vh, 860px)" : undefined }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header Tabs */}
        <div className="st-modal-tabs-header">
          <button
            type="button"
            className={`st-modal-tab-btn ${activeTab === "builder" ? "is-active" : ""}`}
            onClick={() => setActiveTab("builder")}
            data-testid="tab-strategy-builder"
          >
            Strategy Builder
          </button>
          <button
            type="button"
            className={`st-modal-tab-btn ${activeTab === "pine" ? "is-active" : ""}`}
            onClick={() => setActiveTab("pine")}
            data-testid="tab-pine-script"
          >
            Pine Script
          </button>
          <button
            type="button"
            className={`st-modal-tab-btn ${activeTab === "indicator" ? "is-active" : ""}`}
            onClick={() => setActiveTab("indicator")}
            data-testid="tab-indicator"
          >
            Indicator
          </button>
          <div style={{ marginLeft: "auto" }}>
            <button
              type="button"
              className="st-detail-close-btn"
              onClick={onClose}
              aria-label="Close builder"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Modal Content */}
        <div className={`st-modal-body ${activeTab === "indicator" ? "is-indicator" : ""}`}>
          {activeTab === "indicator" ? (
            <IndicatorEditorPanel
              key={editingIndicator?.id || "new-indicator"}
              initial={editingIndicator}
              onCancel={onClose}
              onSaved={(indicator) => {
                onApplyIndicator?.(indicator, false);
                onClose();
              }}
              onSavedAndApply={(indicator) => {
                onApplyIndicator?.(indicator, true);
                onClose();
              }}
            />
          ) : activeTab === "pine" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Toolbar & Version Status */}
              <div className="st-pine-toolbar">
                <div className="st-config-field" style={{ marginBottom: 0 }}>
                  <label style={{ fontSize: "0.8125rem", color: "#f1f5f9", fontWeight: 600 }}>Pine Code</label>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span
                    className={`st-pine-version-badge ${detectedVersion.isSupported ? "is-valid" : "is-warning"}`}
                    data-testid="pine-version-badge"
                  >
                    {detectedVersion.text}
                  </span>
                  <button
                    type="button"
                    className="st-btn-dark"
                    style={{ padding: "3px 8px", fontSize: "0.72rem" }}
                    onClick={() => setShowDebugTrace(!showDebugTrace)}
                    data-testid="btn-toggle-pine-debug"
                    title="Toggle AST Expression Roles Debugger"
                  >
                    {showDebugTrace ? "Hide Debug" : "Debug Trace"}
                  </button>
                  <button
                    type="button"
                    className="st-btn-dark"
                    style={{ padding: "3px 8px", fontSize: "0.72rem" }}
                    onClick={() => setPineCode(DEFAULT_PINE_TEMPLATE)}
                    title="Load starter template"
                  >
                    Template
                  </button>
                </div>
              </div>

              {/* Data Loss Confirmation Dialog */}
              {confirmReplaceOpen && (
                <div className="st-pine-confirm-overlay" data-testid="pine-confirm-replace" style={{
                  background: "#0c1527",
                  border: "1px solid #eab308",
                  borderRadius: 6,
                  padding: 12,
                  marginBottom: 6
                }}>
                  <div style={{ fontWeight: 600, color: "#fef08a", fontSize: "0.875rem", marginBottom: 4 }}>
                    ⚠ Replace Existing Filters?
                  </div>
                  <p style={{ fontSize: "0.8rem", color: "#cbd5e1", margin: "4px 0 10px 0" }}>
                    Pine analysis detected <strong>{pendingResult?.filters.length}</strong> entry filter(s).
                    Your current Strategy Builder contains <strong>{filters.length}</strong> configured filter(s).
                    Replace current filters with detected Pine filters?
                  </p>
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                    <button
                      type="button"
                      className="st-btn-dark"
                      style={{ padding: "4px 10px", fontSize: "0.75rem" }}
                      onClick={() => setConfirmReplaceOpen(false)}
                      data-testid="btn-cancel-replace-filters"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="st-btn-primary"
                      style={{ padding: "4px 10px", fontSize: "0.75rem", background: "#ca8a04", borderColor: "#eab308" }}
                      onClick={() => applyParsedResult(pendingResult)}
                      data-testid="btn-confirm-replace-filters"
                    >
                      Replace Filters
                    </button>
                  </div>
                </div>
              )}

              {/* Debug Trace Viewer */}
              {showDebugTrace && (
                <div className="st-pine-debug-table" data-testid="pine-debug-trace" style={{ maxHeight: 160, overflowY: "auto", background: "#060d1d", border: "1px solid #1e293b", borderRadius: 4, padding: 6, fontSize: "0.72rem" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", color: "#94a3b8" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid #1e293b", color: "#f1f5f9", textAlign: "left" }}>
                        <th style={{ padding: "3px 6px" }}>Expression</th>
                        <th style={{ padding: "3px 6px" }}>Semantic Role</th>
                        <th style={{ padding: "3px 6px" }}>Action / Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {parsePineScript(pineCode, { debug: true }).debugTrace?.map((d, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid #0f172a" }}>
                          <td style={{ padding: "3px 6px", fontFamily: "monospace", color: "#cbd5e1" }}>{d.expression}</td>
                          <td style={{ padding: "3px 6px" }}>
                            <span className="st-tag-pine" style={{ fontSize: "0.65rem" }}>{d.role}</span>
                          </td>
                          <td style={{ padding: "3px 6px", color: "#38bdf8" }}>{d.builderField}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Code Editor */}
              <PineCodeEditor
                value={pineCode}
                onChange={(val) => {
                  setPineCode(val);
                  setPineError(null);
                }}
                placeholder="//@version=6&#10;strategy(&quot;My Strategy&quot;, overlay=true)&#10;..."
              />

              {/* Error Display */}
              {pineError && (
                <div className="st-pine-error-banner" data-testid="pine-error-banner" style={{ whiteSpace: "pre-wrap" }}>
                  {pineError}
                </div>
              )}

              {/* Warnings Display */}
              {pineWarnings.length > 0 && (
                <div className="st-pine-summary-warning">
                  {pineWarnings.map((w, idx) => (
                    <div key={idx}>⚠ {w}</div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Pine Import Summary Banner */}
              {pineImportSummary && (
                <div className="st-pine-summary-banner" data-testid="pine-import-summary">
                  <div className="st-pine-summary-title">
                    <span>{pineImportSummary.title}</span>
                    <span className="st-tag-pine" style={{ fontSize: "0.7rem" }}>
                      {pineImportSummary.filterCount} entry filters detected
                    </span>
                  </div>
                  <div className="st-pine-summary-details" style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 4 }}>
                    <div>Strategy: <strong>{name}</strong> · Position: <strong>{side === "LONG" ? "LONG ONLY" : "SHORT ONLY"}</strong> · Logic: <strong>{logic === "ALL" ? "ALL conditions must be true" : "ANY condition can be true"}</strong></div>
                    {pineImportSummary.benchmarkText && (
                      <div style={{ color: "#38bdf8", fontSize: "0.75rem" }}>✓ Market Gate: <strong>{pineImportSummary.benchmarkText}</strong></div>
                    )}
                    {pineImportSummary.riskText && (
                      <div style={{ color: "#a78bfa", fontSize: "0.75rem" }}>✓ Risk Management: <strong>{pineImportSummary.riskText}</strong></div>
                    )}
                    {pineImportSummary.exitText && (
                      <div style={{ color: "#f472b6", fontSize: "0.75rem" }}>✓ {pineImportSummary.exitText}</div>
                    )}
                    {pineImportSummary.rankingText && (
                      <div style={{ color: "#34d399", fontSize: "0.75rem" }}>✓ {pineImportSummary.rankingText}</div>
                    )}
                  </div>
                  {pineWarnings.length > 0 && (
                    <div className="st-pine-summary-warning">
                      {pineWarnings.map((w, idx) => (
                        <div key={idx}>⚠ {w}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Strategy Name & Position Side */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="st-config-field">
                  <label>Strategy Name</label>
                  <div className="st-config-box">
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Momentum Strategy"
                      data-testid="input-strategy-name"
                    />
                  </div>
                </div>

                <div className="st-config-field">
                  <label>Position Side</label>
                  <div className="st-config-box">
                    <select
                      value={side}
                      onChange={(e) => setSide(e.target.value as "LONG" | "SHORT")}
                      data-testid="select-position-side"
                    >
                      <option value="LONG">LONG ONLY</option>
                      <option value="SHORT">SHORT ONLY</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Description */}
              <div className="st-config-field">
                <label>Description</label>
                <div className="st-config-box" style={{ height: 38 }}>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Brief summary of strategy rationale..."
                    data-testid="input-strategy-desc"
                  />
                </div>
              </div>

              {/* Logic Selector */}
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 4 }}>
                <span style={{ fontSize: "0.8125rem", color: "#cbd5e1", fontWeight: 600 }}>Execution Logic:</span>
                <button
                  type="button"
                  className={logic === "ALL" ? "st-btn-primary" : "st-btn-dark"}
                  onClick={() => setLogic("ALL")}
                  style={{ padding: "4px 12px", fontSize: "0.75rem" }}
                  data-testid="btn-logic-all"
                >
                  ALL conditions must be true
                </button>
                <button
                  type="button"
                  className={logic === "ANY" ? "st-btn-primary" : "st-btn-dark"}
                  onClick={() => setLogic("ANY")}
                  style={{ padding: "4px 12px", fontSize: "0.75rem" }}
                  data-testid="btn-logic-any"
                >
                  ANY condition can be true
                </button>
              </div>

              {/* Filter Rules List */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.8125rem", color: "#f1f5f9", fontWeight: 600 }}>
                    Filter Conditions ({filters.length})
                  </span>
                  <button
                    type="button"
                    className="st-btn-dark"
                    style={{ padding: "3px 8px", fontSize: "0.72rem" }}
                    onClick={handleAddFilter}
                    data-testid="btn-add-filter-rule"
                  >
                    + Add Condition
                  </button>
                </div>

                {filters.map((filter, index) => (
                  <div
                    key={filter.id || index}
                    style={{
                      background: "#050a16",
                      border: "1px solid #1e293b",
                      borderRadius: 6,
                      padding: "8px 10px",
                      display: "grid",
                      gridTemplateColumns: "1.2fr 1fr 1.4fr auto",
                      gap: 8,
                      alignItems: "center",
                    }}
                    data-testid={`filter-row-${index}`}
                  >
                    {/* Left Field */}
                    <div style={{ display: "flex", gap: 4 }}>
                      <select
                        value={filter.field}
                        onChange={(e) => handleFilterChange(index, "field", e.target.value)}
                        className="st-select-small"
                        style={{ flex: 1 }}
                      >
                        {FIELD_OPTIONS.map((f) => (
                          <option key={f.value} value={f.value}>
                            {f.label}
                          </option>
                        ))}
                        {!FIELD_OPTIONS.some((f) => f.value === filter.field) && filter.field && (
                          <option value={filter.field}>{filter.field}</option>
                        )}
                      </select>
                      {["SMA", "EMA", "WMA", "RSI", "HIGH", "LOW", "AVG_VOLUME", "REL_VOLUME", "VWAP", "ATR", "HV", "BB_UPPER", "BB_MIDDLE", "BB_LOWER", "BB_WIDTH"].includes(filter.field) && (
                        <input
                          type="number"
                          value={filter.period || (filter.field === "RSI" || filter.field === "ATR" ? "14" : filter.field === "HIGH" || filter.field === "LOW" ? "252" : ["AVG_VOLUME", "REL_VOLUME", "VWAP", "HV", "BB_UPPER", "BB_MIDDLE", "BB_LOWER", "BB_WIDTH"].includes(filter.field) ? "20" : "50")}
                          onChange={(e) => handleFilterChange(index, "period", e.target.value)}
                          placeholder="Period"
                          style={{
                            width: 44,
                            background: "#091022",
                            border: "1px solid #1e293b",
                            borderRadius: 4,
                            color: "#f1f5f9",
                            fontSize: "0.75rem",
                            padding: "2px 4px",
                          }}
                        />
                      )}
                    </div>

                    {/* Operator */}
                    <select
                      value={filter.operator}
                      onChange={(e) => handleFilterChange(index, "operator", e.target.value)}
                      className="st-select-small"
                    >
                      {OPERATORS.map((op) => (
                        <option key={op.value} value={op.value}>
                          {op.label}
                        </option>
                      ))}
                    </select>

                    {/* Right Operand */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {filter.operator === "between" || filter.operator === "outside" ? (
                        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                          <input
                            type="number"
                            placeholder="Low"
                            value={filter.low}
                            onChange={(e) => handleFilterChange(index, "low", e.target.value)}
                            style={{
                              width: 50,
                              background: "#091022",
                              border: "1px solid #1e293b",
                              borderRadius: 4,
                              color: "#f1f5f9",
                              fontSize: "0.75rem",
                              padding: "4px",
                            }}
                          />
                          <span style={{ color: "#64748b", fontSize: "0.7rem" }}>to</span>
                          <input
                            type="number"
                            placeholder="High"
                            value={filter.high}
                            onChange={(e) => handleFilterChange(index, "high", e.target.value)}
                            style={{
                              width: 50,
                              background: "#091022",
                              border: "1px solid #1e293b",
                              borderRadius: 4,
                              color: "#f1f5f9",
                              fontSize: "0.75rem",
                              padding: "4px",
                            }}
                          />
                        </div>
                      ) : filter.rightKind === "literal" ||
                        ((filter.operator === "<" || filter.operator === ">") && filter.literal && !filter.indicator) ? (
                        <div style={{ display: "flex", gap: 4, width: "100%" }}>
                          <input
                            type="text"
                            placeholder="e.g. 55"
                            value={filter.literal}
                            onChange={(e) => {
                              handleFilterChange(index, { literal: e.target.value, rightKind: "literal" });
                            }}
                            style={{
                              flex: 1,
                              background: "#091022",
                              border: "1px solid #1e293b",
                              borderRadius: 4,
                              color: "#f1f5f9",
                              fontSize: "0.75rem",
                              padding: "4px 6px",
                            }}
                            data-testid={`filter-literal-${index}`}
                          />
                          <button
                            type="button"
                            onClick={() => handleFilterChange(index, "rightKind", "indicator")}
                            style={{
                              background: "transparent",
                              border: "none",
                              color: "#38bdf8",
                              fontSize: "0.68rem",
                              cursor: "pointer",
                            }}
                          >
                            Use Ind.
                          </button>
                        </div>
                      ) : (
                        <div style={{ display: "flex", gap: 4, width: "100%", alignItems: "center" }}>
                          <select
                            value={filter.indicator || "SMA"}
                            onChange={(e) => handleFilterChange(index, "indicator", e.target.value)}
                            className="st-select-small"
                            style={{ flex: 1 }}
                          >
                            <option value="SMA">SMA</option>
                            <option value="EMA">EMA</option>
                            <option value="WMA">WMA</option>
                            <option value="AVG_VOLUME">Avg Volume</option>
                            <option value="REL_VOLUME">Relative Volume</option>
                            <option value="HIGH">Prior High / 52W High</option>
                            <option value="LOW">Prior Low / 52W Low</option>
                            <option value="RSI">RSI</option>
                            <option value="CLOSE">Close</option>
                            <option value="BB_UPPER">Upper Bollinger Band</option>
                            <option value="BB_MIDDLE">Middle Bollinger Band</option>
                            <option value="BB_LOWER">Lower Bollinger Band</option>
                            <option value="VWAP">VWAP</option>
                            <option value="ATR">ATR</option>
                            {!["SMA", "EMA", "WMA", "AVG_VOLUME", "REL_VOLUME", "HIGH", "LOW", "RSI", "CLOSE", "BB_UPPER", "BB_MIDDLE", "BB_LOWER", "VWAP", "ATR"].includes(filter.indicator || "") && filter.indicator && (
                              <option value={filter.indicator}>{filter.indicator}</option>
                            )}
                          </select>
                          <input
                            type="number"
                            placeholder="Period"
                            value={filter.indicatorPeriod || (filter.indicator === "HIGH" || filter.indicator === "LOW" ? "252" : "50")}
                            onChange={(e) => handleFilterChange(index, "indicatorPeriod", e.target.value)}
                            style={{
                              width: 44,
                              background: "#091022",
                              border: "1px solid #1e293b",
                              borderRadius: 4,
                              color: "#f1f5f9",
                              fontSize: "0.75rem",
                              padding: "4px",
                            }}
                          />
                          <button
                            type="button"
                            onClick={() => handleFilterChange(index, "rightKind", "literal")}
                            style={{
                              background: "transparent",
                              border: "none",
                              color: "#38bdf8",
                              fontSize: "0.68rem",
                              cursor: "pointer",
                            }}
                          >
                            Value
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Remove button */}
                    <button
                      type="button"
                      onClick={() => handleRemoveFilter(index)}
                      disabled={filters.length <= 1}
                      style={{
                        background: "transparent",
                        border: "none",
                        color: filters.length <= 1 ? "#334155" : "#f87171",
                        cursor: filters.length <= 1 ? "not-allowed" : "pointer",
                        fontSize: "0.9rem",
                        padding: "2px 6px",
                      }}
                      title="Remove condition"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        {activeTab !== "indicator" && (
        <div className="st-modal-footer">
          <button type="button" className="st-btn-dark" onClick={onClose}>
            Cancel
          </button>
          {activeTab === "pine" ? (
            <button
              type="button"
              className="st-btn-primary"
              onClick={handleObserveFilters}
              data-testid="btn-observe-pine-filters"
            >
              Observe Filters
            </button>
          ) : (
            <button
              type="button"
              className="st-btn-primary"
              onClick={handleSave}
              data-testid="btn-apply-strategy-builder"
            >
              Save & Apply
            </button>
          )}
        </div>
        )}
      </div>
    </div>
  );
};
