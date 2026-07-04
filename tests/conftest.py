"""Shared test fixtures: repo paths."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_inputs():
    return [REPO_ROOT / "sample_inputs"]


@pytest.fixture
def repo_root():
    return REPO_ROOT
