import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { downsampleValues, Sparkline } from "../Sparkline";

describe("Sparkline", () => {
  it("downsamples long series before drawing", () => {
    const values = Array.from({ length: 400 }, (_, i) => i);
    expect(downsampleValues(values, 32)).toHaveLength(32);
    expect(downsampleValues(values, 32)[0]).toBe(0);
    expect(downsampleValues(values, 32)[31]).toBe(399);
  });

  it("renders an svg path instead of a chart library", () => {
    const { container } = render(<Sparkline values={[100, 102, 99, 110]} />);
    expect(container.querySelector("svg.sparkline")).toBeTruthy();
    expect(container.querySelector("path")).toBeTruthy();
    expect(container.querySelector(".recharts-wrapper")).toBeNull();
  });
});
