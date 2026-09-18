import React, { useState } from "react";

interface SaveStrategyModalProps {
  isOpen: boolean;
  initialName: string;
  initialDescription: string;
  onClose: () => void;
  onSave: (name: string, description: string) => void;
}

export const SaveStrategyModal: React.FC<SaveStrategyModalProps> = ({
  isOpen,
  initialName,
  initialDescription,
  onClose,
  onSave,
}) => {
  const [name, setName] = useState(initialName || "");
  const [description, setDescription] = useState(initialDescription || "");
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSave = () => {
    if (!name.trim()) {
      setError("Strategy name is required.");
      return;
    }
    setError(null);
    onSave(name.trim(), description.trim());
    onClose();
  };

  return (
    <div className="st-modal-overlay" onClick={onClose} data-testid="modal-save-strategy">
      <div className="st-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="st-modal-header">
          <h2>Save Strategy Definition</h2>
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
          <div className="st-config-field">
            <label htmlFor="st-save-name">Strategy Name</label>
            <div className="st-config-box">
              <input
                id="st-save-name"
                type="text"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setError(null);
                }}
                placeholder="e.g. My Custom Momentum"
                data-testid="input-save-strategy-name"
              />
            </div>
          </div>

          <div className="st-config-field">
            <label htmlFor="st-save-desc">Description</label>
            <div className="st-config-box" style={{ height: "auto", minHeight: 64 }}>
              <textarea
                id="st-save-desc"
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe your strategy logic and criteria..."
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#f1f5f9",
                  fontSize: "0.8125rem",
                  width: "100%",
                  outline: "none",
                  resize: "vertical",
                }}
                data-testid="textarea-save-strategy-desc"
              />
            </div>
          </div>

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
          <button type="button" className="st-btn-primary" onClick={handleSave} data-testid="btn-confirm-save">
            Save Strategy
          </button>
        </div>
      </div>
    </div>
  );
};
