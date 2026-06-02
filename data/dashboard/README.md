# Dashboard data for GitHub Pages

Committed ingest lives here so CI and the static site use **real** data (not mock seed).

**Publish after ingest** (one command):

Theme clustering requires ML deps (first run downloads `all-MiniLM-L6-v2`):

```bash
pip install -e ".[ml]"
USE_EMBEDDING_THEMES=true python scripts/publish_dashboard_data.py
```

Or without themes (faster):

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

**Automated ingest** (`.github/workflows/ingest.yml`, **30 runs per 24h** — every **48 minutes** UTC):

1. Runs jobs in `data/scheduled_ingest.json` with X guardrails (one rotated keyword per run ≈ 1 GraphQL request)
2. Requires GitHub secrets `AUTH_TOKEN` and `CT0`
3. Commits `heimdall.db`, `x_rate_state.json`, `x_keyword_rotation.json`, and `snapshot.json`

The Pages workflow (`/.github/workflows/pages.yml`) runs on push after ingest and daily at 14:00 UTC:

1. Opens `data/dashboard/heimdall.db` if present
2. Else uses GitHub secret `DASHBOARD_DATABASE_URL` (optional remote DB)
3. Else export fails (no mock seed) — commit `data/dashboard/heimdall.db` from ingest first
4. Exports `web/public/data/snapshot.json` and deploys the site

**Other GitHub Actions**

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| [`ci.yml`](../../.github/workflows/ci.yml) | Push / PR to `main` | Ruff, pytest, web build, snapshot smoke, export regression |
| [`export.yml`](../../.github/workflows/export.yml) | Manual | Re-export `snapshot.json` from committed DB (optional auto-commit) |
| [`health.yml`](../../.github/workflows/health.yml) | Weekly + manual | Snapshot freshness, schema version, narrative metrics |
| [`maintenance.yml`](../../.github/workflows/maintenance.yml) | Weekly (Sun 05:00 UTC) | DB VACUUM/orphans, theme drift report, keyword audit + gap suggestions |
| [`daily-analytics.yml`](../../.github/workflows/daily-analytics.yml) | Daily 15:30 UTC | Coordination watchlist, tier-crossing GitHub issues |

**Tracked analytics files** (under `data/dashboard/`):

| File | Updated by |
| --- | --- |
| `ingest_runs.jsonl` | Every ingest run (keyword yield audit input) |
| `metrics_history.jsonl` | Daily after Pages export (one JSON line per UTC day) |
| `WATCHLIST.md` / `watchlist_state.json` | Daily coordination watchlist |
| `theme_baseline.json` | Weekly theme drift (comparison baseline) |
| `keyword_suggestions.json` | Weekly keyword gap discovery |
| `keyword_rotation_log.jsonl` | Weekly auto keyword swap audit trail |
| `data/scheduled_ingest.json` | Updated weekly when stale keywords are swapped |

**Keyword auto-rotation** (weekly `maintenance.yml`): removes keywords with 0 yield after 3+ runs (never unpins `2026 midterms`), adds top gap suggestions from theme/corpus analysis. Requires ≥5 ingest runs in the 7-day window before swapping.

Dependabot (`.github/dependabot.yml`) opens weekly PRs for GitHub Actions and npm updates.

**Remove test/mock narratives** (keep only production narratives):

```bash
python scripts/prune_narratives.py --keep midterms_2026
USE_EMBEDDING_THEMES=true python scripts/export_dashboard_data.py
```

You can also export JSON locally without committing the DB:

```bash
python scripts/export_dashboard_data.py
cd web && npm run build
```

`heimdall.db` in the repo root stays gitignored; only `data/dashboard/heimdall.db` is meant to be committed.
