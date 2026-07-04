# Candidate Data Transformer

Heterogeneous, partial, conflicting candidate data in → **one canonical,
deduplicated, provenance-tracked, confidence-scored profile per real person**
out, plus a runtime config that reshapes the output with no engine changes.

> **Thesis:** *wrong-but-confident is worse than honestly-empty.* When in
> doubt the system abstains (`null` + low confidence + a recorded failed
> method) rather than guessing.

The design lives in [`docs/architecture.md`](docs/architecture.md); the build
order in [`docs/roadmap.md`](docs/roadmap.md); the running rationale in
[`docs/decisions.md`](docs/decisions.md).

## Status — P0 + P1 + P2

Design rationale for every non-obvious decision is in docs/decisions.md

Four sources in → deduplicated, provenance-tracked, confidence-scored profiles
out, for both the default schema and a custom config.

**Built in P0:** full canonical `pydantic` model + `Claim`; CSV + notes
adapters; the projection interpreter (plain / indexed / wildcard paths, both
failure lanes, the `on_missing × required` matrix); output validation against a
config-derived schema; a CLI.

**Built in P1:** phone→E.164 (region inferred from location, **abstains** with
no region + unparseable), date→YYYY-MM, country→ISO alpha-2, skill
canonicalization (alias + tight rapidfuzz ≥90, OOV kept verbatim); full
conflict resolution (`b = trust × rel × norm_quality`, single-valued winner by
support with losers in provenance, multi-valued union); the confidence model
(noisy-OR support, share-discount, importance-weighted `base_overall`, anchor
gate).

**Built in P2:** real **entity resolution** — multi-pass blocking (E/P/G/N),
the tiered matching cascade (Tier-1 strong id / Tier-2 name + corroborator /
Tier-3 name-only **never merges**, the false-merge guard), union-find
clustering; `cluster_conf` (0.97 / 0.80 / 1.0 by weakest edge) wired into
overall confidence; **ATS JSON** (field-remap) and **GitHub-from-fixtures**
(languages→skills, `--live` opt-in) adapters; abstentions moved to a dedicated
`abstentions` channel so provenance `method` stays clean.

**Deliberately descoped under time (P3)**: per-source try/except hardening beyond adapters, the full
`on_missing` matrix stress, a ~10k-record scale proof, and the `--explain`
diagnostics report.


## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # use a CLEAN venv — a global/conda Pydantic 1.x can shadow the install
pip install -e . pytest
```

## Run

```bash
python -m transformer.cli --inputs <file-or-dir ...> --config <config.json> [--out <path>]
```

- `--inputs` accepts one or more files **or** directories (repeat the flag);
  the file type is auto-detected and routed to the right adapter.
- Omit `--out` to print JSON to stdout; otherwise it is written there.
- A bad config (lane 1) exits non-zero with a clear message before any record
  is read.

On the committed sample inputs:

```bash
# default schema (full canonical profile)
python -m transformer.cli --inputs sample_inputs --config configs/default.json --out outputs/default.json

# the assignment's example custom config
python -m transformer.cli --inputs sample_inputs --config configs/custom_example.json --out outputs/custom_example.json
```

The produced output is committed under [`outputs/`](outputs/) and the gold
tests assert the pipeline reproduces it exactly.

## Sample inputs

7 real people across four sources (CSV, notes, ATS, GitHub), hand-crafted to
exercise every phase: a person across four sources (Tier-1), two same-name
people that must NOT merge (Tier-3), a same-name+same-company pair with no
shared id (Tier-2), a country-less phone (abstention), and notes-/ATS-only
singletons. Full description: [`sample_inputs/README.md`](sample_inputs/README.md).
Entity resolution merges Park's four records and Robert Chen's two, keeps the
two Michael Smiths separate, and the run emits **7 profiles**.

## Tests

```bash
pytest
```

Entity-resolution tests (the two-Michael false-merge guard: same block →
Tier-3 refusal → separate profiles; Park Tier-1; Robert Chen Tier-2; ATS
field-remap; GitHub languages→skills; blocking prunes; `candidate_id` stable
across runs); gold-profile tests for both configs + determinism; the §8e
confidence checks (clean-corroborated lands ~0.92, name-conflict share-discount,
notes-only low); phone abstention; skill canonicalization; the path grammar,
both failure lanes, the `on_missing × required` matrix, error-don't-coerce, and
per-source isolation.

## Assumptions & known limitations

- **Under-merge over false-merge.** Tier-3 (name-only) never unions; a shared
  free-mail domain (gmail/…) is not treated as corroboration. A missed merge is
  recoverable; a false merge silently corrupts two people.
- **`candidate_id` is not cross-run stable** if a cluster's strongest identity
  key changes (a persistent crosswalk is out of scope).
- **Transitive closure can over-chain** (A~B by email, B~C by phone → one
  cluster). Usually correct; `cluster_conf` is set by the weakest edge so thin
  clusters are explicitly less trusted.
- Noisy-OR assumes source independence; correlated sources (e.g. ATS+CSV from
  the same typist) yield mild, known-direction over-confidence on agreement.

## Layout

```
src/transformer/
  models.py            Claim + full CanonicalProfile (pydantic)
  scoring.py           trust/rel/weight tables (data/scoring.json) + belief math
  confidence.py        noisy-OR support, share-discount, base_overall, anchor
  detect.py            file sniffing / routing (.csv/.txt/.json)
  adapters/            csv, notes, ats (field-remap), github (fixtures/--live)
  normalize/           name/email/phone/date/country/skill + abstention stage
                       (data/skills.json = canonical vocab + alias map)
  resolve/             blocking, match (cascade), cluster (union-find),
                       namematch, records, candidate_id
  merge.py             claim reducer -> canonical record + provenance + conf
  project/             path.py (grammar), interpreter.py, validate.py, hooks
  config.py            config load + config-time (lane 1) validation
  pipeline.py          wires the stages
  cli.py
configs/               default.json + custom_example.json
sample_inputs/         recruiter.csv, notes.txt, ats.json (+ README)
fixtures/github/       recorded GitHub API responses (deterministic default)
outputs/               produced JSON, committed
tests/                 gold profiles + ER + unit/edge-case tests
```
