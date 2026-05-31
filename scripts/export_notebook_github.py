#!/usr/bin/env python3
"""Produce a GitHub-compatible .ipynb plus static HTML for reliable viewing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "analyze_narrative.ipynb"
HTML_OUT = ROOT / "notebooks" / "analyze_narrative.html"
DB = ROOT / "heimdall.db"


def _clean_metadata(nb) -> None:
    """GitHub nbconvert fails when metadata.widgets lacks state (VS Code / Jupyter bug)."""
    widgets = nb.metadata.get("widgets")
    if widgets is None:
        return
    if "state" not in widgets:
        # Remove broken widgets block; GitHub's renderer rejects it (see community #155944).
        nb.metadata.pop("widgets", None)


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


def sanitize_notebook(nb, *, execute: bool) -> None:
    import nbformat
    from nbconvert.preprocessors import ExecutePreprocessor

    if execute and DB.exists():
        ep = ExecutePreprocessor(timeout=120, kernel_name="python3")
        ep.preprocess(nb, {"metadata": {"path": str(ROOT)}})
    elif execute:
        print("No heimdall.db — skipping execute.", file=sys.stderr)

    _clean_cells(nb)
    _clean_metadata(nb)
    nb.nbformat = 4
    nb.nbformat_minor = 4
    for cell in nb.cells:
        if hasattr(cell, "id"):
            del cell["id"]
    nbformat.validate(nb)


def main() -> int:
    import nbformat
    from nbconvert import HTMLExporter

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-execute",
        action="store_true",
        help="Sanitize committed outputs only (for CI without heimdall.db).",
    )
    args = parser.parse_args()

    nb = nbformat.read(NOTEBOOK, as_version=4)
    sanitize_notebook(nb, execute=not args.no_execute)
    nbformat.write(nb, NOTEBOOK)

    html, _ = HTMLExporter().from_notebook_node(nb)
    HTML_OUT.write_text(html, encoding="utf-8")

    print(f"Wrote {NOTEBOOK}")
    print(f"Wrote {HTML_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
