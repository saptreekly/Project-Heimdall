# Dashboard database for GitHub Pages

Copy your local SQLite export here so scheduled CI can publish **real** ingest data:

```bash
cp heimdall.db data/dashboard/heimdall.db
git add data/dashboard/heimdall.db
git commit -m "chore: refresh dashboard database"
git push
```

The Pages workflow (`/.github/workflows/pages.yml`) runs daily and on push:

1. Opens `data/dashboard/heimdall.db` if present
2. Else uses GitHub secret `DASHBOARD_DATABASE_URL` (optional remote DB)
3. Else seeds mock demo data
4. Exports `web/public/data/snapshot.json` and deploys the site

You can also export JSON locally without committing the DB:

```bash
python scripts/export_dashboard_data.py
cd web && npm run build
```

`heimdall.db` in the repo root stays gitignored; only `data/dashboard/heimdall.db` is meant to be committed.
