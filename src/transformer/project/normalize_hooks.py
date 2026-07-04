"""Projection-time normalize hooks (architecture s9e).

The config `normalize` key (e.g. "E164", "canonical") selects one of these.
They are applied to the value pulled via `from` and are usually idempotent
(re-asserting a format the pipeline already produced).

A hook may ABSTAIN -> the interpreter folds that into MISSING, which then flows
through the on_missing x required matrix (the SAME record-time lane as a plain
data gap -- NOT the config-error lane). A phone that cannot coerce to E.164
becomes null/omit/error per policy, never a fabricated value.
"""

from __future__ import annotations

from ..normalize.phone import normalize_phone
from ..normalize.result import NormContext
from ..normalize.skill import normalize_skill

# Sentinel: the hook could not produce a confident value -> treat as MISSING.
ABSTAIN = object()


def _e164(value):
    """Re-assert E.164 on a single phone string. Abstain (-> MISSING) if it
    cannot be parsed without a region -- never fabricate a country code."""
    result = normalize_phone(value, NormContext(region=None))
    return ABSTAIN if result.abstained else result.value


def _canonical(value):
    """Canonicalize skill name(s). `from` may resolve to a list
    (skills[].name) or a single string. Skills never abstain (OOV kept
    verbatim), so this never returns ABSTAIN."""
    if isinstance(value, list):
        return [normalize_skill(v).value for v in value]
    return normalize_skill(value).value


PROJECTION_NORMALIZERS = {
    "E164": _e164,
    "canonical": _canonical,
}
