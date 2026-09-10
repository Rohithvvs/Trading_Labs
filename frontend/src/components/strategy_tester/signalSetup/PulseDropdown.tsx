import React, { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useAnchoredPopover } from "./useAnchoredPopover";

type PulseDropdownProps = {
  selected: boolean;
  anchor: HTMLElement | null;
  onSelectTrue: () => void;
  onRemove: () => void;
  onClose: () => void;
};

export const PulseDropdown: React.FC<PulseDropdownProps> = ({
  selected,
  anchor,
  onSelectTrue,
  onRemove,
  onClose,
}) => {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const pos = useAnchoredPopover(true, anchor, 168);

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target)) return;
      if (anchor?.contains(target)) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [anchor, onClose]);

  if (!pos) return null;

  return createPortal(
    <div
      ref={menuRef}
      className="pulse-menu"
      role="menu"
      aria-label="Momentum Pulse"
      data-testid="pulse-dropdown"
      style={{ top: pos.top, left: pos.left, minWidth: pos.width }}
    >
      <button
        type="button"
        role="menuitemradio"
        aria-checked={selected}
        className={`pulse-menu-item${selected ? " is-selected" : ""}`}
        data-testid="pulse-option-true"
        onClick={onSelectTrue}
      >
        True
      </button>
      <div className="pulse-menu-divider" />
      <button type="button" role="menuitem" className="pulse-menu-item is-remove" data-testid="pulse-option-remove" onClick={onRemove}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          <path d="M10 11v6M14 11v6" />
          <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
        </svg>
        Remove
      </button>
    </div>,
    document.body,
  );
};
