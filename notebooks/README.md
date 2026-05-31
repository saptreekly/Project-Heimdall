# Notebooks

## `analyze_narrative.ipynb`

Loads persisted ingest data from `heimdall.db` and charts outrage / copypasta clusters.

### View on GitHub

GitHub’s built-in `.ipynb` preview often fails with a generic message (`Using nbformat v5.10.4 and nbconvert v7.17.1`) — a known platform issue, not your data.

**Reliable options:**

1. **Rendered HTML (recommended on GitHub)**  
   Open [analyze_narrative.html](analyze_narrative.html) in the repo (download or use [HTML preview](https://htmlpreview.github.io/?https://github.com/saptreekly/Project-Heimdall/blob/main/notebooks/analyze_narrative.html)).

2. **NBViewer**  
   https://nbviewer.org/github/saptreekly/Project-Heimdall/blob/main/notebooks/analyze_narrative.ipynb

3. **Local Jupyter**  
   `pip install -e ".[notebook]" && jupyter notebook notebooks/analyze_narrative.ipynb`

### Refresh GitHub artifacts after edits

```bash
python scripts/export_notebook_github.py
git add notebooks/analyze_narrative.ipynb notebooks/analyze_narrative.html
```
