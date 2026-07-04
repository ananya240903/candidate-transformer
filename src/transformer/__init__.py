"""Multi-source candidate data transformer.

Heterogeneous candidate data in -> one canonical, deduplicated,
provenance-tracked, confidence-scored profile per real person out.

Thesis: wrong-but-confident is worse than honestly-empty. When in doubt,
the system abstains (null + low confidence + a recorded failed method)
rather than guessing.
"""
