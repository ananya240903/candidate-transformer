"""Wire the stages (architecture s4):

  detect -> ingest -> extract->claims -> normalize -> resolve (blocking +
         cascade + clustering) -> merge -> project -> validate -> emit

GitHub is a special source: after the file adapters run, the pipeline collects
github logins discovered in their claims (e.g. an ATS github_handle) and loads
those profiles from fixtures (deterministic default) or the live API (--live).

Per-source isolation (invariant 6): every adapter call is wrapped -- a
malformed/garbage/unrecognized source yields a diagnostic and zero claims.

Determinism: sources processed in sorted order (detect); clusters via sorted
union-find; profiles sorted by candidate_id. No wall-clock, no random.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import confidence
from .adapters import ADAPTERS
from .adapters import github as github_adapter
from .config import Config
from .detect import resolve_inputs
from .merge import merge_cluster
from .models import Claim
from .normalize import normalize_claims
from .project.interpreter import project
from .project.validate import validate_output
from .resolve import resolve

# GitHub fixtures live at <repo>/fixtures/github, resolved from the package
# location so the default path works regardless of the caller's cwd.
DEFAULT_GITHUB_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "github"


@dataclass
class PipelineResult:
    profiles: List[dict]                       # projected + validated outputs
    diagnostics: List[str] = field(default_factory=list)
    possible_duplicates: List[dict] = field(default_factory=list)


def run(
    input_paths: List[Path],
    config: Config,
    *,
    github_fixtures_dir: Optional[Path] = DEFAULT_GITHUB_FIXTURES,
    live_github: bool = False,
) -> PipelineResult:
    """Run the full pipeline and return projected profiles + diagnostics."""
    diagnostics: List[str] = []
    claims: List[Claim] = []

    # --- detect + ingest + extract (per-source isolated) ------------------
    for file_path, adapter_name in resolve_inputs(input_paths):
        if adapter_name is None:
            diagnostics.append(f"skipped (no adapter for type): {file_path}")
            continue
        try:
            claims.extend(ADAPTERS[adapter_name](file_path))
        except Exception as exc:  # noqa: BLE001 -- isolation is the point
            diagnostics.append(f"source failed, skipped ({adapter_name}): "
                               f"{file_path}: {exc}")

    # --- GitHub source: fetch profiles for discovered logins --------------
    logins = sorted({c.value for c in claims
                     if c.field_path == "links.github" and c.value})
    if logins and (live_github or github_fixtures_dir):
        gh_claims, gh_diags = github_adapter.load(
            logins, github_fixtures_dir, live=live_github)
        claims.extend(gh_claims)
        diagnostics.extend(gh_diags)

    # --- normalize -> resolve (real ER) -> merge --------------------------
    claims = normalize_claims(claims)
    resolution = resolve(claims)

    merged = [
        merge_cluster(cluster.claims, confidence.cluster_conf(cluster.tier))
        for cluster in resolution.clusters
    ]
    # Deterministic output order, independent of cluster discovery order.
    merged.sort(key=lambda pair: pair[0].candidate_id)

    # --- project + validate -> emit ---------------------------------------
    profiles: List[dict] = []
    for profile, field_conf in merged:
        record = profile.model_dump()
        out = project(record, field_conf, profile.overall_confidence, config)
        validate_output(out, config)
        profiles.append(out)

    # Surface Tier-3 pairs (compared, deliberately not merged) as diagnostics.
    for dup in resolution.possible_duplicates:
        diagnostics.append(
            f"possible_duplicate: {dup['left']} ({dup['left_name']}) ~ "
            f"{dup['right']} ({dup['right_name']}) — {dup['reason']}")

    return PipelineResult(
        profiles=profiles,
        diagnostics=diagnostics,
        possible_duplicates=resolution.possible_duplicates,
    )
