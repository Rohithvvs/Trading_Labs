import React from "react";

export type StrategyBuilderRule = {
  id: string;
  label: string;
  join?: "AND" | "OR";
};

interface StrategyBuilderCardProps {
  rules?: StrategyBuilderRule[];
  logicText?: string;
  universeCount: number;
  timeframe: string;
  positionSide: string;
  exitRule: string;
  capital: number;
  sourceType?: "builder" | "pine";
  onEditClick: () => void;
}

const DEFAULT_RULES: StrategyBuilderRule[] = [
  { id: "1", label: "Close > SMA 50", join: "AND" },
  { id: "2", label: "SMA 50 > SMA 200", join: "AND" },
  { id: "3", label: "RSI > 55", join: "AND" },
  { id: "4", label: "Volume > Avg Volume" },
];

export const StrategyBuilderCard: React.FC<StrategyBuilderCardProps> = ({
  rules = DEFAULT_RULES,
  logicText = "ALL conditions must be true",
  universeCount,
  timeframe = "1 Day",
  positionSide = "LONG ONLY",
  exitRule = "EOD (End of Day)",
  capital = 1000000,
  sourceType = "builder",
  onEditClick,
}) => {
  const displayRules = rules && rules.length > 0 ? rules : DEFAULT_RULES;

  return (
    <div className="st-card st-builder-card" data-testid="card-strategy-builder">
      <div className="st-card-title">
        <span>Strategy Builder</span>
        <button
          type="button"
          className="st-btn-dark"
          style={{ padding: "3px 8px", fontSize: "0.72rem" }}
          onClick={onEditClick}
          data-testid="btn-builder-edit"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          Edit
        </button>
      </div>

      {/* Rules list */}
      <div className="st-filter-list">
        {displayRules.map((rule, idx) => (
          <div key={rule.id || idx} className="st-filter-item">
            <div>
              <span className="st-filter-num">{idx + 1}</span>
              <span>{rule.label}</span>
            </div>
            {rule.join || (idx < displayRules.length - 1) ? (
              <span className="st-filter-tag">{rule.join || "AND"}</span>
            ) : null}
          </div>
        ))}
      </div>

      {/* Logic summary */}
      <div className="st-logic-row">
        Logic: <strong>{logicText.includes("ALL") ? "ALL" : "ANY"}</strong>{" "}
        {logicText.replace(/^(Logic:\s*)?(ALL|ANY)\s*/i, "") || "conditions must be true"}
      </div>

      {/* Meta key-values */}
      <div className="st-builder-meta">
        <div className="st-builder-meta-row">
          <span>Source</span>
          <span className={sourceType === "pine" ? "st-tag-pine" : ""}>
            {sourceType === "pine" ? "Pine Script" : "Builder"}
          </span>
        </div>
        <div className="st-builder-meta-row">
          <span>Universe</span>
          <span>All Stocks ({universeCount})</span>
        </div>
        <div className="st-builder-meta-row">
          <span>Timeframe</span>
          <span>{timeframe}</span>
        </div>
        <div className="st-builder-meta-row">
          <span>Position</span>
          <span className="st-tag-long">{positionSide}</span>
        </div>
        <div className="st-builder-meta-row">
          <span>Exit Rule</span>
          <span>{exitRule}</span>
        </div>
        <div className="st-builder-meta-row">
          <span>Capital</span>
          <span>₹{capital.toLocaleString("en-IN")}</span>
        </div>
      </div>
    </div>
  );
};
