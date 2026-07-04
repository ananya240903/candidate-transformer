"""P2 entity resolution tests (architecture s5).

Centerpiece: the false-merge guard. Two distinct same-name people must land in
the SAME block (so they ARE compared), have the cascade reach Tier-3, and stay
separate -- proving the MATCHER refuses, not that differing keys skipped the
comparison.
"""

from pathlib import Path

import pytest

from transformer import confidence
from transformer.adapters import ADAPTERS
from transformer.adapters import ats as ats_adapter
from transformer.adapters import github as github_adapter
from transformer.config import load_config
from transformer.detect import resolve_inputs
from transformer.merge import merge_cluster
from transformer.normalize import normalize_claims
from transformer.pipeline import DEFAULT_GITHUB_FIXTURES, run
from transformer.resolve import resolve
from transformer.resolve.blocking import block_keys, candidate_pairs
from transformer.resolve.match import TIER1, TIER2, TIER3, classify_pair
from transformer.resolve.records import build_records

REPO = Path(__file__).resolve().parents[1]
SAMPLE = [REPO / "sample_inputs"]


def _sample_claims():
    claims = []
    for path, adapter in resolve_inputs(SAMPLE):
        if adapter:
            claims.extend(ADAPTERS[adapter](path))
    logins = sorted({c.value for c in claims if c.field_path == "links.github"})
    gh_claims, _ = github_adapter.load(logins, DEFAULT_GITHUB_FIXTURES)
    claims.extend(gh_claims)
    return normalize_claims(claims)


def _records_by_key():
    return {r.entity_key: r for r in build_records(_sample_claims())}


def _find(records, **predicate):
    """Find the single record matching a predicate on its fields."""
    matches = [r for r in records.values()
               if all(getattr(r, k) == v for k, v in predicate.items())]
    assert len(matches) == 1, f"expected exactly one match for {predicate}"
    return matches[0]


# --- CENTERPIECE: two same-name people are compared, then NOT merged ------

def test_two_michael_smiths_same_block_reach_tier3_stay_separate():
    records = _records_by_key()
    michaels = [r for r in records.values() if r.name_norm == "michael smith"]
    assert len(michaels) == 2, "both Michael Smiths must be present as records"
    a, b = michaels

    # 1. They share a block key (the N: phonetic key) -> they ARE compared.
    shared = block_keys(a) & block_keys(b)
    assert any(k.startswith("N:") for k in shared), \
        "the two Michaels must collide in the same N: block"
    pair = tuple(sorted((a.entity_key, b.entity_key)))
    assert pair in set(candidate_pairs(list(records.values()))), \
        "block collision must make them a candidate pair (compared, not skipped)"

    # 2. The cascade reaches Tier-3 (name-only, no corroborator) -> refuse.
    assert classify_pair(a, b) == TIER3
    # ... and it is NOT via a strong-id shortcut nor a corroborator existing:
    assert not (a.emails & b.emails)
    assert not (a.companies & b.companies)
    assert not (a.email_domains & b.email_domains)

    # 3. They remain two separate profiles + a possible_duplicate is surfaced.
    result = run(SAMPLE, load_config(REPO / "configs" / "default.json"))
    smiths = [p for p in result.profiles if p["full_name"] == "Michael Smith"]
    assert len(smiths) == 2
    assert any({a.entity_key, b.entity_key} == {d["left"], d["right"]}
               for d in result.possible_duplicates)


# --- Park: Tier-1 merge across sources ------------------------------------

def test_park_merges_tier1_shared_email_cluster_conf_097():
    claims = _sample_claims()
    park_clusters = [c for c in resolve(claims).clusters
                     if any(cl.value == "jon.park@example.com"
                            for cl in c.claims if cl.field_path == "emails")]
    assert len(park_clusters) == 1                     # one merged Park
    cluster = park_clusters[0]
    assert cluster.tier == "tier1"                     # held by a strong-id edge
    profile, _ = merge_cluster(cluster.claims,
                               confidence.cluster_conf(cluster.tier))
    # csv + notes + ats + github all folded in
    assert {c.source for c in cluster.claims} == {"csv", "notes", "ats", "github"}
    assert profile.overall_confidence == pytest.approx(0.87, abs=0.04)


def test_park_pair_classified_tier1_by_email():
    records = _records_by_key()
    park_csv = _find(records, entity_key="csv:0")
    park_github = _find(records, entity_key="github:jonpark")
    assert classify_pair(park_csv, park_github) == TIER1


# --- Tier-2 merge: same name + same company, no shared id -----------------

def test_robert_chen_tier2_merge_at_080():
    claims = _sample_claims()
    chen_clusters = [c for c in resolve(claims).clusters
                     if any("globex.com" in cl.value
                            for cl in c.claims if cl.field_path == "emails")]
    assert len(chen_clusters) == 1                     # merged despite no shared id
    cluster = chen_clusters[0]
    assert cluster.tier == "tier2"
    profile, _ = merge_cluster(cluster.claims,
                               confidence.cluster_conf(cluster.tier))
    # merged on name + company + email-domain corroboration, different local parts
    assert set(profile.emails) == {"r.chen@globex.com", "robert.chen@globex.com"}


def test_robert_chen_pair_is_tier2_not_tier1():
    records = _records_by_key()
    chens = [r for r in records.values() if r.name_norm == "robert chen"]
    assert len(chens) == 2
    a, b = chens
    assert not (a.emails & b.emails)                   # no shared exact email
    assert a.companies & b.companies                   # same company corroborates
    assert classify_pair(a, b) == TIER2


# --- ATS field-remap + GitHub languages->skills ---------------------------

def test_ats_field_remap_produces_canonical_fields():
    claims = ats_adapter.extract(REPO / "sample_inputs" / "ats.json")
    by = lambda fp: [c for c in claims if c.field_path == fp]
    assert all(c.method == "field_remap" for c in claims)   # the remap showcase
    assert any(c.value == "Jonathan Park" for c in by("full_name"))
    assert any(c.value == "jon.park@example.com" for c in by("emails"))
    assert any(c.value == "jonpark" for c in by("links.github"))
    exp = by("experience")
    assert any(c.value["company"] == "Stripe" for c in exp)
    assert any(c.value["country"] == "US" for c in by("location"))


def test_github_languages_become_skills_api_field():
    claims, diagnostics = github_adapter.load(["jonpark"], DEFAULT_GITHUB_FIXTURES)
    skills = [c for c in claims if c.field_path == "skills"]
    assert {c.value for c in skills} == {"Python", "Go", "TypeScript"}
    assert all(c.method == "api_field" for c in skills)
    assert all(c.source == "github" for c in skills)
    assert not diagnostics                              # fixture found


# --- blocking is sub-quadratic --------------------------------------------

def test_blocking_prunes_no_all_pairs_comparison():
    records = list(_records_by_key().values())
    pairs = set(candidate_pairs(records))
    n = len(records)
    all_pairs = n * (n - 1) // 2
    assert len(pairs) < all_pairs                       # blocking prunes
    # Two unrelated people (Priya, Dana) share no block key -> never compared.
    priya = _find(_records_by_key(), name_norm="priya nair")
    dana = _find(_records_by_key(), name_norm="dana lee")
    assert tuple(sorted((priya.entity_key, dana.entity_key))) not in pairs


# --- determinism: candidate_id stable across runs -------------------------

def test_candidate_ids_stable_across_runs():
    cfg = load_config(REPO / "configs" / "default.json")
    first = [p["candidate_id"] for p in run(SAMPLE, cfg).profiles]
    second = [p["candidate_id"] for p in run(SAMPLE, cfg).profiles]
    assert first == second
    assert len(set(first)) == len(first)                # ids are unique per profile
