# Heimdall analysis dashboard

Static TypeScript UI built with **Vite 6** (no React). Reads bundled JSON only — **no live API** on GitHub Pages.

**Live site:** https://saptreekly.github.io/Project-Heimdall/

Data operator guide: [`data/dashboard/README.md`](../data/dashboard/README.md)

---

## Local preview

```bash
# From repo root: copy DB + export snapshot + briefs
python scripts/publish_dashboard_data.py

cd web && npm install && npm run dev
```

Open http://127.0.0.1:5173

Production build (matches CI base path):

```bash
VITE_BASE=/Project-Heimdall/ npm run build
```

---

## Data sources

| Asset | Path | Notes |
| --- | --- | --- |
| Snapshot | `public/data/snapshot.json` | Narratives, posts (cohort cap), themes, CIB, coordination |
| Briefs | `public/data/briefs/` | Precomputed Markdown per narrative + `INDEX.md` |

The dashboard header links to these files on GitHub for transparency.

When `web/dist` exists, FastAPI can serve the built site at `/` alongside `/api/v1`.

---

## Navigation

Single-page app with URL query state (no client-side router).

### Tabs

| Tab | URL param | Content |
| --- | --- | --- |
| **Desk** | `tab=analysis` (default) | Main analysis workspace |
| **Briefing** | `tab=brief` | Auto-generated narrative brief |
| **Methodology** | `tab=methodology` | Scoring and data provenance notes |

### Desk modes

| Mode | URL param | Focus |
| --- | --- | --- |
| **Pulse** | `mode=pulse` | Metrics, charts, alert summary |
| **Frames** | `mode=frames` (default) | Theme clusters, coordination cards, tier labels |
| **Evidence** | `mode=evidence` | Post stream, investigation filters, desk inspector |
| **Network** | `mode=network` | Propagation graph, fuzzy duplicates, cross-pollination |

### Examples

```
/?narrative=1
/?narrative=1&tab=brief
/?narrative=1&mode=network
/?narrative=1&mode=evidence&tab=analysis
```

Narrative IDs are database-specific. The app prefers the narrative named `midterms_2026` when bootstrapping.

---

## Key modules

| File | Role |
| --- | --- |
| `src/main.ts` | Shell, tab/mode switching, data load |
| `src/api.ts` | Fetch bundled snapshot |
| `src/desk-modes.ts` | Pulse / Frames / Evidence / Network panels |
| `src/desk-inspector.ts` | Coordination + duplicate investigation |
| `src/emerging-themes.ts` | Theme cluster cards + coordination overlay |
| `src/propagation-graph.ts` | vis-network graph |
| `src/brief.ts` | Briefing tab (precomputed Markdown) |
| `src/alerts.ts` | Alert tier display |

---

## GitHub Pages deploy

[`.github/workflows/pages.yml`](../.github/workflows/pages.yml):

1. Exports from `data/dashboard/heimdall.db`
2. Builds with `VITE_BASE=/Project-Heimdall/`
3. Deploys to GitHub Pages

Triggered after successful ingest, on filtered pushes to `main`, daily at 14:00 UTC, and manually.
