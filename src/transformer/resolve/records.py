"""RecordView: the per-record projection entity resolution operates on
(architecture s5).

One RecordView per provisional record (one CSV row / notes blurb / ATS record /
GitHub profile), built from that record's already-normalized claims. It exposes
exactly the signals blocking and the matching cascade need -- identifiers,
match-normalized name, and Tier-2 corroborators -- and nothing else.

Role/shared email addresses are excluded from the identifier set (they are not
evidence of one person). Free-mail domains are excluded from the domain
corroborator (a shared gmail.com is not corroboration).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional

from ..models import Claim
from . import namematch

# s5a: role/shared local-parts never anchor a merge.
_ROLE_LOCALPARTS = {"info", "hr", "recruiting", "noreply", "careers", "jobs"}
# Shared consumer domains are not Tier-2 corroboration (under-merge over
# false-merge): two same-name gmail users are not the same person.
_FREE_MAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "proton.me", "protonmail.com", "aol.com",
}


@dataclass(frozen=True)
class RecordView:
    entity_key: str
    emails: FrozenSet[str]         # non-role, for blocking + Tier-1
    phones: FrozenSet[str]         # E.164, for blocking + Tier-1
    github: Optional[str]          # login lowercased, for blocking + Tier-1
    name_norm: str                 # match-normalized, for N: key + Tier-2
    companies: FrozenSet[str]      # Tier-2 corroborator
    cities: FrozenSet[str]         # Tier-2 corroborator
    email_domains: FrozenSet[str]  # Tier-2 corroborator (free-mail excluded)
    institutions: FrozenSet[str]   # Tier-2 corroborator


def _is_role(email: str) -> bool:
    return email.split("@", 1)[0] in _ROLE_LOCALPARTS


def _domain(email: str) -> Optional[str]:
    parts = email.split("@", 1)
    return parts[1] if len(parts) == 2 else None


def _build_one(entity_key: str, claims: List[Claim]) -> RecordView:
    emails, phones, companies, cities, domains, institutions = (
        set(), set(), set(), set(), set(), set())
    github: Optional[str] = None
    names: List[str] = []

    for c in claims:
        if c.abstained:
            continue
        fp, val = c.field_path, c.value
        if fp == "emails" and not _is_role(val):
            emails.add(val)
            dom = _domain(val)
            if dom and dom not in _FREE_MAIL_DOMAINS:
                domains.add(dom)
        elif fp == "phones":
            phones.add(val)
        elif fp == "links.github" and val:
            github = str(val).lower()
        elif fp == "full_name":
            names.append(val)
        elif fp == "experience" and isinstance(val, dict) and val.get("company"):
            companies.add(str(val["company"]).strip().lower())
        elif fp == "location" and isinstance(val, dict):
            for key in ("city", "region"):
                if val.get(key):
                    cities.add(str(val[key]).strip().lower())
        elif fp == "education" and isinstance(val, dict) and val.get("institution"):
            institutions.add(str(val["institution"]).strip().lower())

    # A record has at most one name; if several, pick deterministically.
    name = sorted(names)[0] if names else None
    return RecordView(
        entity_key=entity_key,
        emails=frozenset(emails),
        phones=frozenset(phones),
        github=github,
        name_norm=namematch.normalize_for_match(name),
        companies=frozenset(companies),
        cities=frozenset(cities),
        email_domains=frozenset(domains),
        institutions=frozenset(institutions),
    )


def build_records(claims: List[Claim]) -> List[RecordView]:
    """Group claims by provisional entity_key -> one RecordView each, sorted."""
    by_record: Dict[str, List[Claim]] = defaultdict(list)
    for claim in claims:
        by_record[claim.entity_key].append(claim)
    return [_build_one(key, by_record[key]) for key in sorted(by_record)]
