"""The two load-bearing data types: the internal `Claim` and the canonical
output `CanonicalProfile`.

`Claim` is the internal currency (architecture s3): every adapter decomposes
its input into a stream of immutable, uniform claims, and everything
downstream -- provenance, confidence, conflict resolution -- operates on them.

`CanonicalProfile` is the FULL canonical schema (assignment default-output
table). P0 only populates some of these fields; later phases fill the rest
without reshaping the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# --- The claim model (keystone, architecture s3) -------------------------

# Methods drive rel(m) in the scoring tables. `norm_quality` is added per s6
# (1.0 clean / 0.85 lenient; an abstaining normalizer drops the claim instead
# of emitting a low-quality value).
@dataclass(frozen=True)
class Claim:
    entity_key: str       # provisional per-record grouping key (pre-resolution)
    field_path: str       # canonical field this asserts, e.g. "full_name"
    value: Any            # normalized value (post-normalization)
    raw_value: Any        # original, for provenance / debugging
    source: str           # "ats" | "csv" | "github" | "notes"
    method: str           # how it was extracted (see scoring.REL)
    source_trust: float   # stamped at emit time from the trust table
    norm_quality: float = 1.0  # 1.0 clean, 0.85 lenient (s6); 0.0 if abstained
    # Set when a normalizer abstained (s6): value becomes null, the claim
    # contributes no value to its field, but the failed attempt is still
    # recorded in provenance. `failed_method` names the normalizer that gave up
    # (e.g. "e164", "iso3166", "yyyymm").
    abstained: bool = False
    failed_method: Optional[str] = None


# --- Canonical profile (the full output schema) --------------------------

class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # ISO-3166 alpha-2


class Links(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = Field(default_factory=list)


class Skill(BaseModel):
    name: str
    confidence: float
    sources: List[str] = Field(default_factory=list)


class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None  # YYYY-MM
    end: Optional[str] = None
    summary: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None


class ProvenanceEntry(BaseModel):
    # Fixed 3-key shape (assignment). `method` stays CLEAN (e.g. "direct_field")
    # -- abstentions live in their own channel below, not smuggled into method.
    field: str
    source: str
    method: str


class AbstentionEntry(BaseModel):
    # A normalizer that gave up on a real datum (s6). The honest failure record
    # P3's --explain report enumerates. `reason` names why (e.g. "e164_no_region").
    field: str
    source: str
    reason: str


class CanonicalProfile(BaseModel):
    candidate_id: str
    full_name: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    location: Location = Field(default_factory=Location)
    links: Links = Field(default_factory=Links)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    abstentions: List[AbstentionEntry] = Field(default_factory=list)
    overall_confidence: float = 0.0


# The set of legal root fields a config `from`-path may reference. Derived
# from the model so it can never drift from the schema.
CANONICAL_FIELDS = set(CanonicalProfile.model_fields.keys())
