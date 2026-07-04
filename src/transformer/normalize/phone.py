"""Phone normalization to E.164 via `phonenumbers` (architecture s6).

Region is inferred from the candidate's location/country claim IF the record
has one (carried on `ctx.region` as ISO-3166 alpha-2); otherwise there is no
region. The headline abstention case:

    no region + unparseable  ->  ABSTAIN  (null + recorded failed method)

A bare local number like "555-0188" with no country context becomes null --
NOT a fabricated "+1...". A number that already carries a country code
("+1 415 555 0101") parses with no region and normalizes cleanly.
"""

from __future__ import annotations

from typing import Optional

import phonenumbers

from .result import CLEAN, NormContext, NormResult


def _reason(region: Optional[str]) -> str:
    # Distinguish the headline "no country context" failure from a genuinely
    # malformed number so the abstentions channel is self-explaining.
    return "e164_no_region" if region is None else "e164_invalid"


def normalize_phone(raw, ctx: Optional[NormContext] = None) -> NormResult:
    """Return an E.164 string, or ABSTAIN when it cannot be parsed confidently."""
    region = ctx.region if ctx else None
    if raw is None:
        return NormResult.abstain(_reason(region))
    text = str(raw).strip()
    if not text:
        return NormResult.abstain(_reason(region))

    try:
        # With region=None, only numbers carrying an explicit "+<country>"
        # prefix parse; a bare local number raises -> we abstain rather than
        # assume a country.
        parsed = phonenumbers.parse(text, region)
    except phonenumbers.NumberParseException:
        return NormResult.abstain(_reason(region))

    if not phonenumbers.is_valid_number(parsed):
        return NormResult.abstain(_reason(region))

    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return NormResult.ok(e164, norm_quality=CLEAN)
