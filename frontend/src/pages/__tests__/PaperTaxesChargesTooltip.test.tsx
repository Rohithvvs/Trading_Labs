import "@testing-library/jest-dom";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { InfoTooltip } from "../../components/InfoTooltip";

describe("Paper Desk Taxes & Charges Tooltips", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("renders Taxes & Charges tooltip trigger and shows breakdown on hover", () => {
    render(
      <div>
        <span>Taxes &amp; Charges</span>
        <InfoTooltip
          position="top"
          maxWidth="320px"
          ariaLabel="Taxes and statutory charges breakdown"
          content={
            <div>
              <div>Taxes &amp; Charges Breakdown</div>
              <div>Brokerage: ₹20.00</div>
              <div>STT: 0.1%</div>
              <div>Exchange Turnover: 0.00307%</div>
              <div>SEBI Charges: 0.0001%</div>
              <div>Stamp Duty: 0.015%</div>
              <div>GST: 18%</div>
            </div>
          }
        />
      </div>
    );

    const infoBtn = screen.getByRole("button", { name: "Taxes and statutory charges breakdown" });
    expect(infoBtn).toBeInTheDocument();

    act(() => {
      fireEvent.mouseEnter(infoBtn);
      vi.advanceTimersByTime(10);
    });

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toBeInTheDocument();
    expect(tooltip).toHaveTextContent("Brokerage: ₹20.00");
    expect(tooltip).toHaveTextContent("STT: 0.1%");
    expect(tooltip).toHaveTextContent("Exchange Turnover: 0.00307%");
    expect(tooltip).toHaveTextContent("SEBI Charges: 0.0001%");
    expect(tooltip).toHaveTextContent("GST: 18%");
  });
});
