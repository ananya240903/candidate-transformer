"""Skill canonicalization (architecture s6).

Order: exact alias map -> exact canonical match -> tight rapidfuzz
(token_set_ratio >= threshold) against the canonical vocabulary. An out-of-
vocabulary term is KEPT VERBATIM at lenient confidence (norm_quality 0.85) --
never dropped (losing a real skill is a bug) and never abstained.

The vocab, alias map, and the TIGHT threshold are DATA (`data/skills.json`),
not hardcoded in logic. A loose threshold invents skill identities, so it is
not loosened to "catch more".
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

from .result import CLEAN, LENIENT, NormContext, NormResult

_SKILLS_PATH = Path(__file__).parent / "data" / "skills.json"


@lru_cache(maxsize=1)
def _vocab() -> dict:
    with _SKILLS_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    # Pre-build case-insensitive lookup maps for deterministic exact matching.
    canonical = data["canonical"]
    return {
        "threshold": data["threshold"],
        "canonical": canonical,
        "aliases": {k.lower(): v for k, v in data["aliases"].items()},
        "exact": {c.lower(): c for c in canonical},
    }


def normalize_skill(raw, ctx: Optional[NormContext] = None) -> NormResult:
    """Canonicalize a skill name. Never abstains: OOV is kept verbatim at
    norm_quality 0.85."""
    if raw is None:
        return NormResult.ok("", norm_quality=LENIENT)
    text = str(raw).strip()
    if not text:
        return NormResult.ok("", norm_quality=LENIENT)

    vocab = _vocab()
    key = text.lower()

    # 1. exact alias, 2. exact canonical -> canonical, norm_quality 1.0
    if key in vocab["aliases"]:
        return NormResult.ok(vocab["aliases"][key], norm_quality=CLEAN)
    if key in vocab["exact"]:
        return NormResult.ok(vocab["exact"][key], norm_quality=CLEAN)

    # 3. TIGHT fuzzy match against the canonical vocab.
    match = process.extractOne(
        text, vocab["canonical"], scorer=fuzz.token_set_ratio
    )
    if match is not None and match[1] >= vocab["threshold"]:
        return NormResult.ok(match[0], norm_quality=CLEAN)

    # 4. OOV: keep verbatim at low confidence, never drop.
    return NormResult.ok(text, norm_quality=LENIENT)
