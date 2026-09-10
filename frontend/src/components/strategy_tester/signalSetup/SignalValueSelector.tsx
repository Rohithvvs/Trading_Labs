import React from "react";
import type { AbsorbedOutput } from "../../../utils/indicatorAbsorb";
import { isRangeCondition, valueSourceOptions, type SignalSetupDraft } from "../../../utils/signalSetup";

type SignalValueSelectorProps = {
  draft: SignalSetupDraft;
  columns: AbsorbedOutput[];
  currentField: string;
  onChange: (patch: Partial<SignalSetupDraft>) => void;
};

export const SignalValueSelector: React.FC<SignalValueSelectorProps> = ({
  draft,
  columns,
  currentField,
  onChange,
}) => {
  const sources = valueSourceOptions(columns, currentField);
  const usingValue = !draft.source || draft.source === "value";
  const range = isRangeCondition(draft.condition);

  return (
    <div className="sig-value-row">
      <label className="sig-setup-control">
        <span className="sr-only">Value source</span>
        <select
          aria-label="Value source"
          value={draft.source || "value"}
          onChange={(event) => onChange({ source: event.target.value })}
          data-testid="signal-value-source"
        >
          {sources.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      {usingValue && range ? (
        <>
          <input
            aria-label="Filter low"
            className="sig-setup-input"
            value={draft.low === "" ? "" : String(draft.low)}
            onChange={(event) => onChange({ low: event.target.value === "" ? "" : Number(event.target.value) })}
            data-testid="signal-value-low"
          />
          <input
            aria-label="Filter high"
            className="sig-setup-input"
            value={draft.high === "" ? "" : String(draft.high)}
            onChange={(event) => onChange({ high: event.target.value === "" ? "" : Number(event.target.value) })}
            data-testid="signal-value-high"
          />
        </>
      ) : usingValue ? (
        <input
          aria-label="Filter value"
          className="sig-setup-input"
          value={draft.value === "" ? "" : String(draft.value)}
          onChange={(event) => onChange({ value: event.target.value === "" ? "" : Number(event.target.value) })}
          data-testid="signal-value-input"
        />
      ) : (
        <div className="sig-setup-input is-readonly" data-testid="signal-value-ref">
          {draft.source}
        </div>
      )}
    </div>
  );
};
