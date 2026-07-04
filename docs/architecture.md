# **Architecture — Candidate Data Transformer**

This is the authoritative design. Implement *this*, not an improvised alternative. Where exact formulas/thresholds are given, use them verbatim (they are tuned to be defensible, not arbitrary). If you believe something here is wrong, flag it and ask.

---

## **1\. The problem, stated precisely**

Master-data resolution in miniature: heterogeneous, partial, conflicting candidate records in → **one canonical, deduplicated, provenance-tracked, confidence-scored profile per real-world person** out, plus a runtime projection layer that reshapes output with **no engine code changes**.

Two distinct merge problems live inside "deduplicate," kept in separate stages:

* **Entity resolution (record level):** which raw records refer to the same human.  
* **Conflict resolution (field level):** given one person's records, which value wins per field, and how confident are we.

Objective function: **wrong-but-confident is worse than honestly-empty.** Abstain rather than guess.

---

## **2\. Source set (committed)**

Two structured, two unstructured — beyond the 1+1 minimum, to show the adapter pattern generalizes.

| Source | Group | Key challenge it showcases |
| ----- | ----- | ----- |
| **ATS JSON** | structured | field-name **remap** (its keys deliberately ≠ ours) |
| **Recruiter CSV** | structured | name/phone normalization; multi-source conflict |
| **GitHub (fixtures)** | unstructured | `languages → skills` provenance; real-API shape, deterministic via fixtures |
| **Recruiter notes (.txt)** | unstructured | regex extraction; naturally low confidence |

Out of scope (stated, not built): live LinkedIn (no public API), resume-PDF NLP depth, LLM extraction in the core path, persistent cross-run ID crosswalk.

---

## **3\. The claim model (keystone)**

Every adapter decomposes its input into a stream of immutable, uniform **claims**:

* Claim {  
*   entity_key:   str        # provisional per-record grouping key (pre-resolution)  
*   field_path:   str        # canonical field this asserts, e.g. "full_name", "emails"  
*   value:        Any        # normalized value (post-normalization)  
*   raw_value:    Any        # original, for provenance/debugging  
*   source:       str        # "ats" | "csv" | "github" | "notes"  
*   method:       str        # how it was extracted (see methods below)  
*   source_trust: float      # from the trust table (§7), stamped at emit time  
*   norm_quality: float      # set by normalize stage; 1.0 clean, 0.85 lenient.
* }


Everything downstream operates on claims. Consequences (why this is the keystone):

* **Provenance** \= the claims behind a value. Not a separate thing to remember.  
* **Conflict resolution** \= a pure reducer `claims -> (value, provenance, confidence)`.  
* **Determinism** \= sort claims canonically, reduce deterministically.  
* **Extensibility** \= a new source is one new adapter emitting claims; merge, confidence, projection are never touched (open/closed).

**Methods** (drive `rel(m)` in §7): `direct_field`, `field_remap`, `api_field`, `regex_extract`, `llm_extract` (unused in core), `inferred`.

---

## **4\. Pipeline stages (in order)**

* detect → ingest → extract→claims → normalize → resolve-entities  
*        → merge → score-confidence → project → validate → emit  
    
1. **Detect** — sniff each input (extension \+ content peek); self-route a directory of mixed files to the right adapter. Decouples "what is this" from "how to parse."  
2. **Ingest** — adapter per source parses raw structure. Wrapped: malformed source → diagnostic \+ zero claims, never an exception.  
3. **Extract → claims** — emit field-level claims with honest `method`. ATS remap, GitHub `languages→skills`, notes regex live here. Stamp `source_trust`.  
4. **Normalize** — per-field normalizers; abstention → `null` \+ low conf \+ recorded failed method. See §6.  
5. **Resolve entities** — blocking → cascade matcher → union-find clustering → deterministic `candidate_id`. See §5.  
6. **Merge** — per cluster, per field, reduce claims to value \+ provenance \+ conf. See §7.  
7. **Score confidence** — per-field and overall. See §8.  
8. **Project** — config-driven interpreter over the canonical record. See §9.  
9. **Validate** — projected output against config-derived schema. See §10.  
10. **Emit** — JSON, plus optional `--explain` diagnostics report.  
    ---

    ## **5\. Entity resolution**

Governing asymmetry: **identifiers are near-unique; names are not.** Bias hard toward under-merging.

### **5a. Blocking (recall — cheap candidate generation)**

Each record emits multiple block keys; any two sharing **any** key become a candidate pair. Multi-pass: a true pair only needs to collide on one key. Comparisons scale with block sizes, not n² — this is the scale story.

| Key | Derivation | Notes |
| ----- | ----- | ----- |
| `E:` | each normalized email | exclude role/shared addrs: `info@`, `hr@`, `recruiting@`, `noreply@`, `careers@`, `jobs@` |
| `P:` | E.164 phone, **last 9 digits** | guards country-code formatting drift |
| `G:` | github login, lowercased |  |
| `N:` | `sorted(metaphone(first), metaphone(last))` | phonetic, order-independent; tolerates "Last, First" |

Do **not** block on email domain or name-as-sole-giant-key (`@gmail.com` → everyone in one block → O(n²) returns). `N:` over-generates for common names — fine; the matcher kills false pairs.

### **5b. Matching cascade (precision — within candidate pairs)**

Normalize name first: NFKD accent strip, lowercase, strip punctuation, drop suffixes (Jr/Sr/II/III/IV), reorder "Last, First", collapse middle initials.

First decisive rule wins:

* **Tier 1 — strong unique id → MERGE.** Shared normalized email OR shared E.164 phone OR shared github login. (Role/shared emails already excluded in blocking.)  
* **Tier 2 — name \+ corroboration → MERGE.** High name similarity AND ≥1 independent corroborator (same city/region, same current\_company, same email *domain* even if local parts differ, or overlapping education institution).  
  * "High name similarity" \= Jaro-Winkler ≥ **0.92** OR rapidfuzz `token_set_ratio` ≥ **90**.  
* **Tier 3 — name only, no corroboration → DO NOT MERGE.** Record as `possible_duplicate` in diagnostics; keep records separate. **This is the false-merge guard** — the most important precision decision in the system.

  ### **5c. Clustering**

Tier-1 and Tier-2 edges → union-find. **Tier-3 edges do NOT union** (surfaced, not acted on). Connected components \= candidates. Process nodes/edges in **sorted order** for deterministic component assignment.

### **5d. candidate\_id**

`candidate_id` \= stable hash (e.g. sha256, hex-truncated) of the cluster's **strongest identity key**, chosen by priority: email → phone → github → normalized-name; ties broken lexicographically. Stateless, reproducible. **Stated limitation:** true cross-run stability needs a persistent crosswalk (out of scope); the id shifts if the strongest key changes. Accept and document.

### **5e. Tracked tradeoffs (put in decisions.md)**

* Transitive closure can over-chain (A\~B by email, B\~C by phone → {A,B,C}). Usually correct; `cluster_conf` (§8) is set by the **weakest** edge holding the cluster, so thin clusters are explicitly less trusted.  
* We reject Fellegi–Sunter probabilistic linkage for scope: it needs labeled pairs to calibrate m/u weights; uncalibrated it's a fragile, unexplainable cascade. Name it in the writeup as a deliberate choice.  
  ---

  ## **6\. Normalization (exact formats)**

| Field | Normal form | Abstention rule |
| ----- | ----- | ----- |
| name | NFKD strip, title-case display; internal normalized form for matching | never abstains (keep raw if odd) |
| email | lowercase, trim; validate syntax | invalid syntax → drop claim (not a guess) |
| phone | **E.164** via `phonenumbers`, region inferred from location if available | **no region \+ unparseable → abstain → null \+ low conf** |
| date | **YYYY-MM** via dateutil | unparseable → null; partial (year only) → `YYYY` allowed, flagged |
| country | **ISO-3166 alpha-2** via pycountry | unmappable → null |
| skill | canonical via alias map \+ rapidfuzz; **OOV kept verbatim at low conf, never dropped** | tight threshold (see below) |

`norm_quality` per claim: **1.0** clean normalization, **0.85** lenient/coerced, claim → null (conf 0\) if normalizer abstained.

**Skill canonicalization:** alias map first (exact), then rapidfuzz against the canonical vocabulary with a **tight** threshold (`token_set_ratio ≥ 90`) — a loose threshold invents skill identities. OOV terms are **kept verbatim** at low confidence, not dropped (losing a real skill is a bug). Multi-valued, so no winner-picking.

---

## **7\. Conflict resolution (the merge reducer)**

Per cluster, per canonical field, reduce the claim set.

**Two driver tables (externalized as config, not hardcoded magic):**

`trust(source)`:

| ats | csv | github | linkedin | resume | notes | inferred |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| 0.95 | 0.85 | 0.80 | 0.75 | 0.70 | 0.55 | 0.40 |

`rel(method)`:

| direct\_field | field\_remap | api\_field | regex\_extract | llm\_extract | inferred |
| ----- | ----- | ----- | ----- | ----- | ----- |
| 1.00 | 0.97 | 0.95 | 0.75 | 0.70 | 0.50 |

Per-claim **base belief**: `b = trust(source) × rel(method) × norm_quality`. Max achievable `b = 0.95` → confidence never reaches 1.0 by construction.

**Single-valued fields** (`full_name`, `headline`, `location`, `years_experience`): pick a winner (see §8 `support`), keep provenance for losers. Winner ties broken by single-source trust, then lexicographically — stated so the choice is deterministic.

**Multi-valued fields** (`emails`, `phones`, `skills`): **union \+ dedup**, never pick-one. Each distinct value scored by its own `support`. (Losing a real email to "conflict resolution" is a bug.)

---

## **8\. Confidence scoring (exact math)**

Requirements: bounded \[0,1\], monotonic (agreement ↑, conflict ↓), deterministic, honest (contested/unidentifiable → low; nothing \= 1.0).

### **8a. Agreement — noisy-OR**

Independent claims asserting the **same** normalized value combine as:

* support(value) \= 1 − Π\_i (1 − b\_i)     over claims for that value


Diminishing returns done right: two 0.85 sources → 0.9775, not 1.7.

### **8b. Single-valued field confidence — share-discount for conflict**

* support\_win \= noisy-OR over claims for the chosen value  
* support\_alt \= noisy-OR over claims for the strongest competing value  
* share       \= support\_win / (support\_win \+ support\_alt)      \# \=1 if no conflict  
* field\_conf  \= support\_win × share


Behavior: no conflict → `field_conf = support_win`. A 50/50 tie between equally- trusted sources → `share = 0.5` → confidence **halved** ("picked one, barely above a coin flip"). The thesis, made numeric.

### **8c. Multi-valued field confidence**

No conflict semantics. Each value scored by its own `support`. A skill in github+resume+notes scores high; a notes-only skill ≈ `0.55 × 0.75 ≈ 0.41`.

### **8d. Overall confidence — four honest multiplicands**

* overall \= cluster\_conf × base\_overall × (0.5 \+ 0.5 × anchor)  
    
* **base\_overall** \= importance-weighted mean of `field_conf` over **present** fields. Weights: full\_name 3, emails 3, phones 2, experience 2, skills 1.5, location 1, headline 1, education 1, years\_experience 0.5.  
* **anchor** \= `max(field_conf[full_name], best field_conf among emails)`. Factor `(0.5 + 0.5·anchor)` caps an unidentifiable profile at half-confidence: no name \+ no email → overall halved regardless of how rich the rest is. (Confident skills attached to nobody is not a confident profile.)  
* **cluster\_conf** \= entity-resolution certainty, set by the **weakest necessary edge**: **0.97** if held by Tier-1 edges, **0.80** if it depends on a Tier-2 edge, **1.0** for a singleton (nothing merged → no merge risk).

**Rejected alternative:** weighted geometric mean — collapses to \~0 if any single field is weak/missing (too punishing for legitimately-optional fields). The `anchor` factor gives targeted "punish missing *identity*" without that collateral damage.

### **8e. Worked sanity checks (turn into tests)**

* **Clean corroborated** (ATS+CSV agree, joined by shared email): name support ≈ 0.993, anchor ≈ 0.99, cluster\_conf 0.97, base\_overall ≈ 0.93 → overall ≈ **0.90**. High, never 1.0.  
* **Name conflict** (ATS "Jonathan" 0.95 vs notes-regex "John" 0.41): share ≈ 0.70, field\_conf ≈ **0.66**. Mid — picked better source, flagged doubt.  
* **Thin/junk** (notes-only, name but no email/phone): anchor ≈ 0.41, singleton cluster\_conf 1.0, base\_overall ≈ 0.45 → overall ≈ **0.32**. Correctly low.

  ### **8f. Disclosed assumption**

Noisy-OR assumes **source independence**. Sources aren't fully independent (ATS and CSV may trace to the same recruiter typing the same data → over-credited corroboration). State this plainly; the failure direction is known (mild over- confidence on correlated agreement), not silent. In-scope mitigation noted, not built: down-weight/cap claims sharing an origin.

---

## **9\. Projection (the runtime config / "required twist")**

Clean separation: the canonical record is **immutable**; the projection is a **pure view** over it, driven entirely by config. "Same engine, no code changes" means the projector is a **generic interpreter over the config**, not `if config.x` branches.

### **9a. The `from`\-path grammar (closed, statically checkable)**

* path      := segment ('.' segment)\*  
* segment   := IDENT subscript?  
* subscript := '\[' (INT | ε) '\]'


Three segment behaviors:

* **Plain/nested** — `full_name`, `location.city`. Walk keys.  
* **Indexed** — `emails[0]`, `phones[0]`, `emails[-1]` (negative allowed, still deterministic). Out-of-range → MISSING.  
* **Wildcard map** — `skills[].name`. `[]` switches to map-mode: apply the path remainder to each element → list. Single wildcard level only (no `experience[].titles[]`) — stated descope.

Output `path` (`primary_email`, `phone`) is a **flat destination key** (rename/flatten target), not a rich expression. Rich on the read side (`from`), simple on the write side.

### **9b. Two failure lanes (see CLAUDE.md invariant 4\)**

* **Config-time (once, at load):** every `from`/`path` parses; every root field exists in canonical schema; every `normalize` exists; no two fields write the same output `path`; declared `type`s known. Any violation → **hard config error, run never starts.** Ignores `on_missing` entirely.  
* **Record-time (per candidate):** only data absence. The **only** thing `on_missing` governs.

  ### **9c. on\_missing × required matrix**

Resolution yields a value or `MISSING` (key absent / null / index out of range / normalize-abstained). `required` is an output contract; `on_missing` is an absence policy. **When they conflict, `required` wins.**

| required | value | on\_missing | result |
| ----- | ----- | ----- | ----- |
| true | present | (any) | emit value |
| true | MISSING | (any) | **ERROR** (name the contradiction if on\_missing=omit) |
| false | present | (any) | emit value |
| false | MISSING | null | emit `path: null` |
| false | MISSING | omit | drop the key |
| false | MISSING | error | **ERROR** |

`on_missing` is settable **globally and per-field; per-field overrides global.**

### **9d. MISSING semantics (subtle, load-bearing)**

* Wildcard over an **empty array** → `[]` \= **present**, not MISSING (`skills[].name` on zero skills → `[]`).  
* Index into an empty/short array → **MISSING** (`emails[0]` on empty emails).  
* Null traversal (`location.city` when `location` is null) → MISSING, don't crash.

  ### **9e. Projection-time normalize**

Applied to the value pulled via `from`; usually idempotent (re-asserting E.164). **Projection-time normalize abstention → MISSING** → flows into the matrix. A phone that can't coerce to E.164 → null/omit/error per policy, **never fabricated.**

### **9f. Output assembly \+ toggles**

* Field order \= **config field order** (deterministic, not dict-hash).  
* `include_confidence` / `include_provenance` add **sibling keys** (a `confidence` map / `provenance` block keyed by output path) — they do **not** inline into each field. Inlining would force typed fields into objects and break the `type` contract.  
  ---

  ## **10\. Validation**

Build the output schema **dynamically from the config** (`path → type + required`; suggest pydantic `create_model`). Validate the **projected object**, after `on_missing` applied. Common miss to avoid: validating input but not output. Type mismatch (`from` → list where `type: string`) → **error, never coerce.** `required` \+ MISSING raises here if it slipped through.

---

## **11\. Stack & repo layout**

**Stack (Python):** `pydantic` (canonical model \+ dynamic output validation), `phonenumbers` (E.164 \+ honest failure), `email-validator`, `rapidfuzz` (skill \+ name fuzzy), `pycountry` (ISO-3166), `python-dateutil` (lenient dates), `metaphone` (blocking), `typer` or `click` (CLI), `pytest` (gold-profile tests). Functional style: pure reducers, total normalizers; I/O only at edges.

**Layout:**

* candidate-transformer/  
* ├── CLAUDE.md  
* ├── README.md  
* ├── docs/{assignment,architecture,roadmap,decisions}.md  
* ├── src/transformer/  
* │   ├── models.py            \# Claim, CanonicalProfile (pydantic)  
* │   ├── detect.py            \# file sniffing / routing  
* │   ├── adapters/            \# ats.py, csv.py, github.py, notes.py  → emit claims  
* │   ├── normalize/           \# name.py, email.py, phone.py, date.py, country.py, skill.py  
* │   ├── resolve/             \# blocking.py, match.py, cluster.py, candidate\_id.py  
* │   ├── merge.py             \# claim reducer → canonical record \+ provenance  
* │   ├── confidence.py        \# noisy-OR, share, overall  
* │   ├── project/             \# path.py (grammar), interpreter.py, validate.py  
* │   ├── config.py            \# config load \+ config-time validation (lane 1\)  
* │   ├── pipeline.py          \# wires the stages  
* │   └── cli.py  
* ├── fixtures/github/         \# recorded API responses (deterministic path)  
* ├── configs/                 \# default.json \+ at least one custom config  
* ├── sample\_inputs/           \# ats.json, recruiter.csv, notes.txt, github fixtures  
* ├── outputs/                 \# produced JSON committed for the submission  
* └── tests/                   \# gold profiles \+ unit \+ edge-case tests  
    
  ---

  ## **12\. Edge cases to handle \+ test**

phone-without-country → null · two-people-one-name → don't merge (Tier-3) · conflicting emails → keep both, pick none · garbage source → isolate, zero claims, run continues · empty-skills wildcard → `[]` · typo'd `from` → config error at load · `type: string` but `from`→list → validation error · `required:true` \+ `on_missing:omit` → error naming contradiction · duplicate output `path` → config error · null traversal → MISSING not crash.

* 

