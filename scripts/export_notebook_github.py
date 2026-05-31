#!/usr/bin/env python3
"""Produce a GitHub-compatible .ipynb plus static HTML for reliable viewing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "analyze_narrative.ipynb"
HTML_OUT = ROOT / "notebooks" / "analyze_narrative.html"
DB = ROOT / "heimdall.db"


def _clean_metadata(nb) -> None:
    """GitHub nbconvert fails when metadata.widgets exists without state (common Jupyter/VS Code bug)."""
    widgets = nb.metadata.get("widgets")
    if widgets is None:
        return
    if "state" not in widgets:
        nb.metadata["widgets"] = {
            **widgets,
            "state": {},
            "version_major": widgets.get("version_major", 2),
            "version_minor": widgets.get("version_minor", 0),
        }


def _strip_cell_outputs(cell) -> None:
    kept = []
    for out in cell.outputs:
        otype = out.output_type
        if otype == "stream":
            text = out.text if isinstance(out.text, str) else "".join(out.text)
            if len(text) > 6000:
                out.text = text[:6000] + "\n… (truncated)\n"
            kept.append(out)
        elif otype == "display_data" and "image/png" in out.data:
            out.data = {"image/png": out.data["image/png"]}
            out.metadata = {}
            kept.append(out)
        elif otype == "execute_result":
            if "text/html" in out.data:
                continue
            plain = out.data.get("text/plain", "")
            if isinstance(plain, list):
                plain = "".join(plain)
            if "<Figure size" in plain or len(plain) >= 4000:
                continue
            out.data = {"text/plain": plain}
            kept.append(out)
    cell.outputs = kept


def _clean_cells(nb) -> None:
    for cell in nb.cells:
        cell.metadata.pop("execution", None)
        if cell.cell_type != "code":
            if "outputs" in cell:
                del cell["outputs"]
            if "execution_count" in cell:
                del cell["execution_count"]
            continue
        _strip_cell_outputs(cell)


def main() -> int:
    import nbformat
    from nbconvert import HTMLExporter
    from nbconvert.preprocessors import ExecutePreprocessor

    nb = nbformat.read(NOTEBOOK, as_version=4)

    if DB.exists():
        ep = ExecutePreprocessor(timeout=120, kernel_name="python3")
        ep.preprocess(nb, {"metadata": {"path": str(ROOT)}})
    else:
        print("No heimdall.db — skipping execute; cleaning format only.", file=sys.stderr)

    _clean_cells(nb)
    _clean_metadata(nb)

    nb.nbformat = 4
    nb.nbformat_minor = 4
    for cell in nb.cells:
        if hasattr(cell, "id"):
            del cell["id"]

    nbformat.validate(nb)
    nbformat.write(nb, NOTEBOOK)

    html, _ = HTMLExporter().from_notebook_node(nb)
    HTML_OUT.write_text(html, encoding="utf-8")

    print(f"Wrote {NOTEBOOK}")
    print(f"Wrote {HTML_OUT}")
    print("GitHub preview: open the .html file or use nbviewer (see notebooks/README.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
