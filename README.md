# Heimdall

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

`keywords` are subset names (`hate`, `offensive`, `stance_hillary`, …). No Twitter user IDs — IU astroturf overlap stays N/A.

## IU astroturf bot list

The file `data/astroturf.tsv` is **584 Twitter user IDs** labeled `political_Bot` from the [IU Bot Repository](https://botometer.osome.iu.edu/bot-repository/datasets.html). It auto-imports on startup (disable with `AUTO_IMPORT_ASTROTURF=false`).

```bash
curl -X POST http://127.0.0.1:8000/api/v1/datasets/astroturf/import
curl http://127.0.0.1:8000/api/v1/datasets/astroturf/stats
```

`/cib` responses include `iu_astroturf` overlap for **`platform=x` posts only**. Mastodon numeric account IDs are not Twitter IDs — overlap stays 0 until you ingest X/Twitter data.

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

Use a **research alt account** for cookies; ingest manually a few times per day—not on a tight cron.

Neo4j authors get `known_bot` and `bot_label` when matched.

## Configuration

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async Postgres (SQLAlchemy + asyncpg) |
| `REDDIT_*` | PRAW credentials for Reddit search |
| `X_AUTH_TOKEN` / `X_CT0` | Session cookies for `platform=x` ingest (aliases: `AUTH_TOKEN`, `CT0`) |
| `X_BEARER_TOKEN` | Reserved for official API v2 (not required for cookie ingest) |
| `X_MAX_*`, `X_MIN_*`, `X_INGEST_ENABLED` | X GraphQL guardrails (see table above) |
| `NEO4J_*` | Graph export via `POST /narratives/{id}/graph/neo4j` |
| `MASTODON_INSTANCE_URL` | Instance for hashtag timelines |
| `DEFAULT_INGESTER` | `hackernews`, `mastodon`, `mock`, etc. |

Install transformer-backed sentiment: `pip install -e ".[ml]"` and pass `OutrageAnalyzer(use_transformers=True)` in the pipeline.

## Legal & ethical use

Only collect **public** data in compliance with platform Terms of Service and applicable law. This scaffold is for research and defensive analysis—not for harassment, doxxing, or targeting individuals. Tune lexicons and thresholds with human review; automated CIB scores are **heuristic**, not ground truth.

## Analysis (Jupyter)

Ingest is **saved** to the app database (`heimdall.db` by default). Posts, outrage scores, edges, and narratives survive restarts.

```bash
pip install -e ".[notebook]"
jupyter notebook notebooks/analyze_narrative.ipynb
```

The notebook loads narratives from SQLite, plots outrage distributions, finds duplicate-text (copypasta) clusters, and lists repeat authors. Helpers live in `heimdall/analysis/`.

**GitHub preview:** GitHub’s renderer is picky about Python notebooks (nbformat 5 cell `id`s, large HTML tables). This repo keeps the notebook at **nbformat 4.4** with **PNG chart outputs** (like Julia notebooks). After local changes, refresh the GitHub view:

```bash
python scripts/export_notebook_github.py   # re-execute + strip HTML outputs
```

If GitHub’s `.ipynb` tab still shows `Using nbformat v5.10.4…`, open the rendered **[HTML notebook](notebooks/analyze_narrative.html)** or [nbviewer](https://nbviewer.org/github/saptreekly/Project-Heimdall/blob/main/notebooks/analyze_narrative.ipynb) instead (see [notebooks/README.md](notebooks/README.md)).

## Project layout

```
notebooks/
  analyze_narrative.ipynb
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
- [ ] Dashboard (e.g. React + sigma.js) fed from Neo4j or `/cib`
