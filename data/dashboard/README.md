# Dashboard data for GitHub Pages

Committed ingest lives here so CI and the static site use **real** data (not mock seed).

**Publish after ingest** (one command):

```bash
python scripts/publish_dashboard_data.py
git add data/dashboard/heimdall.db web/public/data/snapshot.json
git commit -m "chore: publish ingest data for dashboard"
git push
```

Manual copy:

```bash
cp heimdall.db data/dashboard/heimdall.db
python scripts/export_dashboard_data.py
```

**Automated ingest** (`.github/workflows/ingest.yml`, daily 13:00 UTC):

1. Runs jobs in `data/scheduled_ingest.json` with X guardrails (keyword cap, post cap, daily GraphQL budget)
2. Requires GitHub secrets `AUTH_TOKEN` and `CT0`
3. Commits `heimdall.db`, `x_rate_state.json`, and `snapshot.json`

The Pages workflow (`/.github/workflows/pages.yml`) runs on push after ingest and daily at 14:00 UTC:

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
