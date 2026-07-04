"""Confidence scoring (architecture s8) — the thesis made numeric.

Bounded [0,1], monotonic (agreement up, conflict down), deterministic, honest
(contested / unidentifiable -> low; nothing -> 1.0). Max per-claim belief is
0.95, so nothing ever reaches 1.0 by construction.

  - s8a agreement      : support(value) = 1 - prod(1 - b_i)        [scoring.noisy_or]
  - s8b single-valued  : field_conf = support_win * share
                         share = support_win / (support_win + support_alt)
  - s8c multi-valued   : each value scored by its own support (no conflict)
  - s8d overall        : cluster_conf * base_overall * (0.5 + 0.5*anchor)
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from .scoring import cluster_conf, importance_weights, noisy_or

# cluster_conf (imported from scoring) is the entity-resolution certainty set
# by the weakest edge holding a cluster together (s8d: 0.97 Tier-1 / 0.80
# Tier-2 / 1.0 singleton). The resolve stage tags each cluster with its weakest
# tier; scoring.cluster_conf maps tier -> value. Accessible as
# confidence.cluster_conf for callers that want one confidence surface.

_WEIGHTS = importance_weights()


def support(beliefs: Iterable[float]) -> float:
    """noisy-OR agreement over claims asserting the same value (s8a)."""
    return noisy_or(beliefs)


def single_valued_field_conf(winner_beliefs: List[float],
                             alt_beliefs: List[float]) -> float:
    """field_conf = support_win * share, with share discounting conflict (s8b).

    No competing value -> share = 1 -> field_conf = support_win. A 50/50 tie
    between equally trusted sources -> share = 0.5 -> confidence halved.
    """
    support_win = noisy_or(winner_beliefs)
    support_alt = noisy_or(alt_beliefs) if alt_beliefs else 0.0
    denom = support_win + support_alt
    share = support_win / denom if denom > 0 else 1.0
    return support_win * share


def overall_confidence(field_conf: Dict[str, float],
                       cluster_conf: float = 1.0) -> float:
    """overall = cluster_conf * base_overall * (0.5 + 0.5*anchor) (s8d).

    `field_conf` contains ONLY present fields (a field with no confident value
    is absent). base_overall is the importance-weighted mean over them; the
    anchor factor caps an unidentifiable profile (no name, no email) at half
    confidence regardless of how rich the rest is.
    """
    if not field_conf:
        return 0.0

    weighted_sum = sum(_WEIGHTS.get(f, 1.0) * c for f, c in field_conf.items())
    total_weight = sum(_WEIGHTS.get(f, 1.0) for f in field_conf)
    base_overall = weighted_sum / total_weight

    # anchor = max(name confidence, best email confidence). Identity, not volume.
    anchor = max(field_conf.get("full_name", 0.0), field_conf.get("emails", 0.0))

    return cluster_conf * base_overall * (0.5 + 0.5 * anchor)
