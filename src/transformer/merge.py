"""Merge: reduce one cluster's claims to a canonical record + provenance +
per-field confidence (architecture s7 + s8).

Policy:
  - single-valued (full_name, headline, location, years_experience): pick the
    WINNER by support (s8); ties broken by single-source trust, then
    lexicographically by value -- stated here so the choice is deterministic.
    LOSER claims are kept in provenance. field_conf = support_win * share
    (s8b), so a name conflict visibly discounts confidence.
  - multi-valued (emails, phones, skills): union + dedup; each value scored by
    its own support (s8c), never pick-one. The field's scalar confidence (for
    base_overall / anchor) is the MAX support among its values -- consistent
    with s8d's "best field_conf among emails".

Abstained claims (a normalizer gave up, e.g. a country-less phone) contribute
NO value but ARE recorded in the profile's `abstentions` channel (field,
source, reason). Provenance `method` stays clean. A field whose only claims
abstained is simply absent (not a present field for base_overall).

Determinism: every list is sorted before output; no dict/set iteration leaks.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from . import confidence
from .models import (
    AbstentionEntry,
    CanonicalProfile,
    Claim,
    Experience,
    Links,
    ProvenanceEntry,
    Skill,
)
from .resolve.candidate_id import candidate_id
from .scoring import base_belief

_ROUND = 4  # decimal places for emitted confidences (clean, deterministic)

SINGLE_VALUED = {"full_name", "headline", "location", "years_experience"}
MULTI_SCALAR = {"emails", "phones"}
# Nested link sub-fields (e.g. "links.github") are assembled into the Links
# object; each sub-key is single-valued (winner by support).
_LINKS_PREFIX = "links."


def _belief(claim: Claim) -> float:
    return base_belief(claim.source, claim.method, claim.norm_quality)


def _hashable(value) -> str:
    """A deterministic hashable key for a claim value (handles dict/list)."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _valued(claims: List[Claim]) -> List[Claim]:
    """Claims that carry a usable value (abstentions excluded)."""
    return [c for c in claims if not c.abstained]


def _reduce_single_valued(claims: List[Claim]) -> Optional[Tuple[object, float]]:
    """Winner by support; ties -> single-source trust -> lexicographic.
    Returns (value, field_conf), or None if every claim abstained."""
    valued = _valued(claims)
    if not valued:
        return None

    by_key: Dict[str, List[Claim]] = defaultdict(list)
    value_of: Dict[str, object] = {}
    for claim in valued:
        key = _hashable(claim.value)
        by_key[key].append(claim)
        value_of[key] = claim.value

    supports = {k: confidence.support(_belief(c) for c in g)
                for k, g in by_key.items()}
    # Rank: highest support, then highest single-source trust, then value asc.
    ranked = sorted(
        by_key,
        key=lambda k: (-supports[k],
                       -max(c.source_trust for c in by_key[k]),
                       k),
    )
    winner = ranked[0]
    winner_beliefs = [_belief(c) for c in by_key[winner]]
    # Strongest competing value (if any) drives the share-discount.
    alt_beliefs: List[float] = []
    if len(ranked) > 1:
        alt_beliefs = [_belief(c) for c in by_key[ranked[1]]]

    field_conf = confidence.single_valued_field_conf(winner_beliefs, alt_beliefs)
    return value_of[winner], round(field_conf, _ROUND)


def _reduce_multi_scalar(claims: List[Claim]) -> Optional[Tuple[List[str], float]]:
    """Union + dedup values, sorted; field_conf = max value support."""
    valued = _valued(claims)
    if not valued:
        return None
    by_value: Dict[str, List[Claim]] = defaultdict(list)
    for claim in valued:
        by_value[claim.value].append(claim)
    values = sorted(by_value)
    supports = [confidence.support(_belief(c) for c in by_value[v]) for v in values]
    return values, round(max(supports), _ROUND)


def _reduce_skills(claims: List[Claim]) -> Optional[Tuple[List[Skill], float]]:
    """Group by canonical name; each skill scored by its own support (s8c)."""
    valued = _valued(claims)
    if not valued:
        return None
    by_name: Dict[str, List[Claim]] = defaultdict(list)
    for claim in valued:
        by_name[claim.value].append(claim)
    skills: List[Skill] = []
    supports: List[float] = []
    for name in sorted(by_name):
        group = by_name[name]
        s = confidence.support(_belief(c) for c in group)
        supports.append(s)
        skills.append(Skill(name=name, confidence=round(s, _ROUND),
                            sources=sorted({c.source for c in group})))
    return skills, round(max(supports), _ROUND)


def _reduce_experience(claims: List[Claim]) -> Optional[Tuple[List[Experience], float]]:
    """Union + dedup experience objects (by canonical JSON), sorted."""
    valued = _valued(claims)
    if not valued:
        return None
    by_key: Dict[str, List[Claim]] = defaultdict(list)
    for claim in valued:
        by_key[_hashable(claim.value)].append(claim)
    entries: List[Experience] = []
    supports: List[float] = []
    for key in sorted(by_key):
        group = by_key[key]
        entries.append(Experience(**group[0].value))
        supports.append(confidence.support(_belief(c) for c in group))
    return entries, round(max(supports), _ROUND)


def _reduce_links(claims: List[Claim]) -> Optional[Tuple[Links, float]]:
    """Assemble Links from 'links.<sub>' claims; each sub-key single-valued."""
    by_sub: Dict[str, List[Claim]] = defaultdict(list)
    for claim in _valued(claims):
        sub = claim.field_path[len(_LINKS_PREFIX):]
        by_sub[sub].append(claim)
    if not by_sub:
        return None
    link_kwargs: Dict[str, object] = {}
    supports: List[float] = []
    for sub in sorted(by_sub):
        reduced = _reduce_single_valued(by_sub[sub])
        if reduced is not None:
            link_kwargs[sub], conf = reduced
            supports.append(conf)
    if not supports:
        return None
    return Links(**link_kwargs), round(max(supports), _ROUND)


def _provenance(claims: List[Claim]) -> List[ProvenanceEntry]:
    """Provenance = the (field, source, method) triples behind the values
    (invariant 3), deduped and sorted. `method` stays CLEAN; an abstention is
    recorded in the separate abstentions channel, not smuggled into method."""
    triples = {(c.field_path, c.source, c.method) for c in claims}
    return [ProvenanceEntry(field=f, source=s, method=m)
            for f, s, m in sorted(triples)]


def _abstentions(claims: List[Claim]) -> List[AbstentionEntry]:
    """The honest failure record: (field, source, reason) for every claim whose
    normalizer abstained. Feeds P3's --explain report."""
    entries = sorted({(c.field_path, c.source, c.failed_method)
                      for c in claims if c.abstained})
    return [AbstentionEntry(field=f, source=s, reason=r) for f, s, r in entries]


def merge_cluster(
    claims: List[Claim],
    cluster_conf: float = 1.0,
) -> Tuple[CanonicalProfile, Dict[str, float]]:
    """Reduce one cluster's claims into a canonical profile + per-field
    confidence map (keyed by canonical field name, present fields only).

    `cluster_conf` (s8d) is the entity-resolution certainty set by the weakest
    edge holding the cluster together (0.97 Tier-1 / 0.80 Tier-2 / 1.0
    singleton). It is supplied by the resolve stage.
    """
    by_field: Dict[str, List[Claim]] = defaultdict(list)
    link_claims: List[Claim] = []
    for claim in claims:
        if claim.field_path.startswith(_LINKS_PREFIX):
            link_claims.append(claim)
        else:
            by_field[claim.field_path].append(claim)

    field_conf: Dict[str, float] = {}
    profile_kwargs: Dict[str, object] = {"candidate_id": candidate_id(claims)}

    for field_path, group in by_field.items():
        if field_path in SINGLE_VALUED:
            reduced = _reduce_single_valued(group)
        elif field_path in MULTI_SCALAR:
            reduced = _reduce_multi_scalar(group)
        elif field_path == "skills":
            reduced = _reduce_skills(group)
        elif field_path == "experience":
            reduced = _reduce_experience(group)
        else:
            reduced = None  # unknown/internal field_path -> not an output field
        if reduced is not None:
            profile_kwargs[field_path], field_conf[field_path] = reduced

    if link_claims:
        reduced_links = _reduce_links(link_claims)
        if reduced_links is not None:
            profile_kwargs["links"], field_conf["links"] = reduced_links

    profile_kwargs["provenance"] = _provenance(claims)
    profile_kwargs["abstentions"] = _abstentions(claims)

    overall = confidence.overall_confidence(field_conf, cluster_conf)
    profile_kwargs["overall_confidence"] = round(overall, _ROUND)

    profile = CanonicalProfile(**profile_kwargs)
    return profile, field_conf
