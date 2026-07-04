"""Date normalization to YYYY-MM via dateutil (architecture s6).

- A full date -> "YYYY-MM" at norm_quality 1.0.
- A year-only value -> "YYYY", flagged lenient (norm_quality 0.85, note
  "year_only").
- Unparseable -> ABSTAIN (null), never a guessed month.

Pure and total. Not wired to a canonical field in P1 (experience start/end are
carried as raw object claims for now); built + unit-tested here, ready to wire.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from dateutil import parser as dateparser

from .result import CLEAN, LENIENT, NormContext, NormResult

_FAILED = "yyyymm"
_YEAR_ONLY_RE = re.compile(r"^\s*(\d{4})\s*$")
# Fixed default so dateutil fills missing fields deterministically (NOT
# datetime.now(), which would be wall-clock and break determinism). We only
# ever emit YYYY-MM, so a present year+month is all that matters.
_DEFAULT = datetime(2000, 1, 1)


def normalize_date(raw, ctx: Optional[NormContext] = None) -> NormResult:
    """Return 'YYYY-MM' (or 'YYYY' for year-only), or ABSTAIN if unparseable."""
    if raw is None:
        return NormResult.abstain(_FAILED)
    text = str(raw).strip()
    if not text:
        return NormResult.abstain(_FAILED)

    # Year-only is partial-but-honest: keep "YYYY", flag it lenient rather than
    # inventing a month.
    year_only = _YEAR_ONLY_RE.match(text)
    if year_only:
        return NormResult.ok(year_only.group(1), norm_quality=LENIENT,
                             note="year_only")

    try:
        parsed = dateparser.parse(text, default=_DEFAULT)
    except (ValueError, OverflowError, TypeError):
        return NormResult.abstain(_FAILED)
    if parsed is None:
        return NormResult.abstain(_FAILED)

    return NormResult.ok(f"{parsed.year:04d}-{parsed.month:02d}", norm_quality=CLEAN)
