# Notebooks

## `analyze_narrative.ipynb`

Loads persisted ingest data from `heimdall.db` and charts outrage / copypasta clusters.

### How we commit it (same idea as Julia notebooks)

The checked-in `.ipynb` is **pre-rendered for GitHub**:

- **PNG charts** (`%matplotlib inline`) — not `<Figure size…>` text
- **nbformat 4.4**, no cell `id`s, no `metadata.widgets`
- **No HTML** table outputs from pandas (text only)

Generate that artifact before you commit:

```bash
pip install -e ".[notebook]"
python scripts/export_notebook_github.py   # needs heimdall.db to refresh charts
git add notebooks/analyze_narrative.ipynb
```

`analyze_narrative.html` is an optional static copy for browsers; the `.ipynb` with PNGs is the primary artifact.

### If GitHub’s `.ipynb` tab still errors

GitHub sometimes shows only `Using nbformat v5.10.4 and nbconvert v7.17.1` during **platform outages** — not much a repo can do. Fallbacks: [nbviewer](https://nbviewer.org/github/saptreekly/Project-Heimdall/blob/main/notebooks/analyze_narrative.ipynb) or open `analyze_narrative.html`.

CI (`.github/workflows/notebooks.yml`) re-sanitizes the notebook on push so a local Jupyter save doesn’t re-introduce broken widgets metadata.
