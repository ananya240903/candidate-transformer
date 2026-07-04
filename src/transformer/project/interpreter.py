"""Projection interpreter (architecture s9).

A GENERIC interpreter over the config -- not `if config.x` branches. The
canonical record is immutable; the projection is a pure view over it.

Per field: resolve `from` -> apply projection normalize -> run the
on_missing x required matrix (s9c). Then optional `confidence` /
`provenance` sibling keys (s9f). Output field order = config field order.
"""

from __future__ import annotations

from typing import Dict

from ..config import Config, FieldSpec
from .normalize_hooks import ABSTAIN, PROJECTION_NORMALIZERS
from .path import MISSING, resolve

_ROUND = 4


class ProjectionError(Exception):
    """A record-time projection failure: required+MISSING, or on_missing=error.
    Distinct from a config-time ConfigError (lane 2 vs lane 1)."""


def _resolve_field(record: dict, spec: FieldSpec):
    """Resolve one field to a value or MISSING, applying projection normalize.

    A resolved literal `None` is folded into MISSING (s9d: null => MISSING).
    An empty list from a wildcard stays PRESENT.
    """
    value = resolve(record, spec.segments)
    if value is None:
        value = MISSING
    if value is MISSING:
        return MISSING

    if spec.normalize:
        value = PROJECTION_NORMALIZERS[spec.normalize](value)
        if value is ABSTAIN:
            return MISSING
    return value


def project(
    record: dict,
    field_confidence: Dict[str, float],
    overall_confidence: float,
    config: Config,
) -> dict:
    """Project a canonical record dict into the configured output shape."""
    out: dict = {}

    for spec in config.fields:
        value = _resolve_field(record, spec)
        policy = spec.on_missing or config.on_missing

        if value is not MISSING:
            out[spec.path] = value
            continue

        # --- value is MISSING: run the matrix -----------------------------
        if spec.required:
            detail = ""
            if policy == "omit":
                detail = (
                    " (config contradiction: required:true with on_missing:omit)"
                )
            raise ProjectionError(
                f"field {spec.path!r} is required but missing{detail}"
            )
        if policy == "null":
            out[spec.path] = None
        elif policy == "omit":
            continue  # drop the key
        elif policy == "error":
            raise ProjectionError(
                f"field {spec.path!r} is missing and on_missing=error"
            )

    if config.include_confidence:
        out["confidence"] = _confidence_block(out, field_confidence, config)
    if config.include_provenance:
        # Sibling block (s9f): provenance keyed nothing fancy in P0 -- the
        # canonical provenance list, surfaced alongside the projected fields.
        out["provenance"] = record.get("provenance", [])

    return out


def _confidence_block(out, field_confidence, config) -> dict:
    """confidence sibling (s9f): output-path -> confidence. P0 maps each output
    field to its canonical root field's confidence; a field whose root received
    no claims is honestly 0.0 (no evidence), never borrowed. Per-value
    confidence refinement (e.g. emails[0] specifically) is P1."""
    block: dict = {}
    for spec in config.fields:
        if spec.path not in out:
            continue
        root = spec.segments[0].ident
        block[spec.path] = round(field_confidence.get(root, 0.0), _ROUND)
    return block
