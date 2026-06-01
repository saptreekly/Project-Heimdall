# Reference datasets

## astroturf.tsv (Indiana University Bot Repository)

- **Source:** [Bot Repository](https://botometer.osome.iu.edu/bot-repository/datasets.html): astroturf campaign list
- **Format:** tab-separated `twitter_user_id` + `political_Bot` (no header)
- **Rows:** ~584 known political bot accounts (Twitter/X numeric IDs)
- **Use in Heimdall:** ground-truth bot labels for author lookup, CIB validation, Neo4j styling

Extract from archive:

```bash
tar -xzf ~/Downloads/astroturf.tar.gz -C data/
```

Import into the API DB:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/datasets/astroturf/import
```
