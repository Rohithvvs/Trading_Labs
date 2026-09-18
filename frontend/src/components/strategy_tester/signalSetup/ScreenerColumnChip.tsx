import React, { useRef } from "react";
import type { IndicatorFilter } from "../../../api_indicator_scanner";
import type { AbsorbedOutput } from "../../../utils/indicatorAbsorb";
import { columnSetupKind, pulseFilter } from "../../../utils/signalSetup";
import { PulseDropdown } from "./PulseDropdown";
import { SignalManualSetup } from "./SignalManualSetup";

type ScreenerColumnChipProps = {
  column: AbsorbedOutput;
  columns: AbsorbedOutput[];
  filter?: IndicatorFilter | null;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  onApplyFilter: (filter: IndicatorFilter) => void;
  onRemoveColumn: (field: string) => void;
};

export const ScreenerColumnChip: React.FC<ScreenerColumnChipProps> = ({
  column,
  columns,
  filter,
  open,
  onToggle,
  onClose,
  onApplyFilter,
  onRemoveColumn,
}) => {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const kind = columnSetupKind(column);
  const hasFilter = Boolean(filter);
  const className = `ind-pill${open ? " is-open" : ""}${hasFilter ? " has-filter" : ""}`;

  return (
    <div className="ind-chip-anchor">
      <button
        ref={buttonRef}
        type="button"
        className={className}
        aria-haspopup={kind === "pulse" ? "menu" : "dialog"}
        aria-expanded={open}
        data-testid={`screener-column-${column.name}`}
        onClick={onToggle}
      >
        {column.name}
      </button>
      {open && kind === "pulse" && (
        <PulseDropdown
          selected={filter?.operator !== "is_false"}
          anchor={buttonRef.current}
          onSelectTrue={() => {
            onApplyFilter(pulseFilter(column.name, true));
            onClose();
          }}
          onRemove={() => {
            onRemoveColumn(column.name);
            onClose();
          }}
          onClose={onClose}
        />
      )}
      {open && kind !== "pulse" && (
        <SignalManualSetup
          column={column}
          columns={columns}
          existing={filter}
          anchor={buttonRef.current}
          onApply={(next) => {
            onApplyFilter(next);
            onClose();
          }}
          onCancel={onClose}
        />
      )}
    </div>
  );
};
