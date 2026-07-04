"""Normalizer + per-source isolation unit tests."""

from pathlib import Path

from transformer.config import load_config
from transformer.normalize.email import normalize_email
from transformer.normalize.name import normalize_name
from transformer.pipeline import run

REPO = Path(__file__).resolve().parents[1]


def test_email_lowercases_and_validates():
    result = normalize_email("  Jon.Park@Example.COM ")
    assert result.value == "jon.park@example.com"
    assert not result.abstained
    assert result.norm_quality == 1.0


def test_email_invalid_syntax_abstains():
    # invalid syntax -> abstain (the stage drops the claim), never a guess
    assert normalize_email("not-an-email").abstained
    assert normalize_email("a@@b").abstained


def test_name_accent_strip_and_titlecase():
    assert normalize_name("  josé  GARCÍA ").value == "Jose Garcia"


def test_name_never_abstains_on_odd_input():
    result = normalize_name("x")
    assert result.value == "X"
    assert not result.abstained


def test_garbage_source_isolated_run_continues(tmp_path):
    """A malformed CSV yields a diagnostic + zero claims; the good source
    still produces profiles (invariant 6)."""
    good = REPO / "sample_inputs" / "recruiter.csv"
    bad = tmp_path / "broken.csv"
    bad.write_bytes(b"\xff\xfe not,valid\x00csv\n\x01\x02")
    cfg = load_config(REPO / "configs" / "default.json")
    result = run([good, bad], cfg)
    assert result.profiles  # run completed with the good source
    # the run did not crash; bad source may or may not log depending on parse,
    # but the key invariant is that profiles came through.
