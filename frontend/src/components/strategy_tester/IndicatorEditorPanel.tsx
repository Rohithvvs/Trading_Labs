import React, { useEffect, useMemo, useState } from "react";
import {
  createIndicator,
  fetchIndicators,
  fetchIndicatorTemplates,
  seedLabIndicators,
  updateIndicator,
  validateIndicatorSource,
  type IndicatorValidation,
  type LabIndicatorTemplate,
  type SavedIndicator,
} from "../../api_indicator_scanner";
import { uniqueIndicatorsByIdAndName } from "../../utils/indicatorScannerState";
import { DEFAULT_INDICATOR_TEMPLATE, INDICATOR_SYNTAX_HELP, BREAKOUT_SCAN_DESCRIPTION, BREAKOUT_SCAN_TITLE } from "../../utils/indicatorTemplate";
import { absorbFromParsedDefinition, absorbEntryConditions, describeAbsorbedFilter, insertScreenerSignalPlot } from "../../utils/indicatorAbsorb";
import { parsePineScript, type ModalBuilderFilter } from "../../utils/pineParser";
import { entryConditionsToFilters } from "../../utils/pineGenerator";
import { PineCodeEditor } from "./PineCodeEditor";

export type IndicatorEditorPanelProps = {
  initial?: SavedIndicator | null;
  onCancel: () => void;
  onSaved: (indicator: SavedIndicator) => void;
  onSavedAndApply: (indicator: SavedIndicator) => void;
  onObserveToBuilder?: (data: {
    name: string;
    description: string;
    source: string;
    filters: ModalBuilderFilter[];
    logic: "ALL" | "ANY";
    side: "LONG" | "SHORT";
    warnings?: string[];
    debugTrace?: any[];
  }) => void;
};

export const IndicatorEditorPanel: React.FC<IndicatorEditorPanelProps> = ({
  initial,
  onCancel,
  onSaved,
  onSavedAndApply,
  onObserveToBuilder,
}) => {
  const [name, setName] = useState(initial?.name || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [timeframe, setTimeframe] = useState(initial?.timeframe || "1D");
  const [source, setSource] = useState(initial?.source_code || "");
  const [validatedSource, setValidatedSource] = useState<string | null>(null);
  const [validatedTimeframe, setValidatedTimeframe] = useState<string | null>(null);
  const [validation, setValidation] = useState<IndicatorValidation | null>(null);
  const [busy, setBusy] = useState<"observe" | "save" | "apply" | "seed" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<LabIndicatorTemplate[]>([]);
  const [templateId, setTemplateId] = useState<string>("");

  const isEditing = Boolean(initial?.id);
  const isValid = validation?.ok === true && validatedSource === source && validatedTimeframe === timeframe;
  const canAttemptSave = name.trim().length > 0 && source.trim().length > 0 && !busy && timeframe === "1D";

  useEffect(() => {
    let cancelled = false;
    fetchIndicatorTemplates()
      .then((rows) => {
        if (!cancelled) setTemplates(rows);
      })
      .catch(() => {
        if (!cancelled) setTemplates([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const applyTemplate = (strategyId: string) => {
    setTemplateId(strategyId);
    if (!strategyId) {
      if (!isEditing) {
        setName("");
        setDescription("");
        setSource("");
      }
      setValidation(null);
      setValidatedSource(null);
      setValidatedTimeframe(null);
      setError(null);
      return;
    }
    const match = templates.find((row) => row.strategy_id === strategyId);
    if (!match?.source_code) return;
    setName((match.name || "").slice(0, 120));
    setDescription((match.description || "").slice(0, 500));
    setSource(match.source_code);
    setValidation(null);
    setValidatedSource(null);
    setValidatedTimeframe(null);
    setError(null);
  };

  const handleSaveAllLab = async () => {
    setBusy("seed");
    setError(null);
    try {
      await seedLabIndicators();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save the research-lab strategies.");
    } finally {
      setBusy(null);
    }
  };

  const runValidation = async (): Promise<IndicatorValidation | null> => {
    const result = await validateIndicatorSource(source, timeframe);
    setValidation(result);
    setValidatedSource(result.ok ? source : null);
    setValidatedTimeframe(result.ok ? timeframe : null);
    return result;
  };

  const absorbed = useMemo(() => {
    if (!isValid || !validation) return { columns: [], filters: [], entryConditions: [] };
    return absorbFromParsedDefinition(validation.parsed_definition || { outputs: validation.outputs });
  }, [isValid, validation]);

  const handleObserve = async () => {
    setBusy("observe");
    setError(null);
    try {
      if (!source.trim()) {
        setError("Please enter Pine Script code before observing.");
        return;
      }
      const result = await runValidation();
      if (result && !result.ok && result.errors && result.errors.length > 0) {
        setError(`Unable to observe Pine code: ${result.errors.map((e) => `Line ${e.line}: ${e.message}`).join("; ")}`);
        return;
      }

      if (onObserveToBuilder) {
        let parsedFilters: ModalBuilderFilter[] = [];
        let parsedLogic: "ALL" | "ANY" = "ALL";
        let parsedSide: "LONG" | "SHORT" = "LONG";
        let warnings: string[] = [];
        let debugTrace: any[] = [];

        try {
          const res = parsePineScript(source, { debug: true });
          if (res.filters && res.filters.length > 0) {
            parsedFilters = res.filters;
            parsedLogic = res.logic || "ALL";
            parsedSide = res.positionSide || "LONG";
            warnings = res.warnings || [];
            debugTrace = res.debugTrace || [];
          }
        } catch {
          // fallback
        }

        if (parsedFilters.length === 0 && result) {
          const conditions = result.entry_conditions || (result.parsed_definition as any)?.entry_conditions;
          if (conditions && Array.isArray(conditions) && conditions.length > 0) {
            parsedFilters = entryConditionsToFilters(conditions);
          } else {
            const absorbedConditions = absorbEntryConditions(result.parsed_definition);
            if (absorbedConditions.length > 0) {
              parsedFilters = entryConditionsToFilters(absorbedConditions);
            }
          }
        }

        if (parsedFilters.length === 0) {
          setError("No supported filter conditions could be extracted from this Pine Script. Please ensure your script defines entry conditions or signal rules.");
          return;
        }

        const effectiveName = name.trim()
          ? name.trim()
          : (result?.title?.trim() || "Custom Indicator");

        const effectiveDesc = description.trim()
          ? description.trim()
          : (result?.description?.trim() || "");

        onObserveToBuilder({
          name: effectiveName,
          description: effectiveDesc,
          source,
          filters: parsedFilters,
          logic: parsedLogic,
          side: parsedSide,
          warnings,
          debugTrace,
        });
        return;
      }

      if (result?.ok && result.title && !name.trim()) {
        setName(result.title.slice(0, 120));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to observe Pine code.");
      setValidation(null);
      setValidatedSource(null);
      setValidatedTimeframe(null);
    } finally {
      setBusy(null);
    }
  };

  const persist = async (): Promise<SavedIndicator> => {
    const finalName = name.trim() || validation?.title?.trim() || BREAKOUT_SCAN_TITLE;
    const payload = {
      name: finalName.slice(0, 120),
      description: (description.trim() || validation?.description?.trim() || "").slice(0, 500),
      source_code: source,
      timeframe,
    };
    if (initial?.id) {
      return updateIndicator(initial.id, payload);
    }
    try {
      const existing = uniqueIndicatorsByIdAndName(await fetchIndicators());
      const match = existing.find((row) => row.name.trim().toLowerCase() === payload.name.toLowerCase());
      if (match?.id) {
        return updateIndicator(match.id, payload);
      }
    } catch {
      /* create a new record if the library cannot be read */
    }
    return createIndicator(payload);
  };

  const handleSave = async (apply: boolean) => {
    if (!canAttemptSave) return;
    setBusy(apply ? "apply" : "save");
    setError(null);
    try {
      let ok = isValid;
      if (!ok) {
        const result = await runValidation();
        ok = result?.ok === true;
        if (!ok) {
          setError("Fix validation errors before saving.");
          return;
        }
      }
      const saved = await persist();
      if (apply) onSavedAndApply(saved);
      else onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save indicator.");
    } finally {
      setBusy(null);
    }
  };

  const statusLabel = useMemo(() => {
    if (!validation) return "Not validated";
    return validation.ok ? "Valid" : "Invalid";
  }, [validation]);

  return (
    <div className="ind-editor" data-testid="indicator-editor-panel">
      <div className="ind-editor-scroll">
      <div>
        <h2 className="ind-editor-title">{isEditing ? "Edit Indicator" : "Create Indicator"}</h2>
        <p className="ind-editor-helper">
          Paste indicator Pine code, click Observe to absorb columns and screen rules, then Apply and Run Scan on the
          755-stock universe.
        </p>
        <p className="ind-editor-compat">
          TradingLabs supports a secure Pine Script v6-compatible subset for screening. Unsupported code will show
          validation errors.
        </p>
      </div>

      <label className="st-config-field" data-testid="lab-template-picker">
        <span>Research-lab strategy (21)</span>
        <select
          value={templateId}
          onChange={(e) => applyTemplate(e.target.value)}
          data-testid="select-lab-template"
        >
          <option value="">Custom / Blank</option>
          {templates.map((row) => (
            <option key={row.strategy_id} value={row.strategy_id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>

      <div className="ind-editor-grid">
        <label className="st-config-field">
          <span>Indicator Name</span>
          <input
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            placeholder="Enter indicator name..."
            data-testid="input-indicator-name"
          />
        </label>
        <label className="st-config-field">
          <span>Timeframe</span>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            data-testid="select-indicator-timeframe"
          >
            <option value="1D">1D</option>
            <option value="1W">1W (coming later)</option>
            <option value="1M">1M (coming later)</option>
          </select>
        </label>
      </div>
      {timeframe !== "1D" && (
        <div className="st-pine-summary-warning" data-testid="indicator-timeframe-warning">
          Weekly and monthly timeframes are not supported yet. Daily (1D) data is available.
        </div>
      )}
      <label className="st-config-field">
        <span>Description</span>
        <textarea
          value={description}
          maxLength={500}
          rows={2}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Brief description of indicator..."
          data-testid="input-indicator-description"
        />
      </label>

      <PineCodeEditor
        value={source}
        onChange={(val) => setSource(val)}
        placeholder="// Enter Pine Script indicator code here..."
      />

      <details className="ind-syntax-help">
        <summary>Supported syntax</summary>
        <ul>
          {INDICATOR_SYNTAX_HELP.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>

      {error && (
        <div className="st-pine-error-banner" data-testid="indicator-error-banner">
          {error}
        </div>
      )}

      {validation && (
        <div className="ind-validation" data-testid="indicator-validation-panel">
          <div className={`ind-validation-status ${validation.ok ? "is-valid" : "is-invalid"}`}>
            Status: {statusLabel}
          </div>
          {validation.errors.map((issue, i) => (
            <div key={`e-${i}`} className="st-pine-error-banner">
              Line {issue.line}: {issue.message}
            </div>
          ))}
          {validation.warnings.map((issue, i) => (
            <div key={`w-${i}`} className="st-pine-summary-warning">
              {issue.message}
              {issue.code === "MISSING_SCREENER_SIGNAL_PLOT" && (
                <div>
                  <button
                    type="button"
                    className="st-btn-dark"
                    data-testid="btn-insert-screener-signal-plot"
                    onClick={() => {
                      setSource((prev) => insertScreenerSignalPlot(prev));
                      setValidation(null);
                      setValidatedSource(null);
                    }}
                  >
                    Insert Signal = 1 plot
                  </button>
                  {" "}
                  Then Observe again and paste the same script into TradingView Pine Screener. Filter Signal = 1 on both platforms.
                </div>
              )}
            </div>
          ))}
          {validation.ok && (
            <div className="ind-observe-summary" data-testid="indicator-observe-summary">
              <h3>Absorbed from Pine</h3>
              <p>These columns and rules will be used on the 755-stock universe when you Run Scan.</p>
              <div>
                <strong>Indicator columns</strong>
                <div className="ind-chip-row">
                  {absorbed.columns.map((col) => (
                    <span key={col.name} className="ind-col-chip">
                      {col.name}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <strong>Strategy conditions</strong>
                {absorbed.entryConditions.length ? (
                  <ul data-testid="indicator-absorbed-filters">
                    {absorbed.entryConditions.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                ) : absorbed.filters.length ? (
                  <ul data-testid="indicator-absorbed-filters">
                    {absorbed.filters.map((filter) => (
                      <li key={describeAbsorbedFilter(filter)}>{describeAbsorbedFilter(filter)}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No automatic screen rule. Run Scan will return every symbol with column values.</p>
                )}
              </div>
              <div className="ind-validation-meta">
                <div>
                  <strong>Inputs</strong>
                  <ul>
                    {validation.inputs.map((inp) => (
                      <li key={inp.name}>
                        {inp.title} = {String(inp.default)}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <strong>Required bars:</strong> {validation.required_bars}
                  <div>
                    <strong>Benchmark:</strong> {validation.required_symbols.join(", ") || "None"}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      </div>

      <div className="ind-editor-actions">
        <button type="button" className="st-btn-dark" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          className="st-btn-dark"
          onClick={handleSaveAllLab}
          disabled={!!busy}
          data-testid="btn-save-all-lab-strategies"
        >
          {busy === "seed" ? "Saving 21…" : "Save all 21 strategies"}
        </button>
        <button
          type="button"
          className="st-btn-dark"
          onClick={handleObserve}
          disabled={!!busy}
          data-testid="btn-validate-indicator"
        >
          {busy === "observe" ? "Observing…" : "Observe"}
        </button>
        <button
          type="button"
          className="st-btn-dark"
          onClick={() => handleSave(false)}
          disabled={!canAttemptSave}
          data-testid="btn-save-indicator"
        >
          {busy === "save" ? "Saving…" : "Save Indicator"}
        </button>
        <button
          type="button"
          className="st-btn-primary"
          onClick={() => handleSave(true)}
          disabled={!canAttemptSave}
          data-testid="btn-save-apply-indicator"
        >
          {busy === "apply" ? "Applying…" : "Apply"}
        </button>
      </div>
      <p className="ind-disclaimer">For research and paper-trading only. Not investment advice.</p>
    </div>
  );
};
