"""Email normalization (architecture s6).

Lowercase + trim, then validate syntax. Invalid syntax -> ABSTAIN, and the
stage DROPS the claim (email is the one field whose abstention is a drop, not
a null+record: a syntactically invalid address is almost certainly not an
address at all). We never guess or repair an address: a fabricated email is
exactly the wrong-but-confident failure the whole system exists to avoid.
"""

from __future__ import annotations

from typing import Optional

from email_validator import EmailNotValidError, validate_email

from .result import CLEAN, NormContext, NormResult


def normalize_email(raw, ctx: Optional[NormContext] = None) -> NormResult:
    """Return the lowercased, validated address, or ABSTAIN on invalid syntax."""
    if raw is None:
        return NormResult.abstain("email_syntax")
    candidate = str(raw).strip().lower()
    if not candidate:
        return NormResult.abstain("email_syntax")
    try:
        # check_deliverability=False keeps us deterministic and offline
        # (no DNS/MX lookups in the default path).
        result = validate_email(candidate, check_deliverability=False)
    except EmailNotValidError:
        return NormResult.abstain("email_syntax")
    return NormResult.ok(result.normalized.lower(), norm_quality=CLEAN)
