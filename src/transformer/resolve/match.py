"""Matching cascade: precision within candidate pairs (architecture s5b).

First decisive rule wins. Governing asymmetry: identifiers are near-unique,
names are not -- so bias hard toward under-merging.

  TIER1  strong unique id  -> MERGE  (shared email OR E.164 phone OR github login)
  TIER2  name + corroborator -> MERGE (high name sim AND >=1 corroborator:
         same city/region, same company, same email DOMAIN, or overlapping
         education institution)
  TIER3  name only, no corroborator -> DO NOT MERGE (possible_duplicate).
         The false-merge guard -- reached via the ACTUAL cascade.
  NO_MATCH  a block collision that is not even a name match (e.g. a metaphone
            clash between different names) -> no edge, not a duplicate.
"""

from __future__ import annotations

from . import namematch
from .records import RecordView

TIER1 = "tier1"
TIER2 = "tier2"
TIER3 = "tier3"
NO_MATCH = "no_match"

# Merge-forming tiers (union-find acts on these); TIER3/NO_MATCH never union.
MERGE_TIERS = (TIER1, TIER2)


def _shares_strong_id(a: RecordView, b: RecordView) -> bool:
    if a.emails & b.emails:
        return True
    if a.phones & b.phones:
        return True
    return bool(a.github and b.github and a.github == b.github)


def _corroborated(a: RecordView, b: RecordView) -> bool:
    """>=1 independent Tier-2 corroborator (s5b)."""
    return bool(
        (a.cities & b.cities)
        or (a.companies & b.companies)
        or (a.email_domains & b.email_domains)  # free-mail already excluded
        or (a.institutions & b.institutions)
    )


def classify_pair(a: RecordView, b: RecordView) -> str:
    """Return the tier for a candidate pair. First decisive rule wins."""
    # Tier 1 -- strong unique identifier.
    if _shares_strong_id(a, b):
        return TIER1

    # Tiers 2/3 require the names to actually be similar. A bare block
    # collision on differing names is NO_MATCH, not a possible_duplicate.
    if not namematch.high_name_similarity(a.name_norm, b.name_norm):
        return NO_MATCH

    # Tier 2 -- high name similarity AND at least one corroborator.
    if _corroborated(a, b):
        return TIER2

    # Tier 3 -- name only, no corroboration. Do NOT merge. This is the guard.
    return TIER3
