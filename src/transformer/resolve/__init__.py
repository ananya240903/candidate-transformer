"""Entity resolution (architecture s5): blocking -> matching cascade ->
union-find clustering.

Replaces P0's throwaway email-else-name grouping wholesale. The governing
asymmetry is under-merge over false-merge: a duplicate profile is recoverable,
a false merge silently corrupts two people.

`resolve(claims)` returns clusters (each tagged with the WEAKEST edge tier that
holds it together, for cluster_conf) plus possible_duplicate diagnostics for
Tier-3 (name-only) pairs that were compared and deliberately NOT merged.

Determinism: records, block keys, candidate pairs, edges, and components are
all processed in sorted order.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from ..models import Claim
from .blocking import block_keys, candidate_pairs  # re-exported for tests
from .cluster import connected_components
from .match import MERGE_TIERS, TIER2, TIER3, classify_pair
from .records import RecordView, build_records

SINGLETON = "singleton"


@dataclass(frozen=True)
class Cluster:
    claims: List[Claim]
    tier: str  # "tier1" | "tier2" | "singleton" -- weakest edge holding it


@dataclass
class ResolveResult:
    clusters: List[Cluster]
    possible_duplicates: List[dict] = field(default_factory=list)


def _weakest_tier(members: set, edge_tier: Dict[tuple, str]) -> str:
    """The weakest merge-edge tier internal to a component (s8d 'weakest edge').
    A conservative under-confidence: any Tier-2 dependency caps the cluster."""
    internal = [t for (a, b), t in edge_tier.items()
                if a in members and b in members]
    if not internal:
        return SINGLETON
    return TIER2 if TIER2 in internal else "tier1"


def resolve(claims: List[Claim]) -> ResolveResult:
    """Cluster claims into candidates via blocking + cascade + union-find."""
    records = build_records(claims)
    by_key: Dict[str, RecordView] = {r.entity_key: r for r in records}

    merge_edges: List[tuple] = []
    edge_tier: Dict[tuple, str] = {}
    possible_duplicates: List[dict] = []

    for a, b in candidate_pairs(records):  # already sorted
        tier = classify_pair(by_key[a], by_key[b])
        if tier in MERGE_TIERS:
            merge_edges.append((a, b))
            edge_tier[(a, b)] = tier
        elif tier == TIER3:
            possible_duplicates.append({
                "left": a,
                "right": b,
                "left_name": by_key[a].name_norm,
                "right_name": by_key[b].name_norm,
                "reason": "name-only match, no corroborating signal (Tier-3)",
            })

    claims_by_record: Dict[str, List[Claim]] = defaultdict(list)
    for claim in claims:
        claims_by_record[claim.entity_key].append(claim)

    clusters: List[Cluster] = []
    for members in connected_components(sorted(by_key), merge_edges):
        member_set = set(members)
        cluster_claims: List[Claim] = []
        for entity_key in members:  # members already sorted
            cluster_claims.extend(claims_by_record[entity_key])
        clusters.append(
            Cluster(claims=cluster_claims,
                    tier=_weakest_tier(member_set, edge_tier))
        )

    return ResolveResult(clusters=clusters,
                         possible_duplicates=possible_duplicates)
