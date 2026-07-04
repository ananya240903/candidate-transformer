"""Name normalization + similarity for entity resolution (architecture s5b).

Match-normalization (distinct from the display normalization in normalize/):
NFKD accent strip, lowercase, strip punctuation, reorder "Last, First", drop
suffixes (Jr/Sr/II/III/IV), collapse middle initials. The result feeds both
the phonetic N: block key and the name-similarity tier of the cascade.

"High name similarity" (s5b) = Jaro-Winkler >= 0.92 OR rapidfuzz
token_set_ratio >= 90.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Tuple

from metaphone import doublemetaphone
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

_JARO_WINKLER_MIN = 0.92
_TOKEN_SET_MIN = 90
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def normalize_for_match(name: Optional[str]) -> str:
    """Return the match-normalized form of a name (may be empty)."""
    if not name:
        return ""
    text = _strip_accents(str(name))
    # "Last, First" -> "First Last" (a single leading comma is the ATS/CSV idiom).
    if "," in text:
        last, _, first = text.partition(",")
        text = f"{first} {last}"
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)  # strip punctuation
    tokens = [t for t in text.split() if t not in _SUFFIXES]
    if len(tokens) > 2:
        # collapse middle initials: drop single-char tokens between first/last
        tokens = [tokens[0]] + [t for t in tokens[1:-1] if len(t) > 1] + [tokens[-1]]
    return " ".join(tokens)


def name_tokens(name_norm: str) -> Tuple[Optional[str], Optional[str]]:
    """(first, last) from a match-normalized name. Single-token -> (t, t)."""
    tokens = name_norm.split()
    if not tokens:
        return None, None
    return tokens[0], tokens[-1]


def _metaphone(token: Optional[str]) -> str:
    if not token:
        return ""
    primary, _ = doublemetaphone(token)
    return primary or token.upper()


def phonetic_key(name_norm: str) -> Optional[str]:
    """The N: block key: sorted(metaphone(first), metaphone(last)).

    Order-independent (tolerates "Last, First"); over-generates for common
    names -- fine, the matcher kills false pairs. None if there is no name.
    """
    first, last = name_tokens(name_norm)
    if first is None:
        return None
    codes = sorted([_metaphone(first), _metaphone(last)])
    return "N:" + "|".join(codes)


def high_name_similarity(a_norm: str, b_norm: str) -> bool:
    """s5b: Jaro-Winkler >= 0.92 OR token_set_ratio >= 90."""
    if not a_norm or not b_norm:
        return False
    if JaroWinkler.similarity(a_norm, b_norm) >= _JARO_WINKLER_MIN:
        return True
    return fuzz.token_set_ratio(a_norm, b_norm) >= _TOKEN_SET_MIN
