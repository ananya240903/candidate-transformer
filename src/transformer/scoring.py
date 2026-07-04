"""Trust / reliability tables and the belief math.

The two driver tables (architecture s7) are externalized as data
(`data/scoring.json`) rather than hardcoded magic, so they are tunable and
point-at-able in the demo (decision #13).

Provides:
  - `base_belief`        : b = trust(source) x rel(method) x norm_quality
  - `noisy_or`           : agreement combination (s8a)
  - `importance_weights` : per-field weights for base_overall (s8d)

The confidence aggregation that consumes these (share-discount, base_overall,
anchor gate) lives in `confidence.py`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable

_SCORING_PATH = Path(__file__).parent / "data" / "scoring.json"


@lru_cache(maxsize=1)
def _tables() -> dict:
    with _SCORING_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def trust(source: str) -> float:
    """source_trust, stamped onto claims at emit time."""
    return _tables()["trust"][source]


def rel(method: str) -> float:
    """rel(method) reliability multiplier."""
    return _tables()["rel"][method]


def importance_weights() -> Dict[str, float]:
    """Per-field importance weights for the base_overall mean (s8d)."""
    return {k: float(v) for k, v in _tables()["importance_weights"].items()}


def cluster_conf(tier: str) -> float:
    """Cluster confidence for an ER tier: 'tier1' / 'tier2' / 'singleton' (s8d)."""
    return float(_tables()["cluster_conf"][tier])


def base_belief(source: str, method: str, norm_quality: float = 1.0) -> float:
    """Per-claim base belief b = trust x rel x norm_quality (s7).

    Max achievable b = 0.95 (ats x direct_field x 1.0), so confidence never
    reaches 1.0 by construction.
    """
    return trust(source) * rel(method) * norm_quality


def noisy_or(beliefs: Iterable[float]) -> float:
    """support(value) = 1 - prod_i (1 - b_i)  over claims for that value (s8a).

    Diminishing returns done right: two 0.85 sources -> 0.9775, not 1.7.
    Assumes source independence (disclosed assumption, s8f).
    """
    product = 1.0
    for b in beliefs:
        product *= (1.0 - b)
    return 1.0 - product
