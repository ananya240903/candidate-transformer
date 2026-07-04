"""GitHub adapter (unstructured source) — languages -> skills.

Deterministic default path reads RECORDED fixtures (`fixtures/github/<login>.json`);
`--live` (opt-in, never the default) hits the real API. Logins are discovered
from other sources (e.g. an ATS `github_handle`), so GitHub attaches to a
person already in the graph.

Every claim uses method `api_field` (rel 0.95). A GitHub profile's public email
lets entity resolution join it to the person via a Tier-1 email edge; its login
also forms the G: block key / Tier-1 github edge.

Fixture shape (mirrors what we record from the API):
  {"login","name","email","blog","languages":[...]}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from ..models import Claim
from ..scoring import trust

SOURCE = "github"
_TRUST = trust(SOURCE)
_METHOD = "api_field"


def _claim(entity_key: str, field_path: str, value) -> Claim:
    return Claim(entity_key=entity_key, field_path=field_path, value=value,
                 raw_value=value, source=SOURCE, method=_METHOD,
                 source_trust=_TRUST)


def from_profile(data: dict) -> List[Claim]:
    """Turn one recorded/fetched GitHub profile into claims."""
    login = str(data.get("login") or "").strip()
    if not login:
        return []
    entity_key = f"{SOURCE}:{login.lower()}"
    claims: List[Claim] = [_claim(entity_key, "links.github", login.lower())]

    name = (data.get("name") or "").strip()
    if name:
        claims.append(_claim(entity_key, "full_name", name))
    email = (data.get("email") or "").strip()
    if email:
        claims.append(_claim(entity_key, "emails", email))
    for language in data.get("languages") or []:
        lang = str(language).strip()
        if lang:
            claims.append(_claim(entity_key, "skills", lang))
    return claims


def load(logins: List[str], fixtures_dir: Optional[Path],
         live: bool = False) -> Tuple[List[Claim], List[str]]:
    """Load GitHub claims for discovered logins. Returns (claims, diagnostics).

    Fixtures by default (deterministic); `live=True` fetches from the API. A
    missing fixture or a failed fetch is a per-source diagnostic, never a crash.
    """
    claims: List[Claim] = []
    diagnostics: List[str] = []
    for login in sorted(set(logins)):
        try:
            data = _fetch_live(login) if live else _read_fixture(login, fixtures_dir)
        except Exception as exc:  # noqa: BLE001 -- per-source isolation
            diagnostics.append(f"github source skipped ({login}): {exc}")
            continue
        if data is None:
            diagnostics.append(
                f"github fixture missing for '{login}' "
                f"(looked in {fixtures_dir}); skipped")
            continue
        claims.extend(from_profile(data))
    return claims, diagnostics


def _read_fixture(login: str, fixtures_dir: Optional[Path]) -> Optional[dict]:
    if fixtures_dir is None:
        return None
    path = Path(fixtures_dir) / f"{login.lower()}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_live(login: str) -> dict:
    """Opt-in live fetch (NOT the default path). Aggregates repo languages into
    the same shape as a fixture. Kept minimal and network-isolated."""
    import json as _json
    import urllib.request

    def _get(url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "candidate-transformer"})
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return _json.loads(resp.read().decode("utf-8"))

    user = _get(f"https://api.github.com/users/{login}")
    repos = _get(f"https://api.github.com/users/{login}/repos?per_page=100")
    languages = sorted({r["language"] for r in repos if r.get("language")})
    return {
        "login": user.get("login", login),
        "name": user.get("name"),
        "email": user.get("email"),
        "blog": user.get("blog"),
        "languages": languages,
    }
