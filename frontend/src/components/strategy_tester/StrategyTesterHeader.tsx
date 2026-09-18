import React from "react";

interface StrategyTesterHeaderProps {
  onImportClick: () => void;
  onSaveClick: () => void;
  onNewClick: () => void;
  workspace?: "strategy" | "indicator";
  onWorkspaceChange?: (workspace: "strategy" | "indicator") => void;
}

export const StrategyTesterHeader: React.FC<StrategyTesterHeaderProps> = ({
  onImportClick,
  onSaveClick,
  onNewClick,
  workspace = "strategy",
  onWorkspaceChange,
}) => {
  return (
    <header className="st-page-header">
      <div>
        <h1 className="st-page-header-title">{workspace === "indicator" ? "Indicator Scanner" : "Strategy Tester"}</h1>
        <p className="st-page-header-subtitle">
          {workspace === "indicator"
            ? "Scan the 755-stock universe with a Pine-compatible indicator."
            : "Test trading strategies across the complete stock universe and analyze signals, returns, and filter performance."}
        </p>
        {onWorkspaceChange && (
          <div className="ind-workspace-tabs" role="tablist" aria-label="Strategy tester workspace">
            <button
              type="button"
              role="tab"
              aria-selected={workspace === "strategy"}
              className={`st-modal-tab-btn ${workspace === "strategy" ? "is-active" : ""}`}
              onClick={() => onWorkspaceChange("strategy")}
              data-testid="workspace-strategy"
            >
              Strategy Tester
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={workspace === "indicator"}
              className={`st-modal-tab-btn ${workspace === "indicator" ? "is-active" : ""}`}
              onClick={() => onWorkspaceChange("indicator")}
              data-testid="workspace-indicator"
            >
              Indicator Scanner
            </button>
          </div>
        )}
      </div>
      <div className={`st-header-actions${workspace === "indicator" ? " ind-header-actions" : ""}`}>
        {workspace !== "indicator" && (
          <>
            <button
              type="button"
              className="st-btn-dark"
              onClick={onImportClick}
              title="Import Strategy from JSON"
              data-testid="btn-import-strategy"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Import Strategy
            </button>
            <button
              type="button"
              className="st-btn-dark"
              onClick={onSaveClick}
              title="Save Strategy"
              data-testid="btn-save-strategy"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                <polyline points="17 21 17 13 7 13 7 21" />
                <polyline points="7 3 7 8 15 8" />
              </svg>
              Save Strategy
            </button>
          </>
        )}
        <button
          type="button"
          className="st-btn-primary"
          onClick={onNewClick}
          title={workspace === "indicator" ? "Create New Indicator" : "Create New Strategy"}
          data-testid="btn-new-strategy"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          {workspace === "indicator" ? "New Indicator" : "New Strategy"}
        </button>
        {workspace === "indicator" && <div id="ind-header-scan-slot" className="ind-header-scan-slot" />}
      </div>
    </header>
  );
};
