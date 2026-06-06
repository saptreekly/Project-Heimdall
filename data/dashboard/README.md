# Dashboard data for GitHub Pages

Committed ingest and analytics live here so CI and the static site use **real** data (not mock seed).

The root `heimdall.db` is gitignored. Only **`data/dashboard/heimdall.db`** is meant to be committed.

---

## Publish after local ingest

**One command** (copies root DB, exports snapshot + briefs):

```bash
pip install -e ".[ml]"   # optional; sentence-transformer themes (first run downloads model)
USE_EMBEDDING_THEMES=true python scripts/publish_dashboard_data.py

git add data/dashboard/heimdall.db web/public/data/snapshot.json web/public/data/briefs
git commit -m "chore: publish ingest data for dashboard"
git push
```

Without ML extras (TF-IDF themes only, faster):

```bash
python scripts/publish_dashboard_data.py
```

Manual steps:

```bash
cp heimdall.db data/dashboard/heimdall.db
DATABASE_URL=sqlite+aiosqlite:///./data/dashboard/heimdall.db \
  USE_EMBEDDING_THEMES=true \
  python scripts/export_dashboard_data.py
```

---

## Automated ingest pipeline

[`.github/workflows/ingest.yml`](../../.github/workflows/ingest.yml) runs **~30 times per 24 hours** (five staggered cron schedules).

Each run:

1. Loads jobs from [`data/scheduled_ingest.json`](../scheduled_ingest.json)
2. Selects **one keyword** per run (`X_SCHEDULED_KEYWORDS_PER_RUN=1`)
3. Uses **`explore_yield`** rotation — under-sampled keywords first, then top-yield pool
4. Alternates X search product **Latest ↔ Top**
5. Enforces X guardrails (daily GraphQL cap **45**, per-search limits)
6. Exports `web/public/data/snapshot.json` + briefs
7. Commits changed files (see list below)

**GitHub secrets:** `AUTH_TOKEN` and `CT0` (aliases `X_AUTH_TOKEN`, `X_CT0`)

**Env paths in CI:**

| Variable | CI value |
| --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/dashboard/heimdall.db` |
| `X_RATE_STATE_PATH` | `data/dashboard/x_rate_state.json` |
| `X_ROTATION_STATE_PATH` | `data/dashboard/x_keyword_rotation.json` |
| `X_AUTHOR_WATCHLIST_PATH` | `data/dashboard/author_watchlist.json` |

Successful ingest triggers [Pages deploy](../../.github/workflows/pages.yml) via `workflow_run`.

---

## Pages export

[`.github/workflows/pages.yml`](../../.github/workflows/pages.yml) runs after ingest, on filtered pushes to `main`, daily at **14:00 UTC**, and manually.

Data source priority:

1. Committed `data/dashboard/heimdall.db`
2. GitHub secret `DASHBOARD_DATABASE_URL` (optional remote DB)
3. Fail if no DB (no mock seed)

Exports `web/public/data/snapshot.json`, appends `metrics_history.jsonl`, builds and deploys the site.

---

## Tracked files

| File | Updated by | Purpose |
| --- | --- | --- |
| `heimdall.db` | Ingest / manual publish | Source of truth for export |
| `x_rate_state.json` | Every X GraphQL call | Daily request counter |
| `x_keyword_rotation.json` | Scheduled ingest | Keyword cursor + search product index |
| `author_watchlist.json` | Ingest + maintenance | Authors for `from:handle` polls |
| `ingest_runs.jsonl` | Every ingest run | Keyword yield audit (rotation input) |
| `ingest_sightings.jsonl` | Ingest pipeline | Append-only sighting events |
| `metrics_history.jsonl` | Pages workflow | One JSON line per UTC day |
| `WATCHLIST.md` / `watchlist_state.json` | Daily analytics | Coordination tier tracking |
| `SENTIMENT_WATCHLIST.md` / `sentiment_watchlist_state.json` | Daily analytics | Sentiment trend / WoW alerts |
| `keyword_suggestions.json` | Weekly maintenance | Gap keywords from audit |
| `keyword_rotation_log.jsonl` | Weekly maintenance | Auto keyword swap audit |
| `theme_baseline.json` | Weekly maintenance | Theme drift comparison baseline |
| `briefs/` | Every export | Auto Markdown briefings (`INDEX.md` + per narrative) |

Mirrored for static hosting: `web/public/data/snapshot.json`, `web/public/data/briefs/`

[`data/scheduled_ingest.json`](../scheduled_ingest.json) is updated weekly when stale keywords are swapped.

---

## Keyword rotation

### Per-run (`explore_yield`)

Used by scheduled ingest when `rotation_strategy` is `explore_yield`:

1. Count runs per keyword in `ingest_runs.jsonl` (last 14 days).
2. If any keyword has **< 2 runs**, pick the least-run keyword(s).
3. Otherwise rotate through the **top 3 keywords by insert yield** (not always #1).

Other strategies: `yield` (pure yield rank), `round_robin` (sequential).

### Weekly auto-swap (`maintenance.yml`)

[`rotate_keywords.py`](../../scripts/rotate_keywords.py) + [`keyword_audit.py`](../../scripts/keyword_audit.py):

- Drops keywords with **0 yield after 3+ runs** (never unpins `2026 midterms`)
- Adds top gap suggestions from theme/corpus analysis
- Requires **≥ 5 ingest runs** in the 7-day window before swapping
- Logs changes to `keyword_rotation_log.jsonl`

---

## Author tree ingest

When `author_watch_enabled` is true in `scheduled_ingest.json`:

- Keyword searches register high-value authors in `author_watchlist.json`
- Every **2nd** scheduled run (`X_AUTHOR_POLL_EVERY_N=2`) polls one watched account via `from:handle (context terms…) since:…`
- Uses the same GraphQL budget as keyword search (1 request)
- Weekly maintenance prunes authors with 2+ polls and zero inserts

---

## Other workflows

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| [`ci.yml`](../../.github/workflows/ci.yml) | Push / PR | Ruff, pytest, web build, snapshot verify |
| [`export.yml`](../../.github/workflows/export.yml) | Manual | Re-export snapshot (optional auto-commit) |
| [`health.yml`](../../.github/workflows/health.yml) | Weekly Mon | Snapshot freshness, schema version |
| [`maintenance.yml`](../../.github/workflows/maintenance.yml) | Weekly Sun | VACUUM, rescore, theme drift, keyword swap, author prune |
| [`daily-analytics.yml`](../../.github/workflows/daily-analytics.yml) | Daily | Coordination + sentiment watchlists, GitHub issues |

---

## Maintenance commands

Remove test/mock narratives (keep production only):

```bash
python scripts/prune_narratives.py --keep midterms_2026
USE_EMBEDDING_THEMES=true python scripts/export_dashboard_data.py
```

Export locally without committing DB:

```bash
python scripts/export_dashboard_data.py
cd web && npm run build
```

Verify snapshot before push:

```bash
SNAPSHOT_SENTIMENT_STRICT=true python scripts/verify_snapshot.py
```
