"""Minimal ``.ipynb`` load/save helpers (FR-02).

A notebook is just JSON on disk (the nbformat schema). These helpers round-trip a
notebook as a plain Python ``dict`` WITHOUT touching its cells or metadata — no
schema upgrade, no normalization, no reordering — so a load/save cycle preserves
the document exactly. That property is what FR-02 requires.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

_PathLike = Union[str, Path]


def load_notebook(path: _PathLike) -> dict[str, Any]:
    """Load a ``.ipynb`` file into a dict, unchanged.

    :param path: path to the notebook file.
    :returns: the parsed notebook document.
    """
    text = Path(path).read_text(encoding="utf-8")
    nb: dict[str, Any] = json.loads(text)
    return nb


def save_notebook(path: _PathLike, nb: dict[str, Any]) -> None:
    """Write a notebook dict back to ``.ipynb`` without altering its contents.

    The document is serialized exactly as given (cells and metadata untouched).

    :param path: destination path for the notebook file.
    :param nb: the notebook document to write.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
