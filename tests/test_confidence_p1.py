"""P1 gold + targeted tests: normalization abstention, conflict resolution,
and the confidence model (architecture s6/s7/s8).

Includes the three s8e worked sanity checks. NOTE: s8e's numbers assume the
real cluster_conf (0.97 Tier-1 / 0.80 Tier-2); P1 pins cluster_conf = 1.0
(real ER is P2), so the corroborated/identified profiles score slightly HIGHER
than the s8e targets. Assertions use tolerant bands and the report states the
actual numbers produced.
"""

import math
from pathlib import Path

import pytest

from transformer import confidence
from transformer.adapters import ADAPTERS
from transformer.adapters import github as github_adapter
from transformer.config import load_config
from transformer.detect import resolve_inputs
from transformer.merge import merge_cluster
from transformer.models import Claim
from transformer.normalize import normalize_claims
from transformer.normalize.skill import normalize_skill
from transformer.pipeline import DEFAULT_GITHUB_FIXTURES, run
from transformer.resolve import resolve
from transformer.scoring import trust

REPO = Path(__file__).resolve().parents[1]
SAMPLE = [REPO / "sample_inputs"]


def _merged_by_name():
    """Run detect->github->normalize->resolve->merge and key merged
    (profile, field_conf) by full_name (sufficient for the sample)."""
    claims = []
    for path, adapter in resolve_inputs(SAMPLE):
        if adapter:
            claims.extend(ADAPTERS[adapter](path))
    logins = sorted({c.value for c in claims if c.field_path == "links.github"})
    gh_claims, _ = github_adapter.load(logins, DEFAULT_GITHUB_FIXTURES)
    claims.extend(gh_claims)
    claims = normalize_claims(claims)
    out = {}
    for cluster in resolve(claims).clusters:
        profile, field_conf = merge_cluster(
            cluster.claims, confidence.cluster_conf(cluster.tier))
        out[profile.full_name] = (profile, field_conf)
    return out


def _claim(field_path, value, source, method, norm_quality=1.0):
    return Claim(entity_key="e", field_path=field_path, value=value,
                 raw_value=value, source=source, method=method,
                 source_trust=trust(source), norm_quality=norm_quality)


# --- s8e worked sanity checks --------------------------------------------

def test_s8e_clean_corroborated_lands_on_090():
    """Two sources agree on identity, merged Tier-1 (shared email) -> the s8e
    clean-corroborated case. With cluster_conf 0.97 wired, overall lands ~0.92,
    on s8e's ~0.90. High, never 1.0."""
    claims = [
        _claim("full_name", "Jordan Reyes", "ats", "direct_field"),
        _claim("full_name", "Jordan Reyes", "csv", "direct_field"),
        _claim("emails", "jordan@corp.com", "ats", "direct_field"),
        _claim("emails", "jordan@corp.com", "csv", "direct_field"),
        _claim("phones", "+14155551234", "csv", "direct_field"),
        _claim("skills", "Python", "ats", "direct_field"),
    ]
    profile, _ = merge_cluster(claims, confidence.cluster_conf("tier1"))
    assert profile.overall_confidence == pytest.approx(0.92, abs=0.03)
    assert profile.overall_confidence < 1.0


def test_s8e_name_conflict_share_discount():
    """The s8e name-conflict worked example, in isolation so the number is
    stable: CSV 'Jonathan Park' (b=0.85) vs notes 'Jon Park' (b=0.4125) ->
    full_name field_conf = 0.85 * 0.85/(0.85+0.4125) ~= 0.57."""
    claims = [
        _claim("full_name", "Jonathan Park", "csv", "direct_field"),
        _claim("full_name", "Jon Park", "notes", "regex_extract"),
    ]
    _, field_conf = merge_cluster(claims)
    assert field_conf["full_name"] == pytest.approx(0.5723, abs=0.005)


def test_park_name_conflict_with_p2_corroboration():
    """In the full P2 graph Park also has ATS + GitHub asserting 'Jonathan
    Park', so the winning value's support (and field_conf) rises above the
    two-source 0.57 -- more agreement, higher confidence, still share-discounted
    below 1.0 by the notes 'Jon Park' minority."""
    park, field_conf = _merged_by_name()["Jonathan Park"]
    assert park.full_name == "Jonathan Park"           # higher-support value wins
    assert field_conf["full_name"] == pytest.approx(0.7054, abs=0.005)
    assert field_conf["full_name"] < 1.0               # still discounted


def test_s8e_notes_only_low_overall():
    """Dana: notes-only, every field at b=0.4125 -> overall ~0.29 (s8e target
    0.32; the difference is the absent thin-profile fields in s8e's example)."""
    dana, _ = _merged_by_name()["Dana Lee"]
    assert dana.overall_confidence == pytest.approx(0.29, abs=0.04)


def test_nothing_reaches_one():
    for profile, _ in _merged_by_name().values():
        assert profile.overall_confidence < 1.0


# --- phone abstention (the headline case) --------------------------------

def test_phone_without_country_abstains_not_fabricated():
    """Priya's '555-0188' has no country code and no region -> phones is empty
    (abstained), recorded in the abstentions channel; NOT a guessed +1.
    Provenance `method` stays clean (no ':abstained' hack)."""
    priya, _ = _merged_by_name()["Priya Nair"]
    assert priya.phones == []                          # abstained, not invented
    # recorded in the dedicated abstentions channel with a real reason
    phone_abstentions = [a for a in priya.abstentions if a.field == "phones"]
    assert phone_abstentions
    assert phone_abstentions[0].source == "csv"
    assert phone_abstentions[0].reason == "e164_no_region"
    # provenance method is clean -- the abstention is NOT smuggled into it
    assert all(":" not in p.method for p in priya.provenance)


def test_phone_with_country_code_normalizes_to_e164():
    park, _ = _merged_by_name()["Jonathan Park"]
    assert park.phones == ["+14155550101"]


# --- skill canonicalization ----------------------------------------------

def test_skill_alias_hits_canonical():
    assert normalize_skill("Postgres").value == "PostgreSQL"
    assert normalize_skill("k8s").value == "Kubernetes"
    assert normalize_skill("Postgres").norm_quality == 1.0


def test_skill_oov_kept_verbatim_low_confidence_not_dropped():
    result = normalize_skill("Underwater Basket Weaving")
    assert result.value == "Underwater Basket Weaving"  # kept verbatim
    assert result.norm_quality == 0.85                  # low confidence
    assert not result.abstained                         # never dropped


def test_skill_tight_threshold_does_not_invent():
    # A term far from any canonical skill stays OOV rather than snapping to one.
    result = normalize_skill("Carpentry")
    assert result.value == "Carpentry"
    assert result.norm_quality == 0.85
