import "@testing-library/jest-dom";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { InfoTooltip } from "../InfoTooltip";

describe("InfoTooltip Component", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("renders the trigger button with the default aria-label", () => {
    render(<InfoTooltip content="Test explanation" />);
    const btn = screen.getByRole("button", { name: "More information" });
    expect(btn).toBeInTheDocument();
  });

  it("renders with a custom aria-label", () => {
    render(<InfoTooltip content="Test explanation" ariaLabel="Custom help text" />);
    expect(screen.getByRole("button", { name: "Custom help text" })).toBeInTheDocument();
  });

  it("shows tooltip content on mouseEnter and hides on mouseLeave", () => {
    render(<InfoTooltip content="Helpful tooltip detail" />);
    const btn = screen.getByRole("button");

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    // Mouse enter triggers tooltip display
    fireEvent.mouseEnter(btn);
    act(() => {
      vi.advanceTimersByTime(10);
    });

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toBeInTheDocument();
    expect(tooltip).toHaveTextContent("Helpful tooltip detail");

    // Mouse leave triggers hide after grace period (120ms)
    fireEvent.mouseLeave(btn);
    expect(screen.getByRole("tooltip")).toBeInTheDocument(); // still visible during grace period

    act(() => {
      vi.advanceTimersByTime(150);
    });

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("maintains visibility when moving mouse from button to tooltip popover", () => {
    render(<InfoTooltip content="Interactive content" />);
    const btn = screen.getByRole("button");

    fireEvent.mouseEnter(btn);
    act(() => {
      vi.advanceTimersByTime(10);
    });

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toBeInTheDocument();

    // Mouse leaves button
    fireEvent.mouseLeave(btn);

    // Mouse enters tooltip popover before timeout expires
    act(() => {
      vi.advanceTimersByTime(50);
    });
    fireEvent.mouseEnter(tooltip);

    // After remaining time, tooltip should STILL be visible
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    // Once leaving tooltip, it hides after timeout
    fireEvent.mouseLeave(tooltip);
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("toggles tooltip visibility on click", () => {
    render(<InfoTooltip content="Toggleable detail" />);
    const btn = screen.getByRole("button");

    fireEvent.click(btn);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    fireEvent.click(btn);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("dismisses tooltip on Escape key press", () => {
    render(<InfoTooltip content="Dismissible with Escape" />);
    const btn = screen.getByRole("button");

    fireEvent.click(btn);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("dismisses tooltip on outside pointer down", () => {
    render(
      <div>
        <div data-testid="outside-element">Outside</div>
        <InfoTooltip content="Dismissible on outside click" />
      </div>
    );
    const btn = screen.getByRole("button");
    const outside = screen.getByTestId("outside-element");

    fireEvent.click(btn);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    fireEvent.pointerDown(outside);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("shows tooltip on focus and hides on blur", () => {
    render(<InfoTooltip content="Accessible focus content" />);
    const btn = screen.getByRole("button");

    fireEvent.focus(btn);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    fireEvent.blur(btn);
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("renders a custom icon when provided", () => {
    render(
      <InfoTooltip
        content="Custom icon text"
        icon={<span data-testid="custom-icon">?</span>}
      />
    );
    expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
  });
});
