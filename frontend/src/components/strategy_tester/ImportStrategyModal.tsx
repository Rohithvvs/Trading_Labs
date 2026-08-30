import React, { useState } from "react";

interface ImportStrategyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (jsonContent: string) => void;
}

export const ImportStrategyModal: React.FC<ImportStrategyModalProps> = ({
  isOpen,
  onClose,
  onImport,
}) => {
  const [jsonText, setJsonText] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleImport = () => {
    try {
      if (!jsonText.trim()) {
        setError("Please enter JSON strategy definition.");
        return;
      }
      JSON.parse(jsonText);
      setError(null);
      onImport(jsonText);
      onClose();
    } catch (e: any) {
      setError(`Invalid JSON format: ${e.message}`);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      setJsonText(content);
    };
    reader.readAsText(file);
  };

  return (
    <div className="st-modal-overlay" onClick={onClose} data-testid="modal-import-strategy">
      <div className="st-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="st-modal-header">
          <h2>Import Strategy Definition</h2>
          <button
            type="button"
            className="st-detail-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        <div className="st-modal-body">
          <p style={{ color: "#94a3b8", fontSize: "0.8125rem", margin: 0 }}>
            Paste a strategy configuration JSON below or choose a JSON file from your disk.
          </p>

          <input
            type="file"
            accept=".json"
            onChange={handleFileUpload}
            style={{ color: "#cbd5e1", fontSize: "0.75rem" }}
          />

          <textarea
            rows={10}
            value={jsonText}
            onChange={(e) => {
              setJsonText(e.target.value);
              setError(null);
            }}
            placeholder='{\n  "name": "Custom Momentum",\n  "description": "...",\n  "filters": [...]\n}'
            style={{
              width: "100%",
              background: "#050a16",
              border: "1px solid #1e293b",
              borderRadius: 6,
              padding: 10,
              color: "#f1f5f9",
              fontFamily: "monospace",
              fontSize: "0.8125rem",
              boxSizing: "border-box",
              resize: "vertical",
            }}
            data-testid="textarea-import-json"
          />

          {error ? (
            <div style={{ color: "#f87171", fontSize: "0.75rem", fontWeight: 600 }}>
              {error}
            </div>
          ) : null}
        </div>

        <div className="st-modal-footer">
          <button type="button" className="st-btn-dark" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="st-btn-primary" onClick={handleImport} data-testid="btn-confirm-import">
            Import
          </button>
        </div>
      </div>
    </div>
  );
};
