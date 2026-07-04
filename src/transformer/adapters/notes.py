"""Recruiter notes adapter (unstructured source).

Free-text blurbs, one candidate per paragraph (blank-line separated). Each
blurb begins with the candidate name, followed by an em-dash / hyphen and
prose containing email, phone, and skills. Extraction is regex-based, so
every claim is emitted with method `regex_extract` -- naturally lower trust
and reliability than a structured field.

Determinism: a fixed split + ordered regexes, no NLP, no network.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from ..models import Claim
from ..scoring import trust

SOURCE = "notes"
_TRUST = trust(SOURCE)

# Name is the text before the first em-dash or " - " separator.
_NAME_RE = re.compile(r"^\s*(.+?)\s*(?:—|\s-\s)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Phone: a leading optional +, then digits/spaces/()-/. with at least 7 digits.
_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{6,}\d")
# Skills: the list following an introducer phrase, up to the next period.
_SKILLS_RE = re.compile(
    r"(?:Strong in|Skilled in|Skills:)\s*(.+?)\.", re.IGNORECASE
)


def _split_skills(blob: str) -> List[str]:
    # Split on commas and the word "and"; preserve first-seen order, dedup.
    parts = re.split(r",|\band\b", blob)
    skills: List[str] = []
    seen = set()
    for part in parts:
        skill = part.strip()
        if skill and skill.lower() not in seen:
            seen.add(skill.lower())
            skills.append(skill)
    return skills


def extract(path: Path) -> List[Claim]:
    """Parse recruiter notes into regex-extracted claims. Raises on read
    failure; the caller wraps this for per-source isolation."""
    text = Path(path).read_text(encoding="utf-8")
    blurbs = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    claims: List[Claim] = []

    for index, blurb in enumerate(blurbs):
        entity_key = f"{SOURCE}:{index}"

        def emit(field_path: str, value: str) -> None:
            claims.append(
                Claim(
                    entity_key=entity_key,
                    field_path=field_path,
                    value=value,
                    raw_value=value,
                    source=SOURCE,
                    method="regex_extract",
                    source_trust=_TRUST,
                )
            )

        name_match = _NAME_RE.search(blurb)
        if name_match:
            emit("full_name", name_match.group(1).strip())

        for email in _EMAIL_RE.findall(blurb):
            emit("emails", email)

        for phone in _PHONE_RE.findall(blurb):
            emit("phones", phone.strip())

        skills_match = _SKILLS_RE.search(blurb)
        if skills_match:
            for skill in _split_skills(skills_match.group(1)):
                emit("skills", skill)

    return claims
