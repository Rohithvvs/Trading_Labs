import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { IndicatorFilter, SignalCondition } from "../../../api_indicator_scanner";
import type { AbsorbedOutput } from "../../../utils/indicatorAbsorb";
import {
  SIGNAL_CONDITIONS,
  defaultSignalDraft,
  draftIsComplete,
  draftToFilter,
  type SignalSetupDraft,
} from "../../../utils/signalSetup";
import { ConditionIcon } from "./ConditionIcons";
import { SignalConditionDropdown } from "./SignalConditionDropdown";
import { SignalValueSelector } from "./SignalValueSelector";
import { useAnchoredPopover } from "./useAnchoredPopover";

type SignalManualSetupProps = {
  column: AbsorbedOutput;
  columns: AbsorbedOutput[];
  existing?: IndicatorFilter | null;
  anchor: HTMLElement | null;
  onApply: (filter: IndicatorFilter) => void;
  onCancel: () => void;
};

export const SignalManualSetup: React.FC<SignalManualSetupProps> = ({
  column,
  columns,
  existing,
  anchor,
  onApply,
  onCancel,
}) => {
  const [draft, setDraft] = useState<SignalSetupDraft>(() => defaultSignalDraft(column, existing));
  const [conditionsOpen, setConditionsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const pos = useAnchoredPopover(true, anchor, 360);
  const selectedLabel = useMemo(
    () => SIGNAL_CONDITIONS.find((item) => item.id === draft.condition)?.label || "Above",
    [draft.condition],
  );

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      const el = target instanceof Element ? target : null;
      if (panelRef.current?.contains(target)) return;
      if (anchor?.contains(target)) return;
      if (el?.closest("[data-testid='signal-condition-dropdown']")) return;
      onCancel();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [anchor, onCancel]);

  if (!pos) return null;

  const patch = (next: Partial<SignalSetupDraft>) => setDraft((prev) => ({ ...prev, ...next }));
  const canApply = draftIsComplete(draft);

  return createPortal(
    <div
      ref={panelRef}
      className="sig-manual-setup"
      role="dialog"
      aria-label="Manual setup"
      data-testid="signal-manual-setup"
      style={{ top: pos.top, left: pos.left, width: pos.width }}
    >
      <div className="sig-manual-setup-head">
        <span>Manual setup</span>
        <button type="button" className="sig-setup-close" aria-label="Close" onClick={onCancel}>
          ×
        </button>
      </div>
      <div className="sig-manual-setup-title" data-testid="signal-manual-setup-name">
        {column.name.toUpperCase()}
      </div>
      <div className="sig-setup-fields">
        <div className="sig-cond-anchor">
          <button
            ref={triggerRef}
            type="button"
            className={`sig-setup-control sig-cond-trigger${conditionsOpen ? " is-open" : ""}`}
            aria-haspopup="listbox"
            aria-expanded={conditionsOpen}
            data-testid="signal-condition-trigger"
            onClick={() => setConditionsOpen((open) => !open)}
          >
            <ConditionIcon condition={draft.condition} />
            <span>{selectedLabel}</span>
            <span className="sig-caret" aria-hidden="true">
              ▾
            </span>
          </button>
          <SignalConditionDropdown
            open={conditionsOpen}
            value={draft.condition}
            anchor={triggerRef.current}
            onSelect={(condition: SignalCondition) => patch({ condition })}
            onClose={() => setConditionsOpen(false)}
          />
        </div>
        <SignalValueSelector draft={draft} columns={columns} currentField={column.name} onChange={patch} />
      </div>
      <div className="sig-manual-setup-actions">
        <button type="button" className="sig-btn-ghost" onClick={onCancel} data-testid="signal-setup-cancel">
          Cancel
        </button>
        <button
          type="button"
          className="sig-btn-apply"
          disabled={!canApply}
          data-testid="signal-setup-apply"
          onClick={() => onApply(draftToFilter(column.name, draft))}
        >
          Apply
        </button>
      </div>
    </div>,
    document.body,
  );
};
