# Screenshots

This directory is intentionally empty in the committed repository. Screenshots are not
checked in because they would show a specific data vintage and go stale as soon as NHS
England publishes the next month.

## Capturing them

```bash
make data      # or: make demo
make dev
```

Then capture each screen at a 1440px-wide viewport:

| File | URL | What to show |
|---|---|---|
| `01-control-room.png` | `/` | KPI row, attention list, priority matrix, ranked table |
| `02-service-detail.png` | `/service/{provider}/{specialty}` | Forecast overlay and score decomposition |
| `03-scenario.png` | `/service/{provider}/{specialty}` | Scenario simulator with the assumptions panel expanded |
| `04-rankings.png` | `/rankings` | Sorted table with filters applied |
| `05-compare.png` | `/compare` | Provider comparison against the peer median |
| `06-data-quality.png` | `/quality` | Dimension scores and the issue register |
| `07-methodology.png` | `/methodology` | Formulas and the limitations section |

## Before publishing a screenshot

- **Check the provenance strip.** If the header shows the amber
  *"DEMO DATA — illustrative only"* banner, the figures are synthetic. Never present a
  demo-mode screenshot as an NHS England finding.
- **Keep the footer visible** where practical — it carries the source, reporting period
  and the non-affiliation notice.
- Remember that priority scores, forecasts and scenario figures are **derived measures
  produced by this application**, not NHS England statistics.
