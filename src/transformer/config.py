"""Projection config: load + config-time (lane 1) validation.

Two failure lanes (CLAUDE.md invariant 4 / architecture s9b):
  - LANE 1 (here): a malformed config path -- typo'd `from`, unknown root
    field, unknown `normalize`, duplicate output `path`, unknown `type`, bad
    `on_missing` -- is a PROGRAMMER error. It is a HARD error raised at load
    time, before any record is touched. `on_missing` does NOT apply to it.
  - LANE 2 (interpreter): a well-formed path that resolves to nothing for a
    record is a data gap, governed by `on_missing`.

Validating here means a bad config can never silently degrade a run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .models import CANONICAL_FIELDS
from .project.normalize_hooks import PROJECTION_NORMALIZERS
from .project.path import PathError, Segment, parse_path

KNOWN_TYPES = {
    "string",
    "string[]",
    "number",
    "number[]",
    "boolean",
    "object",
    "object[]",
}
ON_MISSING_POLICIES = {"null", "omit", "error"}


class ConfigError(Exception):
    """A config-time (lane 1) error: the run never starts."""


@dataclass(frozen=True)
class FieldSpec:
    path: str               # flat output destination key
    from_path: str          # canonical read path (defaults to `path`)
    type: str
    required: bool
    normalize: Optional[str]
    on_missing: Optional[str]  # per-field override of the global policy
    segments: List[Segment] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    fields: List[FieldSpec]
    include_confidence: bool
    include_provenance: bool
    on_missing: str  # global default policy


def load_config(path: Path) -> Config:
    """Load and fully validate a projection config. Raises ConfigError on any
    lane-1 violation."""
    try:
        with Path(path).open(encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc}") from exc

    return _build_config(raw)


def _build_config(raw: dict) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a JSON object")

    global_on_missing = raw.get("on_missing", "null")
    if global_on_missing not in ON_MISSING_POLICIES:
        raise ConfigError(
            f"unknown on_missing policy {global_on_missing!r}; "
            f"expected one of {sorted(ON_MISSING_POLICIES)}"
        )

    raw_fields = raw.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ConfigError("config must declare a non-empty `fields` list")

    specs: List[FieldSpec] = []
    seen_output_paths = set()

    for entry in raw_fields:
        if not isinstance(entry, dict):
            raise ConfigError(f"each field must be an object, got {entry!r}")

        out_path = entry.get("path")
        if not out_path or not isinstance(out_path, str):
            raise ConfigError(f"field is missing a string `path`: {entry!r}")

        # Duplicate output path => two fields write the same key.
        if out_path in seen_output_paths:
            raise ConfigError(f"duplicate output path {out_path!r}")
        seen_output_paths.add(out_path)

        declared_type = entry.get("type")
        if declared_type not in KNOWN_TYPES:
            raise ConfigError(
                f"field {out_path!r} has unknown type {declared_type!r}; "
                f"expected one of {sorted(KNOWN_TYPES)}"
            )

        from_path = entry.get("from", out_path)
        try:
            segments = parse_path(from_path)
        except PathError as exc:
            raise ConfigError(f"field {out_path!r}: {exc}") from exc

        # Root field must exist in the canonical schema.
        root = segments[0].ident
        if root not in CANONICAL_FIELDS:
            raise ConfigError(
                f"field {out_path!r}: `from` root {root!r} is not a canonical "
                f"field {sorted(CANONICAL_FIELDS)}"
            )

        normalize = entry.get("normalize")
        if normalize is not None and normalize not in PROJECTION_NORMALIZERS:
            raise ConfigError(
                f"field {out_path!r}: unknown normalize {normalize!r}; "
                f"expected one of {sorted(PROJECTION_NORMALIZERS)}"
            )

        per_field_on_missing = entry.get("on_missing")
        if (
            per_field_on_missing is not None
            and per_field_on_missing not in ON_MISSING_POLICIES
        ):
            raise ConfigError(
                f"field {out_path!r}: unknown on_missing {per_field_on_missing!r}"
            )

        specs.append(
            FieldSpec(
                path=out_path,
                from_path=from_path,
                type=declared_type,
                required=bool(entry.get("required", False)),
                normalize=normalize,
                on_missing=per_field_on_missing,
                segments=segments,
            )
        )

    return Config(
        fields=specs,
        include_confidence=bool(raw.get("include_confidence", False)),
        include_provenance=bool(raw.get("include_provenance", False)),
        on_missing=global_on_missing,
    )
