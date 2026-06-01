# Heimdall

**Live dashboard:** [https://saptreekly.github.io/Project-Heimdall/](https://saptreekly.github.io/Project-Heimdall/)

> **Content notice:** This project may store and display real posts that include hate speech or other upsetting language, for research and accountability—not endorsement. Quoted material does not reflect the maintainer’s views. See the live dashboard header for the full notice.

Heimdall ingests public, unstructured social data around polarizing domestic narratives, scores **outrage escalation** with NLP, and builds **propagation graphs** to distinguish organic spread from coordinated inauthentic amplification (CIB).

## Architecture

```mermaid
flowchart LR
  subgraph ingest [Ingestion]
    API[FastAPI]
    RL[Rate Limiter]
    SRC[Reddit / Mock / X]
  end
  subgraph store [Storage]
    PG[(PostgreSQL)]
    N4[(Neo4j optional)]
  end
  subgraph analyze [Analysis]
    NLP[Outrage Index]
    NX[NetworkX CIB]
  end
  SRC --> RL --> API --> PG
  API --> NLP --> PG
  PG --> NX
  NX --> N4
```

| Layer | Role |
|-------|------|
| **Ingestion** | Async pipeline with token-bucket rate limiting, text normalization, upsert into Postgres |
| **NLP** | Lexicon + optional Hugging Face sentiment → outrage index, dehumanization, anti-authority signals |
| **Graph** | Author-level directed graph from shares/replies; density/hub/cluster heuristics for CIB |

## Quick start (no Docker)

Docker is optional. By default Heimdall uses a local **SQLite** file (`heimdall.db`) so you can run without Docker Desktop.

```bash
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # optional; SQLite is already the default
uvicorn heimdall.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API.

### Narrative analysis dashboard (TypeScript)

**Published:** [https://saptreekly.github.io/Project-Heimdall/](https://saptreekly.github.io/Project-Heimdall/) (GitHub Pages via `.github/workflows/pages.yml`).

The site ships a **bundled JSON snapshot** (`data/snapshot.json`) rebuilt on every deploy. CI runs daily (`cron: 0 14 * * *`) and on pushes to `main`.

**Ship your latest ingest to the repo and Pages:**

```bash
python scripts/publish_dashboard_data.py
git add data/dashboard/heimdall.db web/public/data/snapshot.json
git commit -m "chore: publish ingest data for dashboard"
git push
```

**Automated ingest** (`.github/workflows/ingest.yml`, **30× per day** every **48 minutes** UTC) pulls one rotated X keyword per run so the daily GraphQL budget (~30) is spread evenly across 24 hours. Config: `data/scheduled_ingest.json`. Add GitHub secrets **`AUTH_TOKEN`** and **`CT0`** (or `X_AUTH_TOKEN` / `X_CT0`).

Pages deploy runs after data is pushed (and daily 14:00 UTC).

Or set GitHub secret **`DASHBOARD_DATABASE_URL`**. If neither is present, CI seeds mock demo data.

The dashboard reads **`snapshot.json` only**; header links point at repo data on GitHub.

**Local preview:**

```bash
python scripts/publish_dashboard_data.py
cd web && npm install && npm run dev
```

Open http://127.0.0.1:5173 (deep link: `?narrative=3`)

**Optional:** `uvicorn heimdall.main:app` still serves ingest/API; after `npm run build` it can also serve `web/dist` at `/`.

### With Docker (Postgres + Redis + Neo4j)

Start **Docker Desktop** first (the error `docker.sock: no such file` means the daemon is not running). Then:

```bash
docker compose up -d
```

Set in `.env`:

```bash
DATABASE_URL=postgresql+asyncpg://heimdall:heimdall@localhost:5432/heimdall
```

### Example workflow

```bash
# Mock demo (bot cluster + share edges for CIB)
curl -s -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"narrative_name":"demo","keywords":["border"],"limit":20,"platform":"mock"}'

# Mastodon hashtag timeline (reblogs → share edges)
curl -s -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"narrative_name":"fed_politics","keywords":["immigration"],"limit":30,"platform":"mastodon"}'

# CIB assessment
curl http://localhost:8000/api/v1/narratives/1/cib

# Push graph to Neo4j (requires docker compose neo4j service)
curl -s -X POST "http://localhost:8000/api/v1/narratives/8/graph/neo4j?include_cib=true"
```

Open **http://localhost:7474** (login `neo4j` / `heimdallgraph`), paste the `sample_query` from the sync response, and run it.

## TweetEval (Hugging Face)

Benchmark tweets from [cardiffnlp/tweet_eval](https://huggingface.co/datasets/cardiffnlp/tweet_eval) for calibrating outrage scores against hate/offensive/stance labels.

```bash
pip install -e ".[hf]"

curl http://127.0.0.1:8000/api/v1/datasets/tweet_eval/subsets

curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"narrative_name":"te_hate_offensive","keywords":["hate","offensive"],"limit":100,"platform":"tweet_eval"}'

curl http://127.0.0.1:8000/api/v1/narratives/11/calibration
curl "http://127.0.0.1:8000/api/v1/narratives/11/posts?min_outrage=0.3"
```

`keywords` are subset names (`hate`, `offensive`, `stance_hillary`, …). No Twitter user IDs; IU astroturf overlap stays N/A.

## IU astroturf bot list

The file `data/astroturf.tsv` is **584 Twitter user IDs** labeled `political_Bot` from the [IU Bot Repository](https://botometer.osome.iu.edu/bot-repository/datasets.html). It auto-imports on startup (disable with `AUTO_IMPORT_ASTROTURF=false`).

```bash
curl -X POST http://127.0.0.1:8000/api/v1/datasets/astroturf/import
curl http://127.0.0.1:8000/api/v1/datasets/astroturf/stats
```

`/cib` responses include `iu_astroturf` overlap for **`platform=x` posts only**. Mastodon numeric account IDs are not Twitter IDs; overlap stays 0 until you ingest X/Twitter data.

### X / Twitter (session cookies)

Copy `auth_token` and `ct0` from browser devtools (Application → Cookies for `x.com`) into `.env`:

```bash
X_AUTH_TOKEN=your_auth_token
X_CT0=your_ct0
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"narrative_name":"x_border","keywords":["border crisis"],"limit":40,"platform":"x"}'

# List timeline instead of search:
# "keywords": ["list:1234567890123456789"]
```

After ingest, `GET /api/v1/narratives/{id}/cib` can report IU astroturf overlap on `platform=x` author IDs.

**Ban-risk guardrails** (defaults are conservative; tune in `.env`):

| Limit | Default | Purpose |
|-------|---------|---------|
| `X_MAX_KEYWORDS_PER_INGEST` | 5 | Cap searches per request |
| `X_MAX_POSTS_PER_INGEST` | 80 | Cap tweets stored per ingest |
| `X_MAX_TWEETS_PER_SEARCH` | 20 | Cap tweets per GraphQL call |
| `X_MIN_SECONDS_BETWEEN_SEARCHES` | 3 | Pause between keyword/list pulls |
| `X_MAX_GRAPHQL_REQUESTS_PER_DAY` | 30 | Daily budget (tracked in `data/x_rate_state.json`) |
| `X_INGEST_ENABLED` | true | Kill switch (`false` blocks all X ingest) |

Check today's usage: `GET /api/v1/platforms/x/usage`. Ingest responses include a `guardrails` object when limits were applied.

Use a **research alt account** for cookies. Scheduled CI rotates keywords (`X_SCHEDULED_KEYWORDS_PER_RUN=1`) to stay within the daily GraphQL cap.

Neo4j authors get `known_bot` and `bot_label` when matched.

## Configuration

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async Postgres (SQLAlchemy + asyncpg) |
| `REDDIT_*` | PRAW credentials for Reddit search |
| `X_AUTH_TOKEN` / `X_CT0` | Session cookies for `platform=x` ingest (aliases: `AUTH_TOKEN`, `CT0`) |
| `X_BEARER_TOKEN` | Reserved for official API v2 (not required for cookie ingest) |
| `X_MAX_*`, `X_MIN_*`, `X_INGEST_ENABLED` | X GraphQL guardrails (see table above) |
| `X_RATE_STATE_PATH` | Daily GraphQL counter file (CI: `data/dashboard/x_rate_state.json`) |
| `NEO4J_*` | Graph export via `POST /narratives/{id}/graph/neo4j` |
| `MASTODON_INSTANCE_URL` | Instance for hashtag timelines |
| `DEFAULT_INGESTER` | `hackernews`, `mastodon`, `mock`, etc. |

Theme clustering: set `USE_EMBEDDING_THEMES=true` when exporting the dashboard snapshot. Base install uses **TF-IDF + DBSCAN/KMeans** when neural embeddings are unavailable; `pip install -e ".[ml]"` (Python 3.11–3.12) adds **sentence-transformers** (`all-MiniLM-L6-v2`). CI enables themes automatically. API: `GET /api/v1/narratives/{id}/themes`.

## Legal & ethical use

Only collect **public** data in compliance with platform Terms of Service and applicable law. This scaffold is for research and defensive analysis, not for harassment, doxxing, or targeting individuals. Tune lexicons and thresholds with human review; automated CIB scores are **heuristic**, not ground truth.

## Analysis

Ingest is **saved** to the app database (`heimdall.db` by default). Posts, outrage scores, edges, and narratives survive restarts.

Use the TypeScript dashboard in `web/` (see [Narrative analysis dashboard](#narrative-analysis-dashboard-typescript)). It loads committed `snapshot.json` only (no live API).

Duplicate-text detection and pandas loaders live in `heimdall/analysis/`.

## Project layout

```
web/                   # Vite + TypeScript analysis UI (GitHub Pages)
heimdall/
  analysis/            # pandas loaders, duplicate-text detection
  main.py              # FastAPI app
  api/routes.py        # REST endpoints
  ingestion/           # Platform ingesters, rate limit, pipeline
  nlp/outrage.py       # Outrage index
  graph/               # NetworkX analysis, Neo4j sync
  db/models.py         # Narratives, posts, edges, scores
tests/
```

## Next steps

- [x] X/Twitter ingester (GraphQL search + list timelines; retweet → SHARE edges)
- [ ] Bot detection features (account age, posting velocity) as graph node attributes
- [x] Narrative analysis dashboard (`web/`, static snapshot from repo data)
- [ ] Graph visualization (e.g. sigma.js) fed from Neo4j or propagation edges
