"""Blocking: cheap candidate-pair generation (architecture s5a).

Each record emits multiple block keys; any two records sharing ANY key become
a candidate pair. Multi-pass: a true pair only needs to collide on one key.
Comparisons happen ONLY within blocks, so they scale with block sizes, not n^2
-- this is the scale story.

Keys:
  E:  each normalized non-role email
  P:  E.164 phone, last 9 digits (guards country-code formatting drift)
  G:  github login, lowercased
  N:  sorted(metaphone(first), metaphone(last))  (phonetic, order-independent)

We deliberately do NOT block on email domain or a name-as-sole-giant-key
(@gmail.com -> everyone in one block -> O(n^2)). N: over-generates for common
names -- fine, the matcher kills the false pairs.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set, Tuple

from . import namematch
from .records import RecordView


def _phone_key(e164: str) -> str:
    digits = "".join(ch for ch in e164 if ch.isdigit())
    return "P:" + digits[-9:]


def block_keys(record: RecordView) -> Set[str]:
    """The set of block keys a record participates in."""
    keys: Set[str] = set()
    for email in record.emails:
        keys.add(f"E:{email}")
    for phone in record.phones:
        keys.add(_phone_key(phone))
    if record.github:
        keys.add(f"G:{record.github}")
    n_key = namematch.phonetic_key(record.name_norm)
    if n_key:
        keys.add(n_key)
    return keys


def candidate_pairs(records: List[RecordView]) -> List[Tuple[str, str]]:
    """All candidate (entity_key, entity_key) pairs, sorted & deduped.

    Deterministic: keys and members are sorted before pairing, so the pair
    list is independent of input/record order.
    """
    key_to_members: Dict[str, List[str]] = defaultdict(list)
    for record in records:
        for key in block_keys(record):
            key_to_members[key].append(record.entity_key)

    pairs: Set[Tuple[str, str]] = set()
    for key in sorted(key_to_members):
        members = sorted(set(key_to_members[key]))
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                pairs.add((members[i], members[j]))
    return sorted(pairs)
