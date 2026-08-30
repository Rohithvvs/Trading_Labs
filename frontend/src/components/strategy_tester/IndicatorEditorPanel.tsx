import React, { useMemo, useState } from "react";
import {
  createIndicator,
  fetchIndicators,
  updateIndicator,
  validateIndicatorSource,
  type IndicatorValidation,
  type SavedIndicator,
} from "../../api_indicator_scanner";
import { uniqueIndicatorsByIdAndName } from "../../utils/indicatorScannerState";
import { DEFAULT_INDICATOR_TEMPLATE, INDICATOR_SYNTAX_HELP, BREAKOUT_SCAN_DESCRIPTION, BREAKOUT_SCAN_TITLE } from "../../utils/indicatorTemplate";
import { absorbOutputs, absorbScreenFilters, describeAbsorbedFilter } from "../../utils/indicatorAbsorb";
import { PineCodeEditor } from "./PineCodeEditor";

export type IndicatorEditorPanelProps = {
  initial?: SavedIndicator | null;
  onCancel: () => void;
  onSaved: (indicator: SavedIndicator) => void;
  onSavedAndApply: (indicator: SavedIndicator) => void;
};

export const IndicatorEditorPanel: React.FC<IndicatorEditorPanelProps> = ({
  initial,
  onCancel,
  onSaved,
  onSavedAndApply,
}) => {
  const [name, setName] = useState(initial?.name || BREAKOUT_SCAN_TITLE);
  const [description, setDescription] = useState(initial?.description || BREAKOUT_SCAN_DESCRIPTION);
  const [timeframe, setTimeframe] = useState(initial?.timeframe || "1D");
  const [source, setSource] = useState(initial?.source_code || DEFAULT_INDICATOR_TEMPLATE);
  const [validatedSource, setValidatedSource] = useState<string | null>(null);
  const [validatedTimeframe, setValidatedTimeframe] = useState<string | null>(null);
  const [validation, setValidation] = useState<IndicatorValidation | null>(null);
  const [busy, setBusy] = useState<"observe" | "save" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isEditing = Boolean(initial?.id);
  const isValid = validation?.ok === true && validatedSource === source && validatedTimeframe === timeframe;
  const canAttemptSave = name.trim().length > 0 && !busy && timeframe === "1D";

  const runValidation = async (): Promise<IndicatorValidation | null> => {
    const result = await validateIndicatorSource(source, timeframe);
    setValidation(result);
    setValidatedSource(result.ok ? source : null);
    setValidatedTimeframe(result.ok ? timeframe : null);
    return result;
  };

  const absorbed = useMemo(() => {
    if (!isValid || !validation) return { columns: [], filters: [] };
    const columns = absorbOutputs(validation.outputs);
    return { columns, filters: absorbScreenFilters(columns) };
  }, [isValid, validation]);

  const handleObserve = async () => {
    setBusy("observe");
    setError(null);
    try {
      const result = await runValidation();
      if (result?.ok && result.title && name === BREAKOUT_SCAN_TITLE) {
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
    const payload = {
      name: name.trim().slice(0, 120),
      description: description.trim().slice(0, 500),
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

      <div className="ind-editor-grid">
        <label className="st-config-field">
          <span>Indicator Name</span>
          <input
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
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
          data-testid="input-indicator-description"
        />
      </label>

      <PineCodeEditor value={source} onChange={(val) => setSource(val)} />

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
                <strong>Screen rules</strong>
                {absorbed.filters.length ? (
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
