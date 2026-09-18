import { expect, test } from "@playwright/test";

import { apiBaseURL } from "./helpers";

const VALIDATION = {
  ok: true,
  status: "valid",
  errors: [],
  warnings: [{ line: 1, column: 1, message: "Input 'ATR Multiplier' is defined but is not used by this indicator." }],
  inputs: [
    { name: "breakoutLength", title: "Breakout Lookback", kind: "int", default: 252 },
    { name: "atrMultiplier", title: "ATR Multiplier", kind: "float", default: 3.0 },
  ],
  outputs: [
    { name: "52W Breakout Signal", kind: "plot" },
    { name: "Close", kind: "plot" },
    { name: "Prior 252 High", kind: "plot" },
    { name: "Volume SMA 20", kind: "plot" },
    { name: "Custom ATR 14", kind: "plot" },
    { name: "NIFTY 500 Close", kind: "plot" },
    { name: "NIFTY 500 SMA 50", kind: "plot" },
    { name: "52W Breakout", kind: "plotshape" },
    { name: "52W Breakout Scan", kind: "alertcondition" },
  ],
  required_bars: 253,
  required_symbols: ["NSE:CNX500"],
};

test("indicator tab validates, applies, and shows mocked scan results", async ({ page }) => {
  await page.route(`${apiBaseURL}/indicators/validate`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(VALIDATION) });
  });
  await page.route(`${apiBaseURL}/indicators`, async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          indicators: [
            {
              id: "ind-1",
              name: "52-Week High Breakout [SCAN]",
              description: "",
              source_code: "indicator()",
              script_version: 6,
              language_mode: "pine_subset_v1",
              timeframe: "1D",
              parsed_definition: { outputs: VALIDATION.outputs },
              validation_status: "valid",
              required_bars: 253,
            },
          ],
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "ind-1",
        name: "52-Week High Breakout [SCAN]",
        description: "",
        source_code: "indicator()",
        script_version: 6,
        language_mode: "pine_subset_v1",
        timeframe: "1D",
        parsed_definition: { outputs: VALIDATION.outputs },
        validation_status: "valid",
        required_bars: 253,
      }),
    });
  });
  await page.route(`${apiBaseURL}/indicators/ind-1/scans`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "run-1",
        scan_id: "IND-E2E-001",
        status: "queued",
        universe_size: 755,
        total_count: 755,
        processed_count: 0,
        progress_pct: 0,
        matched_count: 0,
      }),
    });
  });
  await page.route(`${apiBaseURL}/indicator-scans/IND-E2E-001`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "run-1",
        scan_id: "IND-E2E-001",
        status: "completed",
        stage: "completed",
        universe_size: 755,
        total_count: 755,
        processed_count: 755,
        progress_pct: 100,
        matched_count: 1,
        as_of: "2026-08-28",
        success_count: 755,
        failed_count: 0,
        skipped_count: 0,
      }),
    });
  });
  await page.route(`${apiBaseURL}/indicator-scans/IND-E2E-001/results**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 1,
        page: 1,
        page_size: 50,
        outputs: VALIDATION.outputs.map((o) => o.name),
        results: [
          {
            symbol: "RELIANCE",
            display_name: "Reliance Industries",
            status: "ok",
            matched: true,
            as_of: "2026-08-28",
            outputs: { "52W Breakout Signal": 1, Close: 1400, "Prior 252 High": 1390 },
            ohlcv: { volume: 8000000 },
          },
        ],
      }),
    });
  });

  await page.goto("/strategy-tester");
  await page.getByTestId("workspace-indicator").click();
  await expect(page.getByTestId("indicator-screener")).toBeVisible();
  await page.getByTestId("btn-add-indicator").click();
  await expect(page.getByTestId("tab-indicator")).toHaveClass(/is-active/);
  await expect(page.getByTestId("indicator-editor-panel")).toBeVisible();
  await page.getByTestId("btn-validate-indicator").click();
  await expect(page.getByTestId("indicator-validation-panel")).toContainText("Valid");
  await page.getByTestId("btn-save-apply-indicator").click();
  await expect(page.getByTestId("indicator-screener")).toBeVisible();
  await page.getByTestId("btn-scan-indicator").click();
  await expect(page.getByTestId("indicator-results-table")).toContainText("RELIANCE");
  await expect(page.getByTestId("indicator-results-table")).toContainText("52W Breakout Signal");
});

test("unsupported pine shows a line-specific error", async ({ page }) => {
  await page.route(`${apiBaseURL}/indicators/validate`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        status: "invalid",
        errors: [{ line: 2, column: 1, message: "This is an indicator scanner. Use indicator() instead of strategy()." }],
        warnings: [],
        inputs: [],
        outputs: [],
        required_bars: 0,
        required_symbols: [],
      }),
    });
  });
  await page.goto("/strategy-tester");
  await page.getByTestId("btn-new-strategy").click();
  await page.getByTestId("tab-indicator").click();
  await page.getByTestId("pine-textarea").fill('//@version=6\nstrategy("x")\n');
  await page.getByTestId("btn-validate-indicator").click();
  await expect(page.getByTestId("indicator-validation-panel")).toContainText("Line 2");
  await expect(page.getByTestId("btn-save-apply-indicator")).toBeEnabled();
  await page.getByTestId("btn-save-apply-indicator").click();
  await expect(page.getByTestId("indicator-editor-panel")).toBeVisible();
  await expect(page.getByTestId("indicator-validation-panel")).toContainText("Line 2");
});
