"""Gold-profile tests: the committed outputs ARE the gold (architecture s4
emit). The pipeline run on the sample inputs must reproduce them byte-for-byte
(determinism, invariant 2).
"""

import json

from transformer.config import load_config
from transformer.pipeline import run


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_schema_happy_path(sample_inputs, repo_root):
    cfg = load_config(repo_root / "configs" / "default.json")
    result = run(sample_inputs, cfg)
    gold = _load(repo_root / "outputs" / "default.json")
    assert result.profiles == gold


def test_example_config(sample_inputs, repo_root):
    cfg = load_config(repo_root / "configs" / "custom_example.json")
    result = run(sample_inputs, cfg)
    gold = _load(repo_root / "outputs" / "custom_example.json")
    assert result.profiles == gold


def test_determinism_byte_identical(sample_inputs, repo_root):
    """Same inputs -> byte-identical output across runs."""
    cfg = load_config(repo_root / "configs" / "default.json")
    first = json.dumps(run(sample_inputs, cfg).profiles, indent=2)
    second = json.dumps(run(sample_inputs, cfg).profiles, indent=2)
    assert first == second


def test_park_merges_across_four_sources(sample_inputs, repo_root):
    """Park appears in CSV + notes + ATS + GitHub (shared email): ONE merged
    profile, higher-trust spelling wins, skills unioned across notes + github
    languages, github login attached."""
    cfg = load_config(repo_root / "configs" / "default.json")
    profiles = run(sample_inputs, cfg).profiles
    park = next(p for p in profiles if "jon.park@example.com" in p["emails"])
    assert park["full_name"] == "Jonathan Park"          # beats notes "Jon Park"
    assert park["emails"] == ["jon.park@example.com"]     # deduped across sources
    assert park["links"]["github"] == "jonpark"          # from ATS + github
    # notes skills (Django/PostgreSQL/Python) + github languages (Go/TypeScript)
    assert set(s["name"] for s in park["skills"]) == {
        "Django", "Go", "PostgreSQL", "Python", "TypeScript"}
    sources = {pe["source"] for pe in park["provenance"]}
    assert {"csv", "notes", "ats", "github"} <= sources


def test_two_same_name_people_stay_separate(sample_inputs, repo_root):
    """Both Michael Smiths remain separate profiles (Tier-3 refusal) and a
    possible_duplicate diagnostic is surfaced. (The mechanism -- same block,
    Tier-3 refusal -- is proved in test_entity_resolution.)"""
    cfg = load_config(repo_root / "configs" / "default.json")
    result = run(sample_inputs, cfg)
    smiths = [p for p in result.profiles if p["full_name"] == "Michael Smith"]
    assert len(smiths) == 2
    assert {e for p in smiths for e in p["emails"]} == {
        "michael.smith@acme.com",
        "mike.smith.dev@gmail.com",
    }
    assert any(d["reason"].startswith("name-only")
               for d in result.possible_duplicates)
