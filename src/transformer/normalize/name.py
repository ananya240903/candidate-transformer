"""Name normalization (architecture s6).

NFKD accent strip + title-cased display form. Names NEVER abstain -- if the
input is odd we keep a best-effort display form rather than dropping it
(losing a real name is worse than an imperfect one). The internal
matching-normalized form (used by entity resolution) is P2.

norm_quality: 1.0 for a clean alphabetic name; 0.85 (lenient) when we kept an
odd-but-present token (digits / stray symbols) rather than abstaining.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .result import CLEAN, LENIENT, NormContext, NormResult

_CLEAN_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'\-. ]*$")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_name(raw, ctx: Optional[NormContext] = None) -> NormResult:
    """Return a clean title-cased display name. Never abstains on present
    input; returns an empty-string-free abstention only when there is nothing
    at all to keep (which the stage treats as 'drop' for names is N/A -- names
    are not in the drop set, so an all-empty name simply yields no value)."""
    if raw is None:
        return NormResult.abstain("name_empty")
    text = _strip_accents(str(raw)).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return NormResult.abstain("name_empty")
    # 1.0 for a clean alphabetic name; 0.85 if it carries odd characters we
    # nonetheless keep (never invent, never drop a real name).
    quality = CLEAN if _CLEAN_NAME_RE.match(text) else LENIENT
    return NormResult.ok(text.title(), norm_quality=quality)
