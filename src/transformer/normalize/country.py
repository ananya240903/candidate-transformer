"""Country normalization to ISO-3166 alpha-2 via pycountry (architecture s6).

Accepts a country name, alpha-2, or alpha-3; returns the alpha-2 code.
Unmappable -> ABSTAIN (null), never a guessed code.

Pure and total. Used by phone region inference (a record's country claim, if
any, becomes the phone parse region) and ready to wire to `location.country`.
"""

from __future__ import annotations

from typing import Optional

import pycountry

from .result import CLEAN, NormContext, NormResult

_FAILED = "iso3166"


def normalize_country(raw, ctx: Optional[NormContext] = None) -> NormResult:
    """Return an ISO-3166 alpha-2 code, or ABSTAIN if unmappable."""
    if raw is None:
        return NormResult.abstain(_FAILED)
    text = str(raw).strip()
    if not text:
        return NormResult.abstain(_FAILED)

    country = None
    # Exact code lookups first (alpha-2 / alpha-3), then fuzzy-free name lookup.
    upper = text.upper()
    if len(upper) == 2:
        country = pycountry.countries.get(alpha_2=upper)
    elif len(upper) == 3:
        country = pycountry.countries.get(alpha_3=upper)
    if country is None:
        country = pycountry.countries.get(name=text) \
            or pycountry.countries.get(common_name=text) \
            or pycountry.countries.get(official_name=text)

    if country is None:
        return NormResult.abstain(_FAILED)
    return NormResult.ok(country.alpha_2, norm_quality=CLEAN)
