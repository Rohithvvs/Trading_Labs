# Recommendation Lab UI Modernization

**Date:** 2026-08-05  
**Scope:** Frontend presentation only  
**Reference:** `RE.png` (institutional dark dashboard)

---

## Constraints honored

| Must not change | Status |
|-----------------|--------|
| Backend APIs | ✔ same `fetchRe001*` / `fetchRe002*` |
| Recommendation algorithms | ✔ |
| Database / scanner / experiments | ✔ |
| Auth / routing / feature guard | ✔ |
| Existing test IDs | ✔ preserved |

---

## Component hierarchy

```
RecommendationLabPage
├── Header (title, market chips)
├── Engine registration strip (RE-001 / RE-002 status)
├── KPI row → LabMetricCard[]
├── Main grid
│   ├── Experiments Overview table
│   ├── Scan Comparison controls + table (existing load path)
│   └── LabDonutChart (signals, strategies)
├── Charts row
│   ├── LabPerformanceChart
│   ├── LabConfidenceBarChart
│   └── Top Recommendations table
├── Bottom row
│   ├── Recent Activity
│   ├── Engine Status Donut
│   ├── Quick Actions
│   └── Alerts Panel
└── Footer status bar
```

---

## Folder structure

```
frontend/src/
  pages/RecommendationLabPage.tsx          # dashboard composition + data hooks
  components/recommendation-lab/
    index.ts
    recommendationLab.css
    LabMetricCard.tsx
    LabStatusBadge.tsx
    LabDonutChart.tsx
    LabCharts.tsx
    labIcons.tsx
```

---

## Files modified / added

| File | Action |
|------|--------|
| `frontend/src/pages/RecommendationLabPage.tsx` | Redesigned UI |
| `frontend/src/components/recommendation-lab/*` | **New** reusable components |
| `frontend/src/layout/navConfig.tsx` | Lab flask icon |
| `docs/RECOMMENDATION_LAB_UI_MODERNIZATION.md` | This doc |

---

## Data mapping (no fake PnL)

| UI surface | Source |
|------------|--------|
| Lab Engines KPI | Registration count (RE-001/RE-002) |
| Total Recommendations | Sum of recent scan `decision_count` |
| RE-002 BUY (7d) | `fetchRe002Health` |
| Avg Confidence | Loaded comparison rows |
| Best Engine | Highest avg confidence |
| Experiments table | Registration metadata |
| Comparison table | Same merge of RE-001/RE-002 rows |
| Signal donut | Health BUY/WATCH/REJECT or row states |
| Strategy donut | `strategy_name` frequencies |
| Performance chart | Recent scan decision series |
| Confidence bars | Avg RE-001 / RE-002 confidence |
| Top recommendations | Sorted loaded rows |
| Activity / alerts | Registrations, scans, mismatches, health |

---

## Preserved functionality

- Auto-select best recent cohort  
- Manual scan select + paste `scan_run_id`  
- **Load comparison**  
- RE-001 / RE-002 registration status (`data-testid`s)  
- RE-002 health strip  
- Error / info messaging  
- Multi-engine merged comparison table  

---

## How to verify

1. Open `/recommendation-lab` (feature flag on).  
2. Confirm premium dark cards, KPIs, charts render.  
3. Select a cohort → **Load comparison** → table fills.  
4. Export JSON still works.  
5. Links: Scanner, Paper, Performance.  
6. Existing test IDs still present for automation.  
