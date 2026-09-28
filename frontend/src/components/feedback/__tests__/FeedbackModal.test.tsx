import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { FeedbackModal } from "../FeedbackModal";
import * as apiFeedback from "../../../api_feedback";

vi.mock("../../../api_feedback", () => ({
  submitFeedback: vi.fn().mockResolvedValue({ success: true, id: "fb_test123", message: "Saved" }),
}));

describe("FeedbackModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(<FeedbackModal isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders with title and category options when open", () => {
    render(<FeedbackModal isOpen={true} onClose={vi.fn()} userEmail="tester@example.com" />);
    expect(screen.getByText("Send Feedback / Report a Bug")).toBeTruthy();
    expect(screen.getByText("Bug / Error")).toBeTruthy();
    expect(screen.getByText("Feature Request")).toBeTruthy();
    expect(screen.getByText("Confusing UI")).toBeTruthy();
    expect(screen.getByText("Data Issue")).toBeTruthy();
    expect(screen.getByText("Other")).toBeTruthy();
  });

  it("displays pre-filled contact method from userEmail", () => {
    render(<FeedbackModal isOpen={true} onClose={vi.fn()} userEmail="tester@example.com" />);
    const contactInput = screen.getByLabelText(/Contact Method/i) as HTMLInputElement;
    expect(contactInput.value).toBe("tester@example.com");
  });

  it("allows typing message and submitting feedback", async () => {
    const submitSpy = vi.spyOn(apiFeedback, "submitFeedback");

    render(<FeedbackModal isOpen={true} onClose={vi.fn()} defaultPageOrFeature="Scanner Dashboard" />);

    const textarea = screen.getByLabelText(/Description/i);
    fireEvent.change(textarea, { target: { value: "Buttons are misaligned on Safari." } });

    // Click Category: Confusing UI
    const uiBtn = screen.getByText("Confusing UI");
    fireEvent.click(uiBtn);

    const submitBtn = screen.getByRole("button", { name: /Submit Feedback/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(submitSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          category: "confusing_ui",
          page_or_feature: "Scanner Dashboard",
          message: "Buttons are misaligned on Safari.",
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/Thank You for Your Feedback!/i)).toBeTruthy();
    });
  });

  it("calls onClose when ESC is pressed", () => {
    const onClose = vi.fn();
    render(<FeedbackModal isOpen={true} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
