"""Deterministic candidate_id (architecture s5d).

candidate_id = sha256 (hex-truncated) of the cluster's strongest identity
key, chosen by priority: email > phone > github > normalized-name; ties
broken lexicographically. Stateless and reproducible.

Stated limitation (s5d): true cross-run stability needs a persistent
crosswalk (out of scope). The id shifts if the strongest key changes.
"""

from __future__ import annotations

import hashlib
from typing import List

from ..models import Claim

_ID_LENGTH = 16  # hex chars


def candidate_id(cluster_claims: List[Claim]) -> str:
    """Stable id for a cluster, derived from its strongest identity key.

    Priority email -> phone -> github -> normalized-name (s5d); ties broken
    lexicographically. Operates on the whole CLUSTER's claims, so the id is a
    property of the resolved person, not any single source record.
    """
    for field_path in ("emails", "phones", "links.github"):
        values = sorted(
            c.value for c in cluster_claims
            if c.field_path == field_path and not c.abstained and c.value
        )
        if values:
            return _hash(f"{field_path}:{values[0]}")

    names = sorted(c.value for c in cluster_claims
                   if c.field_path == "full_name" and not c.abstained)
    if names:
        return _hash(f"full_name:{names[0]}")

    # No identity at all: fall back to the (sorted) provisional keys so the
    # id is still deterministic.
    keys = sorted(c.entity_key for c in cluster_claims)
    return _hash("entity_key:" + "|".join(keys))


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:_ID_LENGTH]
