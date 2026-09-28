import { useState, useEffect, useRef, type ChangeEvent, type DragEvent, type ClipboardEvent } from "react";
import { submitFeedback, type FeedbackCategory } from "../../api_feedback";
import { TELEGRAM_CHANNEL_URL, TELEGRAM_GROUP_URL } from "../../config";

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultCategory?: FeedbackCategory;
  defaultPageOrFeature?: string;
  userEmail?: string | null;
}

const CATEGORIES: { value: FeedbackCategory; label: string; icon: string; desc: string }[] = [
  { value: "bug", label: "Bug / Error", icon: "🐛", desc: "Something is broken or not working as expected" },
  { value: "feature_request", label: "Feature Request", icon: "💡", desc: "Suggest a new tool, indicator, or capability" },
  { value: "confusing_ui", label: "Confusing UI", icon: "❓", desc: "Layout, label, or workflow was difficult to use" },
  { value: "data_issue", label: "Data Issue", icon: "📊", desc: "Price, quote, candle, or calculation looks incorrect" },
  { value: "other", label: "Other", icon: "💬", desc: "General thoughts, questions, or comments" },
];

function resolveCurrentPageName(): string {
  if (typeof window === "undefined") return "App";
  const p = window.location.pathname;
  if (p.startsWith("/scanner")) return "Scanner Dashboard";
  if (p.startsWith("/markets")) return "Markets Overview";
  if (p.startsWith("/paper-order")) return "Paper Order Ticket";
  if (p.startsWith("/paper")) return "Paper Trading Desk";
  if (p.startsWith("/strategy-tester")) return "Strategy Tester";
  if (p.startsWith("/strategy-comparison")) return "Strategy Comparison";
  if (p.startsWith("/stock")) return "Stock Details";
  if (p.startsWith("/performance")) return "Performance Analytics";
  if (p.startsWith("/watchlist")) return "Watchlist";
  if (p.startsWith("/profile")) return "User Profile";
  if (p.startsWith("/admin")) return "Admin Panel";
  return document.title || p || "App";
}

export function FeedbackModal({
  isOpen,
  onClose,
  defaultCategory = "bug",
  defaultPageOrFeature,
  userEmail,
}: FeedbackModalProps) {
  const [category, setCategory] = useState<FeedbackCategory>(defaultCategory);
  const [pageOrFeature, setPageOrFeature] = useState(() => defaultPageOrFeature || resolveCurrentPageName());
  const [message, setMessage] = useState("");
  const [contactMethod, setContactMethod] = useState(() => userEmail || "");
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [screenshotName, setScreenshotName] = useState<string | null>(null);
  const [screenshotSizeKb, setScreenshotSizeKb] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedId, setSubmittedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const messageInputRef = useRef<HTMLTextAreaElement>(null);

  // Sync route name on open
  useEffect(() => {
    if (isOpen) {
      setPageOrFeature(defaultPageOrFeature || resolveCurrentPageName());
      setSubmittedId(null);
      setError(null);
      if (userEmail && !contactMethod) {
        setContactMethod(userEmail);
      }
      setTimeout(() => {
        messageInputRef.current?.focus();
      }, 100);
    }
  }, [isOpen, defaultPageOrFeature, userEmail]);

  // ESC key handler
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleFile = (file: File) => {
    if (!file.type.startsWith("image/")) {
      setError("Please select an image file (PNG, JPG, WebP, etc.).");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("Image file is too large. Max size is 5MB.");
      return;
    }

    setError(null);
    setScreenshotName(file.name);
    setScreenshotSizeKb(Math.round(file.size / 1024));

    const reader = new FileReader();
    reader.onload = (e) => {
      setScreenshot(e.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  // Support pasting image from clipboard (Ctrl+V)
  const handlePaste = (e: ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith("image/")) {
        const file = items[i].getAsFile();
        if (file) {
          handleFile(file);
          break;
        }
      }
    }
  };

  const clearScreenshot = () => {
    setScreenshot(null);
    setScreenshotName(null);
    setScreenshotSizeKb(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) {
      setError("Please describe your feedback or the issue encountered.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const res = await submitFeedback({
        category,
        page_or_feature: pageOrFeature.trim() || resolveCurrentPageName(),
        message: message.trim(),
        contact_method: contactMethod.trim() || undefined,
        screenshot,
      });

      if (res.success) {
        setSubmittedId(res.id);
      } else {
        setError(res.message || "Failed to submit feedback. Please try again.");
      }
    } catch (err: any) {
      setError(err?.message || "An unexpected error occurred. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="ds-modal-scrim"
      role="dialog"
      aria-modal="true"
      aria-labelledby="feedback-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onPaste={handlePaste}
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.72)",
        backdropFilter: "blur(4px)",
        zIndex: 9999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "16px",
        overflowY: "auto",
      }}
    >
      <div
        className="feedback-modal-dialog"
        style={{
          background: "var(--bg-surface-elevated, #181d26)",
          color: "var(--text-primary, #f1f5f9)",
          border: "1px solid var(--border-subtle, #2d3748)",
          borderRadius: "12px",
          width: "100%",
          maxWidth: "580px",
          boxShadow: "0 20px 40px rgba(0, 0, 0, 0.4)",
          padding: "24px",
          position: "relative",
          maxHeight: "92vh",
          overflowY: "auto",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
          <div>
            <h2 id="feedback-modal-title" style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700 }}>
              Send Feedback / Report a Bug
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: "0.85rem", color: "var(--text-secondary, #94a3b8)" }}>
              Public Beta · Your feedback directly influences daily releases
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close feedback dialog"
            style={{
              background: "none",
              border: "none",
              color: "var(--text-secondary, #94a3b8)",
              fontSize: "1.25rem",
              cursor: "pointer",
              padding: "4px 8px",
              borderRadius: "4px",
            }}
          >
            ✕
          </button>
        </div>

        {submittedId ? (
          /* Success Screen */
          <div style={{ textAlign: "center", padding: "28px 12px" }}>
            <div style={{ fontSize: "3rem", marginBottom: "12px" }}>✅</div>
            <h3 style={{ margin: "0 0 8px", fontSize: "1.2rem", fontWeight: 600 }}>Thank You for Your Feedback!</h3>
            <p style={{ color: "var(--text-secondary, #94a3b8)", fontSize: "0.9rem", maxWidth: "420px", margin: "0 auto 20px" }}>
              Submission Reference: <code style={{ color: "#38bdf8" }}>{submittedId}</code>. Our engineering and trading
              desk review every report.
            </p>
            <div
              style={{
                background: "rgba(56, 189, 248, 0.08)",
                border: "1px solid rgba(56, 189, 248, 0.2)",
                borderRadius: "8px",
                padding: "14px",
                marginBottom: "24px",
                textAlign: "left",
              }}
            >
              <div style={{ fontWeight: 600, fontSize: "0.9rem", marginBottom: "6px", color: "#38bdf8" }}>
                💬 Join the Beta Discussion
              </div>
              <p style={{ fontSize: "0.82rem", color: "var(--text-secondary, #94a3b8)", margin: "0 0 10px" }}>
                Connect with our team and fellow beta testers in real time:
              </p>
              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                <a
                  href={TELEGRAM_GROUP_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ds-btn ds-btn--secondary ds-btn--sm"
                  style={{ textDecoration: "none" }}
                >
                  Telegram Discussion Group ↗
                </a>
                <a
                  href={TELEGRAM_CHANNEL_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ds-btn ds-btn--ghost ds-btn--sm"
                  style={{ textDecoration: "none" }}
                >
                  Official Channel ↗
                </a>
              </div>
            </div>
            <button
              type="button"
              className="ds-btn ds-btn--primary"
              onClick={onClose}
              style={{ minWidth: "120px" }}
            >
              Done
            </button>
          </div>
        ) : (
          /* Submission Form */
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {error && (
              <div
                style={{
                  background: "rgba(239, 68, 68, 0.12)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "6px",
                  padding: "10px 14px",
                  color: "#f87171",
                  fontSize: "0.85rem",
                }}
              >
                {error}
              </div>
            )}

            {/* Category selection */}
            <div>
              <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, marginBottom: "8px" }}>
                Category <span style={{ color: "#f87171" }}>*</span>
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "8px" }}>
                {CATEGORIES.map((cat) => {
                  const isSelected = category === cat.value;
                  return (
                    <button
                      key={cat.value}
                      type="button"
                      onClick={() => setCategory(cat.value)}
                      title={cat.desc}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        padding: "8px 10px",
                        borderRadius: "6px",
                        fontSize: "0.82rem",
                        cursor: "pointer",
                        fontWeight: isSelected ? 600 : 400,
                        background: isSelected ? "var(--accent-primary, #2563eb)" : "var(--bg-surface, #212631)",
                        color: isSelected ? "#ffffff" : "var(--text-primary, #f1f5f9)",
                        border: isSelected
                          ? "1px solid var(--accent-primary, #2563eb)"
                          : "1px solid var(--border-subtle, #2d3748)",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <span aria-hidden>{cat.icon}</span>
                      <span>{cat.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Page or Feature Name */}
            <div>
              <label
                htmlFor="feedback-page"
                style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, marginBottom: "6px" }}
              >
                Page or Feature Name
              </label>
              <input
                id="feedback-page"
                type="text"
                value={pageOrFeature}
                onChange={(e) => setPageOrFeature(e.target.value)}
                placeholder="e.g. Scanner Dashboard, Paper Desk, Supertrend indicator"
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  background: "var(--bg-input, #0f1319)",
                  border: "1px solid var(--border-subtle, #2d3748)",
                  color: "inherit",
                  fontSize: "0.88rem",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {/* Message Description */}
            <div>
              <label
                htmlFor="feedback-message"
                style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, marginBottom: "6px" }}
              >
                Description <span style={{ color: "#f87171" }}>*</span>
              </label>
              <textarea
                id="feedback-message"
                ref={messageInputRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={4}
                required
                placeholder="What happened? What did you expect? Any steps to reproduce or details help us fix it quickly."
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: "6px",
                  background: "var(--bg-input, #0f1319)",
                  border: "1px solid var(--border-subtle, #2d3748)",
                  color: "inherit",
                  fontSize: "0.88rem",
                  resize: "vertical",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {/* Screenshot Upload with Drag/Drop & Paste */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <label style={{ fontSize: "0.82rem", fontWeight: 600 }}>Screenshot Upload (Optional)</label>
                <span style={{ fontSize: "0.75rem", color: "var(--text-secondary, #94a3b8)" }}>
                  Tip: Paste with Ctrl+V / ⌘+V
                </span>
              </div>

              {screenshot ? (
                <div
                  style={{
                    position: "relative",
                    borderRadius: "8px",
                    overflow: "hidden",
                    border: "1px solid var(--border-subtle, #2d3748)",
                    background: "#0b0e14",
                    padding: "8px",
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                  }}
                >
                  <img
                    src={screenshot}
                    alt="Uploaded issue screenshot"
                    style={{
                      maxHeight: "80px",
                      maxWidth: "120px",
                      borderRadius: "4px",
                      objectFit: "contain",
                      background: "#000",
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "0.82rem",
                        fontWeight: 600,
                        textOverflow: "ellipsis",
                        overflow: "hidden",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {screenshotName || "Screenshot attached"}
                    </div>
                    {screenshotSizeKb ? (
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary, #94a3b8)" }}>
                        {screenshotSizeKb} KB
                      </div>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={clearScreenshot}
                    className="ds-btn ds-btn--ghost ds-btn--sm"
                    style={{ color: "#f87171" }}
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    border: isDragging ? "2px dashed #38bdf8" : "1px dashed var(--border-subtle, #4b5563)",
                    background: isDragging ? "rgba(56, 189, 248, 0.08)" : "var(--bg-input, #0f1319)",
                    borderRadius: "8px",
                    padding: "16px",
                    textAlign: "center",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    onChange={handleFileInputChange}
                    style={{ display: "none" }}
                    aria-label="Upload screenshot"
                  />
                  <div style={{ fontSize: "1.25rem", marginBottom: "4px" }}>📷</div>
                  <div style={{ fontSize: "0.84rem", fontWeight: 500 }}>
                    Drag & drop a screenshot, or click to browse
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary, #94a3b8)", marginTop: "2px" }}>
                    PNG, JPG, WebP up to 5MB
                  </div>
                </div>
              )}
            </div>

            {/* Contact Method */}
            <div>
              <label
                htmlFor="feedback-contact"
                style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, marginBottom: "6px" }}
              >
                Contact Method (Optional)
              </label>
              <input
                id="feedback-contact"
                type="text"
                value={contactMethod}
                onChange={(e) => setContactMethod(e.target.value)}
                placeholder="Email or @Telegram username (if you'd like follow-up updates)"
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  background: "var(--bg-input, #0f1319)",
                  border: "1px solid var(--border-subtle, #2d3748)",
                  color: "inherit",
                  fontSize: "0.88rem",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {/* Telegram Community Notice */}
            <div
              style={{
                fontSize: "0.78rem",
                color: "var(--text-secondary, #94a3b8)",
                padding: "8px 12px",
                background: "rgba(255, 255, 255, 0.03)",
                borderRadius: "6px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: "6px",
              }}
            >
              <span>Need urgent help? Chat with developers on Telegram:</span>
              <a
                href={TELEGRAM_GROUP_URL}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "#38bdf8", textDecoration: "none", fontWeight: 600 }}
              >
                Join Discussion Group ↗
              </a>
            </div>

            {/* Footer Buttons */}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "8px" }}>
              <button
                type="button"
                className="ds-btn ds-btn--secondary"
                onClick={onClose}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="ds-btn ds-btn--primary"
                disabled={isSubmitting || !message.trim()}
                style={{ minWidth: "130px" }}
              >
                {isSubmitting ? "Sending..." : "Submit Feedback"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
