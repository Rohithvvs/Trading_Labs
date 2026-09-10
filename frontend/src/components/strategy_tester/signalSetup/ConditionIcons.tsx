import React from "react";
import type { SignalCondition } from "../../../api_indicator_scanner";

function IconFrame({ children }: { children: React.ReactNode }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" className="sig-cond-icon">
      {children}
    </svg>
  );
}

const stroke = "#94a3b8";
const accent = "#38bdf8";

export function ConditionIcon({ condition }: { condition: SignalCondition }) {
  switch (condition) {
    case "above":
      return (
        <IconFrame>
          <path d="M2 12h14" stroke={stroke} strokeDasharray="2 2" />
          <path d="M2 10 C6 4 12 4 16 8" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "above_or_equal":
      return (
        <IconFrame>
          <path d="M2 12h14" stroke={stroke} />
          <path d="M2 10 C6 4 12 5 16 9" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "below":
      return (
        <IconFrame>
          <path d="M2 6h14" stroke={stroke} strokeDasharray="2 2" />
          <path d="M2 8 C6 14 12 14 16 10" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "below_or_equal":
      return (
        <IconFrame>
          <path d="M2 6h14" stroke={stroke} />
          <path d="M2 8 C6 14 12 13 16 9" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "crosses":
      return (
        <IconFrame>
          <path d="M2 9h14" stroke={stroke} />
          <path d="M2 13 C7 13 8 4 16 5" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "crosses_up":
      return (
        <IconFrame>
          <path d="M2 10h14" stroke={stroke} />
          <path d="M2 14 C8 14 9 4 16 4" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "crosses_down":
      return (
        <IconFrame>
          <path d="M2 8h14" stroke={stroke} />
          <path d="M2 4 C8 4 9 14 16 14" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "between":
      return (
        <IconFrame>
          <path d="M2 5h14M2 13h14" stroke={stroke} />
          <path d="M2 9 C6 7 12 11 16 9" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "outside":
      return (
        <IconFrame>
          <path d="M2 6h14M2 12h14" stroke={stroke} />
          <path d="M2 3 C6 3 8 15 16 15" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
    case "equal":
    default:
      return (
        <IconFrame>
          <path d="M2 9h14" stroke={stroke} />
          <path d="M2 9 C6 6 12 12 16 9" stroke={accent} fill="none" strokeWidth="1.4" />
        </IconFrame>
      );
  }
}
