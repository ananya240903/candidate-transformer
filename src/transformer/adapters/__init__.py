"""Source adapter registry.

Each adapter exposes `extract(path) -> list[Claim]`. The pipeline wraps every
call for per-source isolation (invariant 6): a malformed or garbage source
yields a diagnostic and zero claims, never an exception that crashes the run.

CSV, notes, and ATS are file adapters routed by `detect`. GitHub is NOT in this
registry: it is consulted by the pipeline for logins discovered in other
sources (fixtures by default, --live opt-in). See `adapters/github.py`.
"""

from __future__ import annotations

from . import ats as ats_adapter
from . import csv as csv_adapter
from . import notes as notes_adapter

ADAPTERS = {
    "csv": csv_adapter.extract,
    "notes": notes_adapter.extract,
    "ats": ats_adapter.extract,
}
