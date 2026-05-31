#!/usr/bin/env python3
"""Execute analyze_narrative.ipynb and keep only GitHub-safe outputs (PNG + text)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "analyze_narrative.ipynb"
DB = ROOT / "heimdall.db"


def _strip_cell_outputs(cell: dict) -> None:
    kept: list[dict] = []
    for out in cell.get("outputs", []):
        otype = out.get("output_type")
        if otype == "stream":
            text = "".join(out.get("text", []))
            if len(text) > 8000:
                out = {**out, "text": text[:8000] + "\n… (truncated)\n"}
            kept.append(out)
        elif otype in ("display_data", "execute_result"):
            data = out.get("data", {})
            if "image/png" in data:
                kept.append(
                    {
                        "output_type": "display_data",
                        "data": {"image/png": data["image/png"]},
                        "metadata": {},
                    }
                )
                continue
            if "text/html" in data:
                continue
            if otype == "execute_result" and "text/plain" in data:
                plain = data["text/plain"]
                if isinstance(plain, list):
                    plain = "".join(plain)
                if len(plain) < 4000 and "<Figure size" not in plain:
                    kept.append(
                        {
                            "output_type": "execute_result",
                            "data": {"text/plain": plain},
                            "metadata": {},
                            "execution_count": out.get("execution_count"),
                        }
                    )
    cell["outputs"] = kept


def main() -> int:
    if not DB.exists():
        print("Skip execute: heimdall.db not found. Format-only pass.", file=sys.stderr)
        nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    else:
        import nbformat
        from nbconvert.preprocessors import ExecutePreprocessor

        nb = nbformat.read(NOTEBOOK, as_version=4)
        ep = ExecutePreprocessor(timeout=120, kernel_name="python3")
        ep.preprocess(nb, {"metadata": {"path": str(ROOT)}})
        nbformat.write(nb, NOTEBOOK)

    for cell in nb["cells"]:
        if cell.get("cell_type") == "code":
            cell["execution_count"] = cell.get("execution_count") or 1
            _strip_cell_outputs(cell)
        else:
            cell.pop("outputs", None)
            cell.pop("execution_count", None)

    nb["nbformat"] = 4
    nb["nbformat_minor"] = 4
    for cell in nb["cells"]:
        cell.pop("id", None)

    NOTEBOOK.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote GitHub-safe notebook: {NOTEBOOK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
