"""Uniform normalizer result + context (architecture s6).

Every normalizer is a pure, total function with the signature

    normalize(raw, ctx: NormContext) -> NormResult

returning either a normalized value with a `norm_quality`, or an ABSTENTION
(`NormResult.abstain(...)`). It NEVER guesses a value to satisfy a schema.

`norm_quality` (s6): 1.0 clean normalization, 0.85 lenient/coerced. An
abstention carries norm_quality 0.0 and the name of the method that gave up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# norm_quality tiers, defined by the spec (s6).
CLEAN = 1.0
LENIENT = 0.85


@dataclass(frozen=True)
class NormContext:
    """Per-record context handed to normalizers. Only phone uses `region`
    today (inferred from a location/country claim if the record has one)."""
    region: Optional[str] = None  # ISO-3166 alpha-2, or None if unknown


@dataclass(frozen=True)
class NormResult:
    value: Optional[object]
    norm_quality: float
    failed_method: Optional[str] = None  # set iff this is an abstention
    note: Optional[str] = None           # e.g. "year_only" flag for dates

    @property
    def abstained(self) -> bool:
        return self.failed_method is not None

    @classmethod
    def ok(cls, value: object, norm_quality: float = CLEAN,
           note: Optional[str] = None) -> "NormResult":
        return cls(value=value, norm_quality=norm_quality, note=note)

    @classmethod
    def abstain(cls, failed_method: str) -> "NormResult":
        """Abstention: null value, zero quality, recorded failed method."""
        return cls(value=None, norm_quality=0.0, failed_method=failed_method)
