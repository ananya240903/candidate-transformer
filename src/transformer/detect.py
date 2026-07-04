"""Detect / route inputs to adapters (architecture s4 step 1).

Decouples "what is this file" from "how to parse it". A directory is expanded
to its files (sorted, for determinism) and each file is routed by extension
plus a light content peek. An unrecognized file is returned with adapter
`None` so the pipeline can record a diagnostic rather than crash.

Routes .csv -> csv, .txt -> notes, .json -> ats. GitHub is NOT routed here: it
is a fixtures/live source the pipeline consults for logins discovered in other
sources, not a user-supplied input file.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

_EXTENSION_MAP = {
    ".csv": "csv",
    ".txt": "notes",
    ".json": "ats",
}


def _route_file(path: Path) -> Optional[str]:
    return _EXTENSION_MAP.get(path.suffix.lower())


def resolve_inputs(paths: List[Path]) -> List[Tuple[Path, Optional[str]]]:
    """Expand files/dirs into a sorted list of (file, adapter-name-or-None).

    Sorting makes the source-processing order deterministic regardless of CLI
    argument order or filesystem listing order.
    """
    files: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(p for p in path.iterdir() if p.is_file())
        else:
            files.append(path)

    routed = [(f, _route_file(f)) for f in files]
    # Sort by path string for a stable, deterministic processing order.
    routed.sort(key=lambda pair: str(pair[0]))
    return routed
