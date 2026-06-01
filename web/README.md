# Heimdall analysis dashboard

Vite + TypeScript UI for narrative outrage, CIB, and copypasta clusters.

## Local development

```bash
# From repo root
uvicorn heimdall.main:app --reload

cd web && npm install && npm run dev
```

Open http://127.0.0.1:5173 — API base defaults to `/api/v1` (proxied to port 8000).

## GitHub Pages

CI [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) on schedule + push:

1. Load `data/dashboard/heimdall.db` (committed) or `DASHBOARD_DATABASE_URL` secret
2. `python scripts/export_dashboard_data.py` → `web/public/data/snapshot.json`
3. Build with `VITE_BASE=/Project-Heimdall/` and deploy

**Enable Pages:** Settings → Pages → Source: **GitHub Actions**.

**Publish real data:** `cp heimdall.db data/dashboard/heimdall.db && git push` — see [data/dashboard/README.md](../data/dashboard/README.md).

**Live API** (optional): expand “Live API” on the site; set `CORS_ORIGINS` for your host.

## Build

```bash
cd web
cp .env.example .env   # optional
npm run build
```

Output: `web/dist/` (also served by FastAPI when present).
