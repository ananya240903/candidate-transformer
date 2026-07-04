"""Recruiter CSV adapter (structured source).

Columns: name, email, phone, current_company, title.

Emits direct_field claims. Each row is one provisional record; its
`entity_key` is `csv:<row-index>` (pre-resolution). Real cross-record
grouping happens later -- the adapter never decides identity.
"""

from __future__ import annotations

import csv as _csv
from pathlib import Path
from typing import List

from ..models import Claim
from ..scoring import trust

SOURCE = "csv"
_TRUST = trust(SOURCE)

# CSV column -> canonical scalar field. current_company + title are folded
# into a single `experience` object claim below (not listed here).
_SCALAR_COLUMNS = {
    "name": "full_name",
    "email": "emails",
    "phone": "phones",
}


def extract(path: Path) -> List[Claim]:
    """Parse a recruiter CSV into claims. Raises on a malformed file; the
    caller (pipeline) wraps this for per-source isolation."""
    claims: List[Claim] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        for index, row in enumerate(reader):
            entity_key = f"{SOURCE}:{index}"
            for column, field_path in _SCALAR_COLUMNS.items():
                value = (row.get(column) or "").strip()
                if not value:
                    continue
                claims.append(
                    Claim(
                        entity_key=entity_key,
                        field_path=field_path,
                        value=value,
                        raw_value=value,
                        source=SOURCE,
                        method="direct_field",
                        source_trust=_TRUST,
                    )
                )
            company = (row.get("current_company") or "").strip()
            title = (row.get("title") or "").strip()
            if company or title:
                claims.append(
                    Claim(
                        entity_key=entity_key,
                        field_path="experience",
                        value={
                            "company": company or None,
                            "title": title or None,
                            "start": None,
                            "end": None,
                            "summary": None,
                        },
                        raw_value={"current_company": company, "title": title},
                        source=SOURCE,
                        method="direct_field",
                        source_trust=_TRUST,
                    )
                )
    return claims
