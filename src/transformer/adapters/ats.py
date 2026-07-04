"""ATS JSON adapter (structured source) — showcases field-remap.

The ATS blob uses its OWN field names, deliberately != ours, so every claim is
emitted with method `field_remap` (rel 0.97). Input is a JSON list of records
(a single object is also accepted).

ATS key            -> canonical claim
  applicant_name          full_name
  contact.email_address   emails
  contact.phone_number    phones
  employer + role         experience {company, title}
  github_handle           links.github
  city / country          location {city, country}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ..models import Claim
from ..scoring import trust

SOURCE = "ats"
_TRUST = trust(SOURCE)
_METHOD = "field_remap"


def _claim(entity_key: str, field_path: str, value, raw) -> Claim:
    return Claim(entity_key=entity_key, field_path=field_path, value=value,
                 raw_value=raw, source=SOURCE, method=_METHOD,
                 source_trust=_TRUST)


def extract(path: Path) -> List[Claim]:
    """Parse an ATS JSON export into field-remapped claims. Raises on malformed
    JSON; the caller wraps this for per-source isolation."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else [data]
    claims: List[Claim] = []

    for index, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        entity_key = f"{SOURCE}:{index}"
        contact = rec.get("contact") or {}

        def emit(field_path: str, value, raw=None) -> None:
            if value:
                claims.append(_claim(entity_key, field_path, value,
                                     raw if raw is not None else value))

        emit("full_name", (rec.get("applicant_name") or "").strip())
        emit("emails", (contact.get("email_address") or "").strip())
        emit("phones", (contact.get("phone_number") or "").strip())
        emit("links.github", (rec.get("github_handle") or "").strip())

        company = (rec.get("employer") or "").strip()
        title = (rec.get("role") or "").strip()
        if company or title:
            emit("experience",
                 {"company": company or None, "title": title or None,
                  "start": None, "end": None, "summary": None},
                 raw={"employer": company, "role": title})

        city = (rec.get("city") or "").strip()
        country = (rec.get("country") or "").strip()
        if city or country:
            emit("location",
                 {"city": city or None, "region": None,
                  "country": country or None},
                 raw={"city": city, "country": country})

    return claims
