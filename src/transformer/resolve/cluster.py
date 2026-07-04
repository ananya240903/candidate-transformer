"""Clustering: connected components over merge edges (architecture s5c).

Tier-1 and Tier-2 edges union; Tier-3 edges do NOT (surfaced, not acted on).
Nodes and edges are processed in SORTED order so component assignment is
deterministic regardless of input order.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


class _UnionFind:
    def __init__(self, nodes: Iterable[str]):
        self.parent: Dict[str, str] = {n: n for n in nodes}

    def find(self, x: str) -> str:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # path compression (order-independent, so determinism holds)
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # Attach the lexicographically larger root under the smaller, so the
        # representative is deterministic.
        lo, hi = sorted([ra, rb])
        self.parent[hi] = lo


def connected_components(
    nodes: List[str],
    edges: List[Tuple[str, str]],
) -> List[List[str]]:
    """Return components as sorted member lists, ordered by first member.

    `edges` are the merge edges only (Tier-1/Tier-2). Isolated nodes come back
    as singletons.
    """
    uf = _UnionFind(sorted(nodes))
    for a, b in sorted(edges):
        uf.union(a, b)

    groups: Dict[str, List[str]] = {}
    for node in sorted(nodes):
        groups.setdefault(uf.find(node), []).append(node)

    return sorted((sorted(members) for members in groups.values()),
                  key=lambda members: members[0])
