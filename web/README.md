# Heimdall analysis dashboard

Static TypeScript UI: reads **`public/data/snapshot.json`** only (exported from repo data). No live API.

## Local preview

```bash
# From repo root: refresh snapshot from ingested DB
python scripts/publish_dashboard_data.py

cd web && npm install && npm run dev
```

Open http://127.0.0.1:5173

## GitHub Pages

CI [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) exports from `data/dashboard/heimdall.db` and deploys.

**Update site data:** [data/dashboard/README.md](../data/dashboard/README.md)

**Live site:** https://saptreekly.github.io/Project-Heimdall/

Header links on the dashboard point to `snapshot.json` and `heimdall.db` on GitHub.
