# Reference datasets

Static files used by ingest, CIB validation, and benchmarks. Not generated at runtime.

---

## astroturf.tsv (Indiana University Bot Repository)

| | |
| --- | --- |
| **Source** | [IU Bot Repository](https://botometer.osome.iu.edu/bot-repository/datasets.html) astroturf campaign list |
| **Format** | Tab-separated `twitter_user_id` + `political_Bot` (no header) |
| **Rows** | ~584 known political bot accounts (Twitter/X numeric IDs) |
| **Config** | `ASTROTURF_TSV_PATH=data/astroturf.tsv`, `AUTO_IMPORT_ASTROTURF=true` |

**Use in Heimdall:** ground-truth bot labels for author lookup, CIB overlap on `platform=x` posts, Neo4j `known_bot` styling.

Extract from archive:

```bash
tar -xzf ~/Downloads/astroturf.tar.gz -C data/
```

Import via API:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/datasets/astroturf/import
curl http://127.0.0.1:8000/api/v1/datasets/astroturf/stats
```

Mastodon numeric account IDs are not Twitter IDs; overlap stays 0 until you ingest X data.

---

## scheduled_ingest.json

Cron job definitions for [`scripts/scheduled_ingest.py`](../scripts/scheduled_ingest.py). See root [README](../README.md#scheduled-ingest-ci) and [`dashboard/README.md`](dashboard/README.md).

---

## dashboard/

Committed CI database, analytics state, watchlists, and export inputs. See [`dashboard/README.md`](dashboard/README.md).
