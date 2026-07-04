"""The normalize pipeline stage (architecture s4/s6).

Per-field normalizers are applied to claim values. Each normalizer is a pure
`(raw, ctx) -> NormResult`. Two abstention behaviours, both honest, never a
guess:

  - DROP_ON_ABSTAIN fields (email): an abstention means the value is almost
    certainly garbage -> the claim is dropped entirely (s6: invalid email ->
    drop claim).
  - everything else (phone, date, country): an abstention means "we had a
    value but could not normalize it" -> the claim is KEPT with value=None,
    norm_quality 0.0, and a recorded failed method, so provenance can show the
    honest failure. The merge stage skips it for values but records it.

Region inference for phones (s6): for each record we derive an ISO-3166
alpha-2 region from a location/country claim IF one exists, and hand it to the
phone normalizer via `NormContext`. P1 inputs carry no location, so the region
is None and a country-less number like "555-0188" abstains -- the headline
case.

Determinism: records are processed in sorted entity_key order; within a record
claim order is preserved. No set/dict iteration leaks into output.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from typing import Callable, Dict, List, Optional

from ..models import Claim
from .country import normalize_country
from .date import normalize_date
from .email import normalize_email
from .name import normalize_name
from .phone import normalize_phone
from .result import NormContext, NormResult
from .skill import normalize_skill

# field_path -> normalizer. All share the (raw, ctx) -> NormResult signature.
FIELD_NORMALIZERS: Dict[str, Callable[..., NormResult]] = {
    "full_name": normalize_name,
    "emails": normalize_email,
    "phones": normalize_phone,
    "skills": normalize_skill,
}

# Fields whose abstention DROPS the claim rather than recording a null+failure.
# Email only (s6): invalid syntax is not an address worth recording.
DROP_ON_ABSTAIN = {"emails"}


def _region_hint(record_claims: List[Claim]) -> Optional[str]:
    """Derive an ISO-3166 alpha-2 region for phone parsing from a record's
    location/country claim, if any. None when the record has no country
    context (the common case in P1 inputs)."""
    for claim in record_claims:
        candidate = None
        if claim.field_path == "location" and isinstance(claim.raw_value, dict):
            candidate = claim.raw_value.get("country")
        elif claim.field_path == "country":
            candidate = claim.raw_value
        if candidate:
            result = normalize_country(candidate)
            if not result.abstained:
                return result.value
    return None


def normalize_claims(claims: List[Claim]) -> List[Claim]:
    """Apply field normalizers per record; handle abstention per field policy."""
    by_record: Dict[str, List[Claim]] = defaultdict(list)
    for claim in claims:
        by_record[claim.entity_key].append(claim)

    out: List[Claim] = []
    for entity_key in sorted(by_record):
        record_claims = by_record[entity_key]
        ctx = NormContext(region=_region_hint(record_claims))

        for claim in record_claims:
            normalizer = FIELD_NORMALIZERS.get(claim.field_path)
            if normalizer is None:
                out.append(claim)  # no normalizer for this field; pass through
                continue

            result = normalizer(claim.raw_value, ctx)

            if result.abstained:
                if claim.field_path in DROP_ON_ABSTAIN:
                    continue  # drop (e.g. invalid email)
                # Keep as a recorded failure: null value, zero quality.
                out.append(dataclasses.replace(
                    claim, value=None, norm_quality=0.0,
                    abstained=True, failed_method=result.failed_method,
                ))
                continue

            out.append(dataclasses.replace(
                claim, value=result.value, norm_quality=result.norm_quality,
            ))
    return out
