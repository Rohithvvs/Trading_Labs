# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: indicator_scanner.spec.ts >> indicator tab validates, applies, and shows mocked scan results
- Location: e2e\indicator_scanner.spec.ts:29:1

# Error details

```
Test timeout of 45000ms exceeded.
```

```
Error: locator.click: Test timeout of 45000ms exceeded.
Call log:
  - waiting for getByTestId('workspace-indicator')

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e7]:
    - switch "Switch to dark theme" [ref=e8] [cursor=pointer]:
      - generic [ref=e9]: Light mode active
      - img [ref=e12]
      - generic [ref=e15]: Light
  - generic [ref=e16]:
    - generic [ref=e17]:
      - generic [ref=e18]:
        - generic [ref=e19]:
          - img [ref=e20]
          - generic [ref=e22]: TradeX
        - generic [ref=e23]:
          - heading "Trade Smarter Invest Better" [level=1] [ref=e24]:
            - text: Trade Smarter
            - text: Invest Better
          - paragraph [ref=e25]: Real-time market data at your fingertips
      - generic [ref=e26]:
        - generic [ref=e27]:
          - img [ref=e28]
          - generic [ref=e30]:
            - generic [ref=e31]: Real-time Data
            - generic [ref=e32]: Live market updates
        - generic [ref=e33]:
          - img [ref=e34]
          - generic [ref=e36]:
            - generic [ref=e37]: Smart Analytics
            - generic [ref=e38]: Track, analyze & grow
        - generic [ref=e39]:
          - img [ref=e40]
          - generic [ref=e42]:
            - generic [ref=e43]: Secure & Reliable
            - generic [ref=e44]: Bank level security
    - generic [ref=e48]:
      - generic [ref=e49]:
        - heading "Welcome back" [level=2] [ref=e50]
        - paragraph [ref=e51]: Please enter your details to sign in
      - paragraph [ref=e52]: Server reachable (2040ms)
      - generic [ref=e53]:
        - generic [ref=e54]:
          - generic [ref=e55]: Email address
          - textbox "you@example.com" [ref=e57]
        - generic [ref=e59]:
          - generic [ref=e60]: Password
          - generic [ref=e61]:
            - textbox "********" [ref=e62]
            - button "Show password" [ref=e64] [cursor=pointer]:
              - generic [ref=e65]:
                - img [ref=e66]
                - img [ref=e69]
        - generic [ref=e71]:
          - generic [ref=e72]:
            - checkbox "Remember for 30 days" [ref=e73]
            - generic [ref=e74]: Remember for 30 days
          - button "Forgot Password?" [ref=e75] [cursor=pointer]
        - button "Sign In" [ref=e76] [cursor=pointer]
      - separator [ref=e77]:
        - generic [ref=e81]: OR
      - generic [ref=e85]:
        - button "Continue with Google. Opens in new tab" [ref=e87] [cursor=pointer]:
          - generic [ref=e89]:
            - img [ref=e91]
            - generic [ref=e98]: Continue with Google
        - iframe
      - generic [ref=e99]:
        - text: Don't have an account?
        - button "Sign up" [ref=e100] [cursor=pointer]
```

# Test source

```ts
  36  |         status: 200,
  37  |         contentType: "application/json",
  38  |         body: JSON.stringify({
  39  |           indicators: [
  40  |             {
  41  |               id: "ind-1",
  42  |               name: "52-Week High Breakout [SCAN]",
  43  |               description: "",
  44  |               source_code: "indicator()",
  45  |               script_version: 6,
  46  |               language_mode: "pine_subset_v1",
  47  |               timeframe: "1D",
  48  |               parsed_definition: { outputs: VALIDATION.outputs },
  49  |               validation_status: "valid",
  50  |               required_bars: 253,
  51  |             },
  52  |           ],
  53  |         }),
  54  |       });
  55  |       return;
  56  |     }
  57  |     await route.fulfill({
  58  |       status: 200,
  59  |       contentType: "application/json",
  60  |       body: JSON.stringify({
  61  |         id: "ind-1",
  62  |         name: "52-Week High Breakout [SCAN]",
  63  |         description: "",
  64  |         source_code: "indicator()",
  65  |         script_version: 6,
  66  |         language_mode: "pine_subset_v1",
  67  |         timeframe: "1D",
  68  |         parsed_definition: { outputs: VALIDATION.outputs },
  69  |         validation_status: "valid",
  70  |         required_bars: 253,
  71  |       }),
  72  |     });
  73  |   });
  74  |   await page.route(`${apiBaseURL}/indicators/ind-1/scans`, async (route) => {
  75  |     await route.fulfill({
  76  |       status: 200,
  77  |       contentType: "application/json",
  78  |       body: JSON.stringify({
  79  |         id: "run-1",
  80  |         scan_id: "IND-E2E-001",
  81  |         status: "queued",
  82  |         universe_size: 755,
  83  |         total_count: 755,
  84  |         processed_count: 0,
  85  |         progress_pct: 0,
  86  |         matched_count: 0,
  87  |       }),
  88  |     });
  89  |   });
  90  |   await page.route(`${apiBaseURL}/indicator-scans/IND-E2E-001`, async (route) => {
  91  |     await route.fulfill({
  92  |       status: 200,
  93  |       contentType: "application/json",
  94  |       body: JSON.stringify({
  95  |         id: "run-1",
  96  |         scan_id: "IND-E2E-001",
  97  |         status: "completed",
  98  |         stage: "completed",
  99  |         universe_size: 755,
  100 |         total_count: 755,
  101 |         processed_count: 755,
  102 |         progress_pct: 100,
  103 |         matched_count: 1,
  104 |         as_of: "2026-08-28",
  105 |         success_count: 755,
  106 |         failed_count: 0,
  107 |         skipped_count: 0,
  108 |       }),
  109 |     });
  110 |   });
  111 |   await page.route(`${apiBaseURL}/indicator-scans/IND-E2E-001/results**`, async (route) => {
  112 |     await route.fulfill({
  113 |       status: 200,
  114 |       contentType: "application/json",
  115 |       body: JSON.stringify({
  116 |         total: 1,
  117 |         page: 1,
  118 |         page_size: 50,
  119 |         outputs: VALIDATION.outputs.map((o) => o.name),
  120 |         results: [
  121 |           {
  122 |             symbol: "RELIANCE",
  123 |             display_name: "Reliance Industries",
  124 |             status: "ok",
  125 |             matched: true,
  126 |             as_of: "2026-08-28",
  127 |             outputs: { "52W Breakout Signal": 1, Close: 1400, "Prior 252 High": 1390 },
  128 |             ohlcv: { volume: 8000000 },
  129 |           },
  130 |         ],
  131 |       }),
  132 |     });
  133 |   });
  134 | 
  135 |   await page.goto("/strategy-tester");
> 136 |   await page.getByTestId("workspace-indicator").click();
      |                                                 ^ Error: locator.click: Test timeout of 45000ms exceeded.
  137 |   await expect(page.getByTestId("indicator-screener")).toBeVisible();
  138 |   await page.getByTestId("btn-add-indicator").click();
  139 |   await expect(page.getByTestId("tab-indicator")).toHaveClass(/is-active/);
  140 |   await expect(page.getByTestId("indicator-editor-panel")).toBeVisible();
  141 |   await page.getByTestId("btn-validate-indicator").click();
  142 |   await expect(page.getByTestId("indicator-validation-panel")).toContainText("Valid");
  143 |   await page.getByTestId("btn-save-apply-indicator").click();
  144 |   await expect(page.getByTestId("indicator-screener")).toBeVisible();
  145 |   await page.getByTestId("btn-scan-indicator").click();
  146 |   await expect(page.getByTestId("indicator-results-table")).toContainText("RELIANCE");
  147 |   await expect(page.getByTestId("indicator-results-table")).toContainText("52W Breakout Signal");
  148 | });
  149 | 
  150 | test("unsupported pine shows a line-specific error", async ({ page }) => {
  151 |   await page.route(`${apiBaseURL}/indicators/validate`, async (route) => {
  152 |     await route.fulfill({
  153 |       status: 200,
  154 |       contentType: "application/json",
  155 |       body: JSON.stringify({
  156 |         ok: false,
  157 |         status: "invalid",
  158 |         errors: [{ line: 2, column: 1, message: "This is an indicator scanner. Use indicator() instead of strategy()." }],
  159 |         warnings: [],
  160 |         inputs: [],
  161 |         outputs: [],
  162 |         required_bars: 0,
  163 |         required_symbols: [],
  164 |       }),
  165 |     });
  166 |   });
  167 |   await page.goto("/strategy-tester");
  168 |   await page.getByTestId("btn-new-strategy").click();
  169 |   await page.getByTestId("tab-indicator").click();
  170 |   await page.getByTestId("pine-textarea").fill('//@version=6\nstrategy("x")\n');
  171 |   await page.getByTestId("btn-validate-indicator").click();
  172 |   await expect(page.getByTestId("indicator-validation-panel")).toContainText("Line 2");
  173 |   await expect(page.getByTestId("btn-save-apply-indicator")).toBeDisabled();
  174 | });
  175 | 
```