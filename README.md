# Heimdall

**Live dashboard:** [https://saptreekly.github.io/Project-Heimdall/](https://saptreekly.github.io/Project-Heimdall/)

> **Content notice:** This project may store and display real posts that include hate speech or other upsetting language, for research and accountability—not endorsement. Quoted material does not reflect the maintainer’s views. See the live dashboard header for the full notice.

Heimdall ingests public social text around polarizing domestic narratives, scores **outrage escalation** with NLP, clusters **emerging themes**, and builds **propagation graphs** to distinguish organic spread from coordinated inauthentic amplification (CIB).

Production tracking today centers on the **`midterms_2026`** narrative (X search ingest with Mastodon/Hacker News fallbacks).

---

## What you get

| Layer | What it does |
| --- | --- |
| **Ingest** | Async pipeline from X, Reddit, Mastodon, Hacker News, mock, or TweetEval → SQLite/Postgres |
| **NLP** | Lexicon v2.4 outrage index, escalation tiers, optional twitter-roberta sentiment |
| **Themes** | TF-IDF or sentence-transformer clustering (DBSCAN/KMeans) on export |
| **Graph** | Author-level directed graph (shares/replies); NetworkX CIB heuristics |
| **Coordination** | Near-duplicate clusters, fuzzy Jaccard frames, cross-pollination actors, ingest sightings |
| **Dashboard** | Static TypeScript SPA on GitHub Pages — Pulse, Frames, Evidence, Network + auto briefs |
| **Automation** | Scheduled ingest, watchlists, keyword rotation, daily/weekly CI maintenance |

The public site reads a **bundled JSON snapshot** only (`web/public/data/snapshot.json`). The FastAPI backend is for local ingest, rescore, and research workflows.

---

## Architecture

```mermaid
flowchart TB
  classDef source fill:#dbeafe,stroke:#2563eb,color:#1e3a8a,stroke-width:2px
  classDef guard fill:#ffedd5,stroke:#ea580c,color:#7c2d12,stroke-width:2px
  classDef orch fill:#ede9fe,stroke:#7c3aed,color:#4c1d95,stroke-width:2px
  classDef pipe fill:#f3e8ff,stroke:#9333ea,color:#581c87,stroke-width:1px
  classDef store fill:#dcfce7,stroke:#16a34a,color:#14532d,stroke-width:2px
  classDef analyze fill:#fce7f3,stroke:#db2777,color:#831843,stroke-width:2px
  classDef artifact fill:#fef3c7,stroke:#d97706,color:#78350f,stroke-width:2px
  classDef ui fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e,stroke-width:2px
  classDef ci fill:#f1f5f9,stroke:#475569,color:#0f172a,stroke-width:2px
  classDef optional fill:#f8fafc,stroke:#94a3b8,color:#475569,stroke-dasharray:6 4

  subgraph L0["① External sources"]
    direction LR
    SX(("X / Twitter<br/>GraphQL search"))
    SFB["Fallback platforms<br/>Mastodon · Reddit · HN"]
    SMOCK["Mock · TweetEval"]
    SREF["IU astroturf.tsv<br/>bot ground truth"]
  end

  subgraph L1["② CI orchestration · GitHub Actions"]
    direction LR
    CING["ingest.yml<br/>~30 runs / 24h"]
    CPAGE["pages.yml<br/>build + deploy"]
    CMAINT["maintenance.yml<br/>weekly rescore · keywords"]
    CDAILY["daily-analytics<br/>watchlist issues"]
    CCFG[/"scheduled_ingest.json<br/>midterms_2026 · limit 60"/]
  end

  subgraph L2["③ Ingest scheduling · per run"]
    direction TB
    ROT{{explore_yield<br/>under-sampled → top pool}}
    PROD{{Search product<br/>Latest ↔ Top}}
    AUTHW["Author watchlist<br/>every 2nd run: from:handle"]
    SCHED[["scheduled_ingest.py"]]
  end

  subgraph L3["④ X guardrails"]
    direction LR
    BUDGET["Daily GraphQL cap · 45"]
    RLIM["Rate limit · page-2 cursor"]
    XSTATE[("x_rate_state.json<br/>x_keyword_rotation.json")]
  end

  subgraph L4["⑤ IngestionPipeline"]
    direction TB
    PLAN["Query plan · exclude terms"]
    FETCH["Platform ingesters"]
    CLEAN["Normalize · keyword filter"]
    DEDUP["Dedupe in DB<br/>duplicates = coordination signal"]
    OUTR["Outrage lexicon v2.4<br/>escalation tier · polarity"]
    GRAPH["Propagation edges<br/>share · reply · retweet"]
    SIGHT["ingest_sightings.jsonl"]
  end

  subgraph L5["⑥ Persistent layer"]
    direction LR
    DB[("heimdall.db<br/>posts · scores · edges · narratives")]
    AUDIT[("Audit & state<br/>ingest_runs.jsonl<br/>author_watchlist.json")]
  end

  subgraph L6["⑦ Rescore · export · enrich"]
    direction TB
    RESCORE["rescore_dashboard_narratives<br/>if stale"]
    THEMES["Theme clusters<br/>TF-IDF · MiniLM embeddings"]
    COORD["Coordination layer<br/>near-dup · fuzzy Jaccard · CIB overlay"]
    SNAPSHOT["build_dashboard_snapshot"]
    BRIEFGEN["write_brief_artifacts"]
  end

  subgraph L7["⑧ Published artifacts"]
    direction LR
    SNAP[/"web/public/data/snapshot.json"/]
    BRIEFS[/"briefs/*.md + INDEX"/]
    METRICS[/"metrics_history.jsonl"/]
    WATCH[/"WATCHLIST · SENTIMENT_WATCHLIST"/]
  end

  subgraph L8["⑨ Consumers"]
    direction LR
    FASTAPI["FastAPI /api/v1<br/>ingest · CIB · rescore · Neo4j"]
    DESK["GitHub Pages SPA"]
    PULSE["Pulse"]
    FRAMES["Frames"]
    EVID["Evidence"]
    NET["Network · vis-network"]
    NEO4(("Neo4j<br/>optional"))
  end

  %% Source → guard → schedule
  SX --> BUDGET
  SFB --> SCHED
  SMOCK --> SCHED
  SREF -.-> DB

  %% CI triggers
  CING --> SCHED
  CCFG --> ROT
  CCFG --> AUTHW
  CING --> SNAPSHOT
  CPAGE --> SNAP
  CMAINT --> CCFG
  CMAINT --> RESCORE
  CDAILY --> WATCH

  %% Scheduling internals
  ROT --> SCHED
  PROD --> SCHED
  AUTHW --> SCHED
  BUDGET --> SCHED
  RLIM --> FETCH
  XSTATE --- BUDGET
  SCHED --> PLAN

  %% Pipeline
  PLAN --> FETCH --> CLEAN --> DEDUP --> OUTR --> GRAPH --> DB
  CLEAN --> SIGHT --> AUDIT
  SCHED --> AUDIT

  %% Storage → analysis
  DB --> RESCORE --> THEMES
  DB --> COORD
  THEMES --> SNAPSHOT
  COORD --> SNAPSHOT
  SNAPSHOT --> SNAP
  SNAPSHOT --> BRIEFGEN --> BRIEFS
  SNAP --> METRICS

  %% Artifacts → UI
  SNAP --> DESK
  BRIEFS --> DESK
  WATCH -.-> DESK
  DB --> FASTAPI
  DESK --> PULSE & FRAMES & EVID & NET
  GRAPH -.-> NEO4
  FASTAPI -.-> NEO4

  %% Feedback loops
  AUDIT -.->|"yield stats"| ROT
  AUDIT -.->|"keyword audit"| CCFG
  METRICS -.-> CMAINT

  class SX,SFB,SMOCK,SREF source
  class BUDGET,RLIM,XSTATE guard
  class ROT,PROD,AUTHW,SCHED orch
  class PLAN,FETCH,CLEAN,DEDUP,OUTR,GRAPH,SIGHT pipe
  class DB,AUDIT store
  class RESCORE,THEMES,COORD,SNAPSHOT,BRIEFGEN analyze
  class SNAP,BRIEFS,METRICS,WATCH artifact
  class FASTAPI,DESK,PULSE,FRAMES,EVID,NET ui
  class CING,CPAGE,CMAINT,CDAILY,CCFG ci
  class NEO4 optional

  linkStyle 38,39,40,41,42 stroke:#db2777,stroke-width:2px
  linkStyle 43,44,45 stroke:#0284c7,stroke-width:3px
  linkStyle 46,47,48 stroke:#94a3b8,stroke-dasharray:6 4
```

**Flow summary:** cron ingest selects a keyword + search product under guardrails → pipeline writes posts, scores, and edges to SQLite → export rescores, clusters themes, builds coordination overlays → snapshot and briefs deploy to GitHub Pages. Audit logs and watchlists feed weekly keyword rotation and daily alert workflows.

| Component | Default | Notes |
| --- | --- | --- |
| Database | SQLite `heimdall.db` | CI commits `data/dashboard/heimdall.db` |
| Redis | Configured | Not used by application code today |
| Neo4j | Optional via Docker | Graph export from FastAPI only |
| Snapshot | `web/public/data/snapshot.json` | Rebuilt on every ingest/export CI run |

---

## Quick start

### Backend (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # optional; SQLite is the default
uvicorn heimdall.main:app --reload
```

- API docs: http://127.0.0.1:8000/docs  
- All routes are under `/api/v1`

### Dashboard (local preview)

```bash
pip install -e ".[ml]"   # optional; enables sentence-transformer themes on export
python scripts/publish_dashboard_data.py

cd web && npm install && npm run dev
```

Open http://127.0.0.1:5173 — deep links:

| Param | Example | Purpose |
| --- | --- | --- |
| `narrative` | `?narrative=1` | Narrative ID (IDs are DB-specific) |
| `tab` | `?tab=brief` | `analysis` (Desk), `brief`, `methodology` |
| `mode` | `?mode=network` | Desk: `pulse`, `frames`, `evidence`, `network` |

After `npm run build`, FastAPI can also serve `web/dist` at `/` when present.

### Docker (Postgres + Redis + Neo4j)

Start Docker Desktop, then:

```bash
docker compose up -d
```

Set in `.env`:

```bash
DATABASE_URL=postgresql+asyncpg://heimdall:heimdall@localhost:5432/heimdall
```

---

## Dashboard

The analysis UI lives in [`web/`](web/). See [`web/README.md`](web/README.md) for UI structure.

**Desk modes**

| Mode | Focus |
| --- | --- |
| **Pulse** | Volume, outrage distribution, alerts, sentiment watchlist hooks |
| **Frames** | Theme clusters, coordination overlays, tier labels |
| **Evidence** | Post stream, filters, duplicate/coordination inspector |
| **Network** | Propagation graph (vis-network), fuzzy duplicates, cross-pollination |

**Briefing tab** loads precomputed Markdown from `web/public/data/briefs/` (generated on export).

**Publishing data to GitHub Pages**

```bash
python scripts/publish_dashboard_data.py
git add data/dashboard/heimdall.db web/public/data/snapshot.json web/public/data/briefs
git commit -m "chore: publish ingest data for dashboard"
git push
```

Operator details: [`data/dashboard/README.md`](data/dashboard/README.md)

---

## Scheduled ingest (CI)

GitHub Actions workflow [`.github/workflows/ingest.yml`](.github/workflows/ingest.yml) runs **~30 times per day** (five staggered cron blocks). Each run:

1. Picks **one keyword** (`X_SCHEDULED_KEYWORDS_PER_RUN=1`)
2. Alternates X search product **Latest ↔ Top**
3. Respects daily GraphQL budget (default **45** requests)
4. Commits DB, rate/rotation state, snapshot, briefs, ingest log

**Secrets required:** `AUTH_TOKEN` and `CT0` (aliases: `X_AUTH_TOKEN`, `X_CT0`)

**Config:** [`data/scheduled_ingest.json`](data/scheduled_ingest.json)

| Field | Current value |
| --- | --- |
| Narrative | `midterms_2026` |
| Platform | `x` (fallbacks: mastodon, hackernews) |
| Keywords | 7 phrases (e.g. `2026 midterms`, `2026 election integrity`, …) |
| `rotation_strategy` | `explore_yield` — under-sampled keywords first, then rotate top-yield pool |
| `limit` | 60 posts per run |
| `author_watch_enabled` | Every 2nd run polls a watched author via `from:handle` |

**Keyword selection (`explore_yield`)**

1. Keywords with **< 2 runs** in the last 14 days are prioritized (exploration).
2. Once all keywords are sampled, rotate through the **top 3 by insert yield** instead of always picking #1.

**Search product rotation:** `Latest` and `Top` alternate per run (state in `data/dashboard/x_keyword_rotation.json`).

**Weekly keyword maintenance** ([`maintenance.yml`](.github/workflows/maintenance.yml)): drops stale zero-yield keywords (never unpins `2026 midterms`), adds gap suggestions from [`keyword_audit.py`](scripts/keyword_audit.py).

Run ingest locally (needs X cookies in `.env`):

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/dashboard/heimdall.db \
  X_RATE_STATE_PATH=data/dashboard/x_rate_state.json \
  X_ROTATION_STATE_PATH=data/dashboard/x_keyword_rotation.json \
  X_SCHEDULED_KEYWORDS_PER_RUN=1 \
  python scripts/scheduled_ingest.py
```

---

## X / Twitter ingest

Session cookies from browser devtools (Application → Cookies for `x.com`):

```bash
X_AUTH_TOKEN=your_auth_token
X_CT0=your_ct0
```

Manual API ingest:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"narrative_name":"x_test","keywords":["2026 midterms"],"limit":40,"platform":"x"}'

# List timeline instead of search:
# "keywords": ["list:1234567890123456789"]
```

Check daily budget: `GET /api/v1/platforms/x/usage`

**Guardrails** (defaults; tune in `.env`):

| Variable | Default | Purpose |
| --- | ---: | --- |
| `X_MAX_KEYWORDS_PER_INGEST` | 8 | Max searches per request |
| `X_MAX_POSTS_PER_INGEST` | 80 | Max tweets stored per ingest |
| `X_MAX_TWEETS_PER_SEARCH` | 20 | Max tweets per GraphQL call |
| `X_MIN_SECONDS_BETWEEN_SEARCHES` | 3 | Pause between keyword/list pulls |
| `X_MAX_GRAPHQL_REQUESTS_PER_DAY` | 45 | Daily budget (`data/dashboard/x_rate_state.json` in CI) |
| `X_INGEST_ENABLED` | true | Kill switch |

Use a **research alt account** for cookies. Ingest responses include a `guardrails` object when limits apply.

After X ingest, `GET /api/v1/narratives/{id}/cib` can report IU astroturf overlap on `platform=x` author IDs.

---

## Example API workflow

```bash
# Mock demo (bot cluster + share edges for CIB)
curl -s -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"narrative_name":"demo","keywords":["border"],"limit":20,"platform":"mock"}'

curl http://127.0.0.1:8000/api/v1/narratives/1/cib

# Mastodon hashtag timeline
curl -s -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"narrative_name":"fed_politics","keywords":["immigration"],"limit":30,"platform":"mastodon"}'

# Push graph to Neo4j (requires docker compose neo4j service)
curl -s -X POST "http://127.0.0.1:8000/api/v1/narratives/1/graph/neo4j?include_cib=true"
```

### API reference

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health check |
| GET/POST | `/narratives` | List / create narratives |
| POST | `/ingest/preview` | Dry-run ingest plan |
| POST | `/ingest` | Run ingest |
| GET | `/platforms/x/usage` | X daily GraphQL budget |
| GET | `/narratives/{id}/posts` | Posts (filters: min_outrage, platform, …) |
| GET | `/narratives/{id}/amplification` | Amplification report |
| GET | `/narratives/{id}/cib` | CIB assessment |
| GET | `/cross-pollination` | Global cross-narrative actors |
| GET | `/narratives/{id}/cross-pollination` | Per-narrative hits |
| GET | `/narratives/{id}/themes` | Theme clusters |
| GET | `/narratives/{id}/sentiment-shift` | Sentiment divergence / WoW |
| POST | `/narratives/{id}/rescore` | Rescore narrative |
| POST | `/datasets/astroturf/import` | Import IU bot list |
| GET | `/datasets/astroturf/stats` | Bot list stats |
| GET | `/datasets/tweet_eval/subsets` | TweetEval subset list |
| GET | `/narratives/{id}/calibration` | TweetEval calibration |
| GET | `/benchmarks/tweet-eval` | Offline benchmark |
| POST | `/narratives/{id}/graph/neo4j` | Push graph to Neo4j |

---

## Reference datasets

### IU astroturf bot list

[`data/astroturf.tsv`](data/astroturf.tsv) — ~584 Twitter user IDs labeled `political_Bot` from the [IU Bot Repository](https://botometer.osome.iu.edu/bot-repository/datasets.html). Auto-imports on startup (`AUTO_IMPORT_ASTROTURF=true`).

See [`data/README.md`](data/README.md) for format and import commands.

### TweetEval (Hugging Face)

Benchmark tweets from [cardiffnlp/tweet_eval](https://huggingface.co/datasets/cardiffnlp/tweet_eval) for calibrating outrage scores.

```bash
pip install -e ".[hf]"

curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"narrative_name":"te_hate_offensive","keywords":["hate","offensive"],"limit":100,"platform":"tweet_eval"}'

curl http://127.0.0.1:8000/api/v1/narratives/{id}/calibration
```

`keywords` are subset names (`hate`, `offensive`, `stance_hillary`, …). No Twitter user IDs.

---

## CI/CD

| Workflow | When | What |
| --- | --- | --- |
| [**ci**](.github/workflows/ci.yml) | Push / PR to `main` | Ruff, pytest, web build, snapshot verify, export regression |
| [**ingest**](.github/workflows/ingest.yml) | ~30×/day + manual | X scheduled ingest → commit DB + snapshot + briefs |
| [**pages**](.github/workflows/pages.yml) | After ingest, push (filtered paths), daily 14:00 UTC | Export snapshot, metrics history, deploy GitHub Pages |
| [**export-dashboard**](.github/workflows/export.yml) | Manual | Re-export snapshot from committed DB |
| [**health**](.github/workflows/health.yml) | Weekly Mon + manual | Snapshot age, schema version, metrics |
| [**maintenance**](.github/workflows/maintenance.yml) | Weekly Sun + manual | VACUUM, rescore, theme drift, keyword audit + swap, author prune, TweetEval benchmark |
| [**daily-analytics**](.github/workflows/daily-analytics.yml) | Daily 15:30 UTC | Coordination + sentiment watchlists; opens GitHub issues on tier crossings |

**Chain:** ingest commits data → `workflow_run` triggers pages deploy.

**CI theme clustering:** `USE_EMBEDDING_THEMES=true` with `USE_NEURAL_EMBEDDINGS=false` (TF-IDF fallback in CI to avoid Hugging Face rate limits). Local dev can set `USE_NEURAL_EMBEDDINGS=true` with `pip install -e ".[ml]"`.

**Optional secret:** `DASHBOARD_DATABASE_URL` — remote DB fallback for Pages export when committed SQLite is absent.

Dependabot (`.github/dependabot.yml`) opens weekly PRs for GitHub Actions and npm.

---

## Configuration

Full template: [`.env.example`](.env.example). Source of truth: [`heimdall/config.py`](heimdall/config.py).

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Async SQLAlchemy URL (SQLite default) |
| `CORS_ORIGINS` | Comma-separated origins for FastAPI CORS |
| `REDDIT_*` | PRAW credentials |
| `X_AUTH_TOKEN` / `X_CT0` | Session cookies (`AUTH_TOKEN`, `CT0` aliases) |
| `X_MAX_*`, `X_MIN_*`, `X_INGEST_ENABLED` | X GraphQL guardrails |
| `X_RATE_STATE_PATH` | Daily GraphQL counter file |
| `X_AUTHOR_POLL_*`, `X_AUTHOR_WATCHLIST_*` | Author tree snowball ingest |
| `X_SCHEDULED_KEYWORDS_PER_RUN` | Keywords per scheduled run (CI: `1`) |
| `X_ROTATION_STATE_PATH` | Keyword + search-product rotation state (CI path in ingest workflow) |
| `NEO4J_*` | Graph export |
| `MASTODON_INSTANCE_URL` | Mastodon instance |
| `DEFAULT_INGESTER` | Default platform when omitted |
| `USE_EMBEDDING_THEMES` | Theme clustering on export |
| `USE_NEURAL_EMBEDDINGS` | Sentence-transformers vs TF-IDF themes |
| `RESCORE_BEFORE_EXPORT` | Rescore stale posts before snapshot |
| `RESCORE_USE_EMBEDDINGS` | Include embed theme boosts on rescore |
| `USE_TRANSFORMER_SENTIMENT` | Optional twitter-roberta polarity (`.[ml-hf]`) |
| `SNAPSHOT_SENTIMENT_STRICT` | Fail verify if sentiment fields missing (CI: true) |
| `AUTO_IMPORT_ASTROTURF` | Import IU bot list on startup |

---

## Development

### Project layout

```
web/                      # Vite + TypeScript dashboard (GitHub Pages)
  public/data/            # snapshot.json, briefs/ (deployed assets)
heimdall/
  api/                    # FastAPI routes
  ingestion/              # Platform ingesters, X guard, pipeline, author watchlist
  nlp/                    # Outrage, themes, embeddings
  graph/                  # NetworkX, Neo4j sync
  analysis/               # CIB, duplicates, coordination, sentiment shift
  export/                 # Snapshot, briefs, coordination overlay
  db/                     # SQLAlchemy models
scripts/                  # Ingest, export, watchlists, maintenance (see below)
data/
  dashboard/              # Committed CI database + analytics state
  scheduled_ingest.json     # Cron job definitions
tests/
.github/workflows/        # CI/CD
```

### Scripts

| Script | Purpose |
| --- | --- |
| `scheduled_ingest.py` | CI/cron ingest from `scheduled_ingest.json` |
| `publish_dashboard_data.py` | Copy root DB → `data/dashboard/` + export |
| `export_dashboard_data.py` | Build snapshot + briefs |
| `verify_snapshot.py` | CI snapshot schema/freshness gate |
| `coordination_watchlist.py` | Daily coordination tier tracking |
| `sentiment_watchlist.py` | Daily sentiment trend alerts |
| `rotate_keywords.py` / `keyword_audit.py` | Weekly keyword swap + gap discovery |
| `maintain_dashboard_db.py` | SQLite VACUUM, orphan cleanup |
| `prune_author_watchlist.py` | Remove low-yield watched authors |
| `rescore_dashboard_narratives.py` | Rescore all narratives |
| `benchmark_outrage.py` | TweetEval outrage benchmark |

Run `python scripts/verify_automation_setup.py` to validate workflow ↔ script wiring.

### Tests

```bash
pip install -e ".[ml,dev]"
ruff check heimdall tests scripts
pytest -q

cd web && npm ci && VITE_BASE=/Project-Heimdall/ npm run build

python scripts/verify_snapshot.py
SNAPSHOT_SENTIMENT_STRICT=true python scripts/verify_snapshot.py
```

---

## Legal & ethical use

Only collect **public** data in compliance with platform Terms of Service and applicable law. This scaffold is for research and defensive analysis, not for harassment, doxxing, or targeting individuals. Tune lexicons and thresholds with human review; automated CIB scores are **heuristic**, not ground truth.

---

## Roadmap

- [x] X/Twitter ingester (GraphQL search + list timelines; retweet → SHARE edges)
- [x] Narrative analysis dashboard (`web/`, static snapshot)
- [x] Propagation graph visualization (vis-network)
- [x] Auto briefs, coordination overlays, watchlists, keyword rotation
- [ ] Bot detection features (account age, posting velocity) as graph node attributes
- [ ] Official X API v2 bearer integration (reserved)
