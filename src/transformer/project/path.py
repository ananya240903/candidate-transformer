"""The `from`-path grammar: parser + resolver (architecture s9a).

    path      := segment ('.' segment)*
    segment   := IDENT subscript?
    subscript := '[' (INT | epsilon) ']'

Three segment behaviours:
  - plain/nested : full_name, location.city  -> walk keys
  - indexed      : emails[0], emails[-1]      -> out of range => MISSING
  - wildcard map : skills[].name              -> map remainder over each elem

Single wildcard level only (no experience[].titles[]). The parser is the
static checker used at config-load time (lane 1): an unparseable or
illegally-nested path is a programmer error, raised before any record runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# Sentinel for "this path resolved to nothing" (key absent / null / index out
# of range / wildcard over a non-list). Distinct from a legitimate None value
# only at resolution time; the interpreter folds a resolved None into MISSING.
MISSING = object()


class PathError(ValueError):
    """A `from`/`path` string that does not parse or violates the grammar.
    Surfaced as a config-time (lane 1) hard error."""


@dataclass(frozen=True)
class Segment:
    ident: str
    kind: str            # "plain" | "index" | "wildcard"
    index: Optional[int] = None


_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(-?\d+|)\])?$")


def parse_path(path: str) -> List[Segment]:
    """Parse a path string into segments, validating the grammar.

    Raises PathError on malformed syntax or more than one wildcard / any
    subscript following a wildcard (single-level descope, s9a).
    """
    if not path or not isinstance(path, str):
        raise PathError(f"empty or non-string path: {path!r}")

    segments: List[Segment] = []
    seen_wildcard = False
    for part in path.split("."):
        match = _SEGMENT_RE.match(part)
        if not match:
            raise PathError(f"malformed path segment {part!r} in {path!r}")
        ident, subscript = match.group(1), match.group(2)

        if seen_wildcard:
            # Nothing may carry a subscript after a wildcard, and a second
            # wildcard is disallowed.
            if subscript is not None:
                raise PathError(
                    f"subscript after wildcard not allowed in {path!r} "
                    "(single wildcard level only)"
                )
            segments.append(Segment(ident, "plain"))
            continue

        if subscript is None:
            segments.append(Segment(ident, "plain"))
        elif subscript == "":
            segments.append(Segment(ident, "wildcard"))
            seen_wildcard = True
        else:
            segments.append(Segment(ident, "index", int(subscript)))

    return segments


def resolve(record: dict, segments: List[Segment]):
    """Resolve parsed segments against a canonical record dict.

    Returns the value, or MISSING. Never raises on data shape: a null
    traversal or wrong-typed node yields MISSING (s9d), it does not crash.
    """
    return _resolve(record, segments)


def _resolve(value, segments: List[Segment]):
    if not segments:
        return value
    if value is None or value is MISSING:
        return MISSING
    if not isinstance(value, dict):
        return MISSING

    seg, rest = segments[0], segments[1:]
    if seg.ident not in value:
        return MISSING
    child = value[seg.ident]

    if seg.kind == "plain":
        return _resolve(child, rest)

    if seg.kind == "index":
        if not isinstance(child, list):
            return MISSING
        try:
            element = child[seg.index]
        except IndexError:
            return MISSING
        return _resolve(element, rest)

    # wildcard: map the remainder over each element. An empty list yields []
    # (PRESENT, not MISSING -- s9d). Elements whose remainder is MISSING are
    # dropped from the result.
    if not isinstance(child, list):
        return MISSING
    out = []
    for element in child:
        resolved = _resolve(element, rest)
        if resolved is not MISSING:
            out.append(resolved)
    return out
