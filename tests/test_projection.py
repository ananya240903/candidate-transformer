"""Projection unit tests: path grammar, the two failure lanes, the
on_missing x required matrix, and output validation (architecture s9/s10)."""

import json
import tempfile
from pathlib import Path

import pytest

from transformer.config import ConfigError, load_config
from transformer.pipeline import run
from transformer.project.interpreter import ProjectionError
from transformer.project.path import MISSING, parse_path, resolve
from transformer.project.validate import OutputValidationError


def _cfg(data):
    path = Path(tempfile.mktemp(suffix=".json"))
    path.write_text(json.dumps(data), encoding="utf-8")
    return load_config(path)


# --- path grammar (s9a/s9d) ----------------------------------------------

def test_path_plain_nested():
    assert resolve({"a": {"b": 1}}, parse_path("a.b")) == 1


def test_path_indexed_and_out_of_range():
    assert resolve({"e": ["x", "y"]}, parse_path("e[0]")) == "x"
    assert resolve({"e": ["x"]}, parse_path("e[-1]")) == "x"
    assert resolve({"e": []}, parse_path("e[0]")) is MISSING


def test_path_wildcard_empty_array_is_present():
    # wildcard over empty array -> [] (PRESENT, not MISSING)
    assert resolve({"skills": []}, parse_path("skills[].name")) == []


def test_path_wildcard_maps_remainder():
    rec = {"skills": [{"name": "a"}, {"name": "b"}]}
    assert resolve(rec, parse_path("skills[].name")) == ["a", "b"]


def test_path_null_traversal_is_missing_not_crash():
    assert resolve({"location": None}, parse_path("location.city")) is MISSING


# --- lane 1: config-time errors ------------------------------------------

def test_typo_from_root_is_config_error():
    with pytest.raises(ConfigError):
        _cfg({"fields": [{"path": "x", "from": "emailz[0]", "type": "string"}]})


def test_duplicate_output_path_is_config_error():
    with pytest.raises(ConfigError):
        _cfg({"fields": [
            {"path": "n", "from": "full_name", "type": "string"},
            {"path": "n", "from": "emails[0]", "type": "string"},
        ]})


def test_double_wildcard_is_config_error():
    with pytest.raises(ConfigError):
        _cfg({"fields": [{"path": "x", "from": "a[].b[].c", "type": "string"}]})


def test_unknown_normalize_is_config_error():
    with pytest.raises(ConfigError):
        _cfg({"fields": [{"path": "p", "from": "phones[0]", "type": "string",
                          "normalize": "NOPE"}]})


def test_unknown_type_is_config_error():
    with pytest.raises(ConfigError):
        _cfg({"fields": [{"path": "x", "from": "full_name", "type": "str"}]})


# --- lane 2: record-time matrix (s9c) ------------------------------------

SAMPLE = [Path(__file__).resolve().parents[1] / "sample_inputs"]


def test_required_missing_omit_names_contradiction():
    cfg = _cfg({"fields": [
        {"path": "headline", "type": "string", "required": True,
         "on_missing": "omit"}]})
    with pytest.raises(ProjectionError, match="contradiction"):
        run(SAMPLE, cfg)


def test_on_missing_null_emits_null():
    cfg = _cfg({"fields": [
        {"path": "candidate_id", "type": "string", "required": True},
        {"path": "headline", "type": "string", "on_missing": "null"}]})
    profiles = run(SAMPLE, cfg).profiles
    assert all(p["headline"] is None for p in profiles)


def test_on_missing_omit_drops_key():
    cfg = _cfg({"fields": [
        {"path": "candidate_id", "type": "string", "required": True},
        {"path": "headline", "type": "string", "on_missing": "omit"}]})
    profiles = run(SAMPLE, cfg).profiles
    assert all("headline" not in p for p in profiles)


# --- s10: validate output, never coerce ----------------------------------

def test_list_where_string_errors_not_coerces():
    cfg = _cfg({"fields": [
        {"path": "emails", "from": "emails", "type": "string", "required": True}]})
    with pytest.raises(OutputValidationError):
        run(SAMPLE, cfg)
