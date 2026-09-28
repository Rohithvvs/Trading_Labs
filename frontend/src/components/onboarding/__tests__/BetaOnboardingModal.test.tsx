import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import {
  BetaOnboardingModal,
  hasAcknowledgedBetaOnboarding,
  setAcknowledgedBetaOnboarding,
  BETA_ONBOARDING_STORAGE_KEY,
} from "../BetaOnboardingModal";

describe("BetaOnboardingModal", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("checks and sets localStorage acknowledgment correctly", () => {
    expect(hasAcknowledgedBetaOnboarding()).toBe(false);
    setAcknowledgedBetaOnboarding(true);
    expect(hasAcknowledgedBetaOnboarding()).toBe(true);
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(<BetaOnboardingModal isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders all 5 required beta principles when open", () => {
    render(<BetaOnboardingModal isOpen={true} onClose={vi.fn()} />);

    // 1. Paper trading only
    expect(screen.getByText("Paper Trading Only")).toBeTruthy();
    // 2. No live trade orders
    expect(screen.getByText("No Live Trade Orders")).toBeTruthy();
    // 3. Not investment advice
    expect(screen.getByText("Not Investment Advice")).toBeTruthy();
    // 4. Data may be delayed or unavailable
    expect(screen.getByText("Data May Be Delayed or Unavailable")).toBeTruthy();
    // 5. How to report a bug
    expect(screen.getByText("How to Report a Bug")).toBeTruthy();
  });

  it("persists acknowledgment and closes when user clicks I Understand", () => {
    const onClose = vi.fn();
    render(<BetaOnboardingModal isOpen={true} onClose={onClose} />);

    const ackBtn = screen.getByRole("button", { name: /I Understand & Acknowledge/i });
    fireEvent.click(ackBtn);

    expect(onClose).toHaveBeenCalled();
    expect(localStorage.getItem(BETA_ONBOARDING_STORAGE_KEY)).toBe("true");
  });

  it("links to official Telegram channel and discussion group", () => {
    render(<BetaOnboardingModal isOpen={true} onClose={vi.fn()} />);

    const channelLink = screen.getByRole("link", { name: /Channel/i });
    const discussionLink = screen.getByRole("link", { name: /Discussion Group/i });

    expect(channelLink.getAttribute("href")).toContain("t.me");
    expect(discussionLink.getAttribute("href")).toContain("t.me");
  });

  it("closes when ESC is pressed", () => {
    const onClose = vi.fn();
    render(<BetaOnboardingModal isOpen={true} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
