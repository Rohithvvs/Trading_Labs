import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { SignalCondition } from "../../../api_indicator_scanner";
import { SIGNAL_CONDITIONS } from "../../../utils/signalSetup";
import { ConditionIcon } from "./ConditionIcons";

type SignalConditionDropdownProps = {
  open: boolean;
  value: SignalCondition;
  anchor: HTMLElement | null;
  onSelect: (condition: SignalCondition) => void;
  onClose: () => void;
};

type MenuPos = { top: number; left: number; width: number; maxHeight: number };

function menuPosition(anchor: HTMLElement): MenuPos {
  const rect = anchor.getBoundingClientRect();
  const gap = 4;
  const width = Math.max(rect.width, 220);
  const itemHeight = 36;
  const needed = SIGNAL_CONDITIONS.length * itemHeight + 12;
  const spaceBelow = Math.max(80, window.innerHeight - rect.bottom - 8);
  const spaceAbove = Math.max(80, rect.top - 8);
  const openDown = spaceBelow >= Math.min(needed, 200) || spaceBelow >= spaceAbove;
  const maxHeight = Math.min(needed, openDown ? spaceBelow : spaceAbove);
  const top = openDown ? rect.bottom + gap : Math.max(8, rect.top - maxHeight - gap);
  let left = rect.left;
  if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8);
  return { top, left, width, maxHeight };
}

export const SignalConditionDropdown: React.FC<SignalConditionDropdownProps> = ({
  open,
  value,
  anchor,
  onSelect,
  onClose,
}) => {
  const listRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<MenuPos | null>(null);
  const [activeId, setActiveId] = useState<SignalCondition>(value);

  useEffect(() => {
    setActiveId(value);
  }, [value, open]);

  useEffect(() => {
    if (!open || !anchor) {
      setPos(null);
      return undefined;
    }
    const place = () => setPos(menuPosition(anchor));
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, anchor]);

  useEffect(() => {
    if (!open) return undefined;
    listRef.current?.focus();
    const selected = listRef.current?.querySelector<HTMLElement>("[aria-selected='true']");
    if (selected && typeof selected.scrollIntoView === "function") {
      selected.scrollIntoView({ block: "nearest" });
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      const index = SIGNAL_CONDITIONS.findIndex((item) => item.id === activeId);
      if (event.key === "ArrowDown") {
        event.preventDefault();
        const next = SIGNAL_CONDITIONS[Math.min(SIGNAL_CONDITIONS.length - 1, index + 1)] || SIGNAL_CONDITIONS[0];
        setActiveId(next.id);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        const next = SIGNAL_CONDITIONS[Math.max(0, index - 1)] || SIGNAL_CONDITIONS[0];
        setActiveId(next.id);
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect(activeId);
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose, onSelect, activeId]);

  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-condition-id="${activeId}"]`);
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "nearest" });
  }, [activeId, open]);

  if (!open || !pos) return null;

  return createPortal(
    <div
      ref={listRef}
      className="sig-cond-menu"
      role="listbox"
      tabIndex={0}
      aria-label="Condition"
      data-testid="signal-condition-dropdown"
      style={{ top: pos.top, left: pos.left, width: pos.width, maxHeight: pos.maxHeight }}
      onWheel={(event) => event.stopPropagation()}
    >
      {SIGNAL_CONDITIONS.map((item) => {
        const selected = item.id === value;
        const active = item.id === activeId;
        return (
          <button
            key={item.id}
            type="button"
            role="option"
            aria-selected={selected}
            data-condition-id={item.id}
            className={`sig-cond-option${selected ? " is-selected" : ""}${active ? " is-active" : ""}`}
            data-testid={`signal-condition-${item.id}`}
            onMouseEnter={() => setActiveId(item.id)}
            onClick={() => {
              onSelect(item.id);
              onClose();
            }}
          >
            <ConditionIcon condition={item.id} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </div>,
    document.body,
  );
};
